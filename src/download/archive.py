"""Download historical snapshots from the DATA.GOV.HK Historical Archive.

API docs: https://data.gov.hk/en/help/api-spec

How the archive is organised (checked Sep 2026):
- `list-file-versions?url=..&start=YYYYMMDD&end=YYYYMMDD` returns the snapshot
  `timestamps` (YYYYMMDD-HHMM) plus `data-files`, i.e. bundles (usually one ZIP
  per month) that contain every snapshot of that period.
- `get-file?url=..&time=YYYYMMDD-HHMM` redirects to a single snapshot;
  `get-file?url=..&time=YYYYMMDD` (a bundle timestamp) redirects to the bundle ZIP.

A monthly traffic bundle is ~1 GB, but one day of snapshots is only ~30 MB
compressed. So we read the bundle's central directory with HTTP range
requests and fetch only the members for the requested days. When no bundle
exists yet (e.g. the current month), we fall back to per-snapshot downloads.

Output: data/raw/<source>/<YYYY>/<YYYYMMDD>.zip, one XML per snapshot, named
<YYYYMMDD-HHMM>-<resource file name>. The snapshot time is when the file was
archived, not the measurement time: traffic XMLs lag it by several minutes, so
the parse step must use the timestamps inside each file.
"""

from __future__ import annotations

import io
import struct
import threading
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from posixpath import basename
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import ARCHIVED_SOURCES, RAW_DIR

API = "https://app.data.gov.hk/v1/historical-archive"
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
LOCAL_HEADER_SIG = 0x04034B50

_local = threading.local()


def session() -> requests.Session:
    """One requests.Session per thread, with retries on transient errors."""
    if not hasattr(_local, "session"):
        s = requests.Session()
        retry = Retry(total=5, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "HEAD"))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=32))
        _local.session = s
    return _local.session


def list_versions(resource_url: str, start: date, end: date) -> dict:
    resp = session().get(f"{API}/list-file-versions", timeout=60, params={
        "url": resource_url, "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}"})
    resp.raise_for_status()
    return resp.json()


def resolve(resource_url: str, time: str) -> str:
    """Return the storage URL that `get-file` redirects to for a snapshot or bundle timestamp."""
    resp = session().get(f"{API}/get-file", params={"url": resource_url, "time": time},
                         allow_redirects=False, timeout=60)
    if resp.status_code != 302:
        raise RuntimeError(f"get-file {time} for {resource_url}: HTTP {resp.status_code}")
    return resp.headers["Location"]


def get_snapshot(resource_url: str, time: str) -> bytes:
    resp = session().get(resolve(resource_url, time), timeout=120)
    resp.raise_for_status()
    return resp.content


# --- Reading members of a remote ZIP via HTTP range requests -----------------

class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file backed by HTTP range requests."""

    def __init__(self, url: str):
        self.url = url
        self.pos = 0
        resp = session().head(url, timeout=60)
        resp.raise_for_status()
        self.size = int(resp.headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, buf) -> int:
        if self.pos >= self.size or len(buf) == 0:
            return 0
        data = fetch_range(self.url, self.pos, min(self.pos + len(buf), self.size))
        buf[:len(data)] = data
        self.pos += len(data)
        return len(data)


def fetch_range(url: str, start: int, stop: int) -> bytes:
    """Bytes [start, stop) of a remote file."""
    resp = session().get(url, headers={"Range": f"bytes={start}-{stop - 1}"}, timeout=120)
    resp.raise_for_status()
    if resp.status_code != 206:
        raise RuntimeError(f"server ignored Range header for {url}")
    return resp.content


def extract_member(raw: bytes, info: zipfile.ZipInfo) -> bytes | None:
    """Decompress one ZIP member from bytes starting at its local header.

    Returns None if `raw` is too short (the local extra field can be longer
    than the central directory says); the caller should fetch more bytes.
    """
    sig, _, _, method, _, _, _, _, _, name_len, extra_len = LOCAL_HEADER.unpack_from(raw)
    if sig != LOCAL_HEADER_SIG:
        raise ValueError(f"bad local header for {info.filename}")
    begin = LOCAL_HEADER.size + name_len + extra_len
    if len(raw) < begin + info.compress_size:
        return None
    payload = raw[begin:begin + info.compress_size]
    if method == zipfile.ZIP_STORED:
        data = payload
    elif method == zipfile.ZIP_DEFLATED:
        data = zlib.decompress(payload, -15)
    else:
        raise ValueError(f"unsupported compression method {method} in {info.filename}")
    if zlib.crc32(data) != info.CRC:
        raise ValueError(f"CRC mismatch for {info.filename}")
    return data


@dataclass
class RemoteZip:
    url: str
    members: list[zipfile.ZipInfo]

    def read(self, info: zipfile.ZipInfo) -> bytes:
        slack = 1024
        while True:
            length = LOCAL_HEADER.size + len(info.orig_filename.encode()) + info.compress_size + slack
            data = extract_member(fetch_range(self.url, info.header_offset, info.header_offset + length), info)
            if data is not None:
                return data
            slack *= 8


@lru_cache(maxsize=4)
def open_bundle(url: str) -> RemoteZip:
    with zipfile.ZipFile(io.BufferedReader(HttpRangeFile(url), buffer_size=1 << 20)) as zf:
        return RemoteZip(url, zf.infolist())


# --- Per-day download ---------------------------------------------------------

def resource_name(resource_url: str) -> str:
    return basename(urlparse(resource_url).path)


def day_path(source: str, day: date) -> Path:
    return RAW_DIR / source / f"{day:%Y}" / f"{day:%Y%m%d}.zip"


def download_day(source: str, day: date, workers: int = 8, overwrite: bool = False) -> Path | None:
    """Download all snapshots of `source` archived on `day` into one local ZIP."""
    resource_url = ARCHIVED_SOURCES[source]
    out = day_path(source, day)
    if out.exists() and not overwrite:
        print(f"[skip] {out.relative_to(RAW_DIR)} exists")
        return out

    listing = list_versions(resource_url, day, day)
    prefix, suffix = f"{day:%Y%m%d}-", "-" + resource_name(resource_url)
    bundles = listing.get("data-files") or []

    if bundles:
        # Normally one monthly bundle covers the day; take the members from whichever bundle has them.
        # Bundles occasionally hold the same snapshot twice under one name: skip exact
        # duplicates (same CRC); keep differing ones under a suffixed name.
        items, seen = [], {}
        for bundle in bundles:
            rz = open_bundle(resolve(resource_url, bundle["timestamp"]))
            for info in rz.members:
                name = basename(info.filename)
                if not (name.startswith(prefix) and name.endswith(suffix)):
                    continue
                crcs = seen.setdefault(name, set())
                if info.CRC in crcs:
                    continue
                crcs.add(info.CRC)
                if len(crcs) > 1:
                    name = name.replace(suffix, f"_{len(crcs)}{suffix}")
                items.append((name, lambda rz=rz, info=info: rz.read(info)))
        items.sort(key=lambda item: item[0])
        mode = "bundle"
    else:
        items = [(f"{ts}{suffix}", lambda ts=ts: get_snapshot(resource_url, ts))
                 for ts in listing.get("timestamps", [])]
        mode = "snapshots"

    if not items:
        print(f"[none] {source} {day}: no archived versions")
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".zip.part")
    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool, \
            zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # pool.map keeps input order; results are written as they arrive in that order.
        for name, data in zip((n for n, _ in items), pool.map(lambda item: item[1](), items)):
            zf.writestr(name, data)
            total += len(data)
    tmp.replace(out)
    print(f"[ok]   {source} {day}: {len(items)} snapshots via {mode}, "
          f"{total / 1e6:.0f} MB raw -> {out.stat().st_size / 1e6:.0f} MB")
    return out
