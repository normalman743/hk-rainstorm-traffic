"""Download from the DATA.GOV.HK Historical Archive, driven by a plan file.

A plan says only what to request. Each entry converts directly into get-file
requests -- coverage is not consulted to decide anything -- and whatever the
archive answers (a file, 404, ...) is what you get. Write plans by looking at
`python -m hkdata.discover coverage URL --brief`, with `add` below or by hand.

Plan file: a JSON list of entries, each one resource URL plus either `dates`
or `range`:

    {"url": URL, "dates": [ITEM, ...]}
        "YYYY-MM"     get-file time=YYYYMM01: the whole bundle
        "YYYYMMDD"    get-file time=YYYYMMDD as written: the whole bundle. For
                      copying a bundle timestamp from coverage (`timestamps-zip`),
                      e.g. the current month, which only has daily bundles.
        "YYYY-MM-DD"  from the bundle at time=YYYYMM01, only that day's files
                      (members named YYYYMMDD-...), read with HTTP Range requests
    {"url": URL, "range": ["YYYY-MM", "YYYY-MM"], "exclude": ["YYYY-MM", ...]}
        every month from the first to the last (inclusive) except `exclude`
        (optional), each as "YYYY-MM" above. Months only: to leave out single
        days, delete them after downloading.

How get-file answered `time` (tested 2026-09 on CurrentWeather.xml):
    20250701 (1st of a past month)   -> 302 to that month's bundle (period M)
    20250715 (other day, past month) -> 404 {"message": "Not Found"}
    202507                           -> 400 {"message": "REQUEST ERROR: Invalid time parameter"}
    20260901, 20260915 (this month)  -> 302 to that day's bundle (period D)
So a month that isn't over has no monthly bundle yet: "YYYY-MM", range months
and "YYYY-MM-DD" in the current month (or later) print a warning and are sent
anyway.

Output, under OUT/<url host>/<url path>/:
    bundle/<time>.zip     the bundle exactly as downloaded
    day/<YYYYMMDD>.zip    that day's members of the month bundle: original names,
                          timestamps and contents, re-zipped (deflate level 1);
                          every member kept, duplicates included
An existing output file is skipped unless --overwrite.

Errors: a request answered 429/5xx (or a dropped connection) is retried up to 3
times, each retry printed. A task that still fails -- an archive error (with its
response), a day with no matching member, a CRC mismatch, ... -- is printed and
the rest continue; the failed ones are listed again at the end and the exit
status is 1. Run again to retry them: finished files are skipped.

Whole bundles download several at once by their size from coverage: below
10 MB 32 at a time, below 100 MB 4, larger (or size unknown) one at a time with
a byte progress bar. The parallel ones go first, then the rest in plan order.
Interrupted (Ctrl-C)? Run the same command again: finished files are skipped;
the interrupted file restarts from zero (its .part is overwritten).

Parallel Range requests for a "YYYY-MM-DD" day default to max(1, min(ceil(files
/ 10), 16)). No limit is published by DATA.GOV.HK (API spec, FAQ, terms checked
2026-09); the Range requests go to the archive's storage host
(historical-resource-archive*.oss-cn-hongkong.aliyuncs.com), not data.gov.hk.
One traffic day (1012 files, 2025-06-11) took 100 s at 4, 31 s at 16, 18 s at 32.

Sizes, printed by `show` and by `run` before it starts, come from coverage:
    bundle        `size` of the data-files entry whose timestamp equals `time`
    YYYY-MM-DD    `total-size` of that day: the raw (uncompressed) snapshots;
                  the Range transfer is compressed, so smaller. An entry with
                  more than 20 such days samples 5 at random and scales up.

CLI (every example below has been run):

    python -m hkdata.download add plan.json https://rss.weather.gov.hk/rss/CurrentWeather.xml --range 2026-07 2026-08
    python -m hkdata.download add plan.json https://rss.weather.gov.hk/rss/CurrentWeather.xml --dates 2026-06-15 20260901
    python -m hkdata.download show plan.json
    python -m hkdata.download show plan.json --out data/raw    (files already there: local size, not asked about)
    python -m hkdata.download run plan.json --out data/raw
        other options: --yes (no confirmation), --overwrite, --workers N
"""

from __future__ import annotations

import argparse
import io
import json
import math
import random
import re
import struct
import sys
import threading
import traceback
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

from hkdata.discover import ARCHIVE_API, TIMEOUT, _check, coverage

SAMPLE_ABOVE = 20  # an entry with more "YYYY-MM-DD" days than this is size-estimated from a sample
SAMPLE_SIZE = 5
RETRIES = 3  # per request, on 429/5xx and connection errors; each retry is printed
COVERAGE_WORKERS = 8  # parallel coverage queries in show (data.gov.hk's own API server, so fewer than MAX_WORKERS)
MAX_WORKERS = 16
# whole bundles downloading at once, by size (bytes): below 10 MB 32, below 100 MB 4, else 1
BUNDLE_PARALLEL = ((10e6, 32), (100e6, 4))  # default cap on parallel Range requests (31 s per traffic day at 16, 100 s at 4)
LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
LOCAL_HEADER_SIG = 0x04034B50

_MONTH = re.compile(r"\d{4}-\d{2}")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMESTAMP = re.compile(r"\d{8}")

_local = threading.local()


class _PrintedRetry(Retry):
    """urllib3 Retry that prints every retry (urllib3's own are silent), so a 429
    (rate limit) or 5xx shows up even when a later attempt succeeds."""

    def increment(self, method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None):
        new = super().increment(method, url, response, error, _pool, _stacktrace)  # raises when exhausted
        cause = f"HTTP {response.status}" if response is not None and response.status else repr(error)
        host = f"{_pool.scheme}://{_pool.host}" if _pool is not None else ""
        tqdm.write(f"retry {RETRIES - new.total}/{RETRIES}: {method} {host}{url} after {cause}", file=sys.stderr)
        return new


def _session() -> requests.Session:
    """One Session per thread (downloads run in threads). Retries 429/5xx up to
    RETRIES times, printing each: a day read via Range is ~1000 requests, and one
    transient error shouldn't fail the day."""
    if not hasattr(_local, "session"):
        s = requests.Session()
        retry = _PrintedRetry(total=RETRIES, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                              allowed_methods=("GET", "HEAD"))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=32))
        _local.session = s
    return _local.session


# --- Plan -> requests -------------------------------------------------------------

def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def _month(text: str, what: str) -> date:
    if not _MONTH.fullmatch(text):
        raise ValueError(f"{what}: expected YYYY-MM, got {text!r}")
    return datetime.strptime(text, "%Y-%m").date()


def _warn_unfinished(month: date, item: str) -> None:
    today = date.today()
    if (month.year, month.month) >= (today.year, today.month):
        _warn(f"{item}: month not over, so it likely has no monthly bundle yet "
              f"(get-file time={month:%Y%m%d} gave that day's daily bundle in tests); sending anyway")


def _month_task(url: str, month: date, item: str) -> dict:
    _warn_unfinished(month, item)
    return {"url": url, "item": item, "time": f"{month:%Y%m%d}", "day": None}


def _item_task(url: str, item: str) -> dict:
    if _MONTH.fullmatch(item):
        return _month_task(url, _month(item, "dates"), item)
    if _TIMESTAMP.fullmatch(item):
        return {"url": url, "item": item, "time": item, "day": None}
    if _DAY.fullmatch(item):
        d = date.fromisoformat(item)
        _warn_unfinished(d.replace(day=1), item)
        return {"url": url, "item": item, "time": f"{d:%Y%m}01", "day": f"{d:%Y%m%d}"}
    raise ValueError(f"dates: expected YYYY-MM, YYYY-MM-DD or YYYYMMDD, got {item!r}")


def tasks(entry: dict) -> list[dict]:
    """The requests one plan entry converts to, in plan order: dicts with `url`,
    `item` (what the plan wrote), `time` (get-file's time) and `day` (YYYYMMDD
    to take from the bundle, or None for the whole bundle). Raises ValueError
    for anything that can't be converted; prints warnings to stderr."""
    keys = set(entry)
    if "url" not in keys or keys - {"url"} not in ({"dates"}, {"range"}, {"range", "exclude"}):
        raise ValueError(f"plan entry needs 'url' and either 'dates' or 'range' (+ optional 'exclude'), "
                         f"got keys {sorted(keys)}")
    url = entry["url"]
    if "dates" in entry:
        return [_item_task(url, item) for item in entry["dates"]]

    if len(entry["range"]) != 2:
        raise ValueError(f"range: expected [first YYYY-MM, last YYYY-MM], got {entry['range']!r}")
    first, last = (_month(m, "range (months only)") for m in entry["range"])
    if first > last:
        raise ValueError(f"range: first month {first:%Y-%m} is after last month {last:%Y-%m}")
    exclude = {_month(m, "exclude (whole months only; to leave out days, delete them after downloading)")
               for m in entry.get("exclude", [])}
    months, m = [], first
    while m <= last:
        months.append(m)
        m = date(m.year + m.month // 12, m.month % 12 + 1, 1)
    for m in sorted(exclude - set(months)):
        _warn(f"exclude {m:%Y-%m} is outside range {first:%Y-%m}..{last:%Y-%m}; has no effect")
    return [_month_task(url, m, f"{m:%Y-%m}") for m in months if m not in exclude]


def load(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())


def add(path: Path, entry: dict) -> list[dict]:
    """Append `entry` to the plan file (created if missing), after checking it
    converts; returns its tasks."""
    entry_tasks = tasks(entry)
    plan = load(path) if Path(path).exists() else []
    plan.append(entry)
    Path(path).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    return entry_tasks


# --- Sizes -----------------------------------------------------------------------

def _mb(n: float) -> str:
    if n >= 1e9:
        return f"{n / 1e9:,.2f} GB"
    return f"{n / 1e6:,.1f} MB" if n >= 1e6 else f"{n / 1e3:,.1f} kB"


def _bundle_size(task: dict) -> tuple[int | None, str]:
    try:
        d = datetime.strptime(task["time"], "%Y%m%d").date()
    except ValueError:  # display only: the request itself is still sent as written
        return None, f"time={task['time']} is not a date, so coverage can't be asked; size unknown"
    found = [b for b in coverage(task["url"], d, d)["data-files"] if b["timestamp"] == task["time"]]
    if len(found) != 1:
        return None, f"coverage has {len(found)} bundles with timestamp {task['time']}; size unknown"
    return found[0]["size"], f"{_mb(found[0]['size'])} zip, period {found[0]['period']}"


def _day_raw_size(task: dict) -> int:
    d = date.fromisoformat(task["item"])
    return coverage(task["url"], d, d)["total-size"]


def show(plan: list[dict], plan_tasks: list[list[dict]], out: Path | None = None) -> dict[int, int | None]:
    """Print every task of the plan with its size from coverage, and the totals.
    `plan_tasks` is [tasks(entry) for entry in plan]. One coverage request per
    bundle and per (sampled) day, COVERAGE_WORKERS at a time; printed once all
    have answered, in plan order. Returns {id(task): bundle size in bytes or None}
    for the whole-bundle tasks still to download, for run(sizes=...).

    `out`: a task whose output file already exists under it isn't asked about;
    it's shown with the local file's size and left out of the totals to download."""
    local = {}  # id(task) -> size of the already-downloaded output file
    if out is not None:
        for ts in plan_tasks:
            for t in ts:
                path = output_path(out, t)
                if path.exists():
                    local[id(t)] = path.stat().st_size
    sampled = []  # per entry: the "YYYY-MM-DD" tasks (not yet downloaded) whose size is looked up
    for entry_tasks in plan_tasks:
        days = [t for t in entry_tasks if t["day"] is not None and id(t) not in local]
        sampled.append(random.sample(days, SAMPLE_SIZE) if len(days) > SAMPLE_ABOVE else days)
    queries = ([t for ts in plan_tasks for t in ts if t["day"] is None and id(t) not in local]
               + [t for ts in sampled for t in ts])
    with ThreadPoolExecutor(max_workers=COVERAGE_WORKERS) as pool:
        answers = list(tqdm(pool.map(lambda t: _bundle_size(t) if t["day"] is None else _day_raw_size(t), queries),
                            total=len(queries), unit="query", desc="coverage", leave=False))
    answer = {id(t): a for t, a in zip(queries, answers)}

    bundle_total, bundle_unknown, day_total, day_estimated = 0, 0, 0, False
    for i, (entry, entry_tasks, entry_sampled) in enumerate(zip(plan, plan_tasks, sampled), 1):
        print(f"== entry {i}/{len(plan)}: {entry['url']} ({len(entry_tasks)} request(s))")
        days = [t for t in entry_tasks if t["day"] is not None and id(t) not in local]
        sizes = {id(t): answer[id(t)] for t in entry_sampled}
        for t in entry_tasks:
            if id(t) in local:
                note = f"exists, {_mb(local[id(t)])} local"
            elif t["day"] is None:
                size, note = answer[id(t)]
                bundle_total += size or 0
                bundle_unknown += size is None
            else:
                note = (f"{_mb(sizes[id(t)])} raw (uncompressed)" if id(t) in sizes else "not sampled")
            print(f"  {t['item']:<10} time={t['time']}" + (f" day={t['day']}" if t["day"] else "") + f" | {note}")
        if days:
            per_day = sum(sizes.values()) / len(sizes)
            day_total += per_day * len(days)
            if len(entry_sampled) < len(days):
                day_estimated = True
                print(f"  days: ~{_mb(per_day * len(days))} raw, estimated from {len(entry_sampled)} sampled "
                      f"of {len(days)} ({_mb(per_day)} per day on average)")
    if local:
        print(f"already downloaded: {len(local)} file(s), {_mb(sum(local.values()))} local (not asked about)")
    print(f"total bundles: {_mb(bundle_total)} zip" + (f" (+{bundle_unknown} of unknown size)" if bundle_unknown else ""))
    print(f"total days via Range: {'~' if day_estimated else ''}{_mb(day_total)} raw (uncompressed); "
          f"the transfer is compressed, so smaller")
    return {id(t): answer[id(t)][0] for ts in plan_tasks for t in ts if t["day"] is None and id(t) not in local}


# --- Remote ZIP via HTTP Range ---------------------------------------------------

def _resolve(url: str, time: str) -> str:
    """The storage URL get-file redirects to."""
    resp = _session().get(f"{ARCHIVE_API}/get-file", params={"url": url, "time": time},
                          allow_redirects=False, timeout=TIMEOUT)
    _check(resp)
    if resp.status_code != 302:
        raise requests.HTTPError(f"get-file time={time} for {url}: expected 302, got {resp.status_code}\n"
                                 f"response body:\n{resp.text}", response=resp)
    return resp.headers["Location"]


def _fetch_range(url: str, start: int, stop: int) -> bytes:
    """Bytes [start, stop) of a remote file."""
    resp = _check(_session().get(url, headers={"Range": f"bytes={start}-{stop - 1}"}, timeout=TIMEOUT))
    if resp.status_code != 206:
        raise requests.HTTPError(f"expected 206 for a Range request to {url}, got {resp.status_code}",
                                 response=resp)
    return resp.content


class _RangeFile(io.RawIOBase):
    """Seekable read-only remote file, so zipfile can read a bundle's central directory
    without downloading the bundle."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        self.size = int(_check(_session().head(url, timeout=TIMEOUT)).headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        self.pos = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence] + offset
        return self.pos

    def readinto(self, buf) -> int:
        if self.pos >= self.size or len(buf) == 0:
            return 0
        data = _fetch_range(self.url, self.pos, min(self.pos + len(buf), self.size))
        buf[:len(data)] = data
        self.pos += len(data)
        return len(data)


@lru_cache(maxsize=4)
def _members(bundle_url: str) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(io.BufferedReader(_RangeFile(bundle_url), buffer_size=1 << 20)) as zf:
        return zf.infolist()


def _read_member(bundle_url: str, info: zipfile.ZipInfo) -> bytes:
    """One member's contents: fetch its local header + data, decompress, check CRC.
    The local extra field can be longer than the central directory says, so the
    fetch grows until the data fits."""
    slack = 1024
    while True:
        length = LOCAL_HEADER.size + len(info.orig_filename.encode()) + info.compress_size + slack
        raw = _fetch_range(bundle_url, info.header_offset, info.header_offset + length)
        sig, _, _, method, _, _, _, _, _, name_len, extra_len = LOCAL_HEADER.unpack_from(raw)
        if sig != LOCAL_HEADER_SIG:
            raise ValueError(f"bad local header for {info.filename} in {bundle_url}")
        begin = LOCAL_HEADER.size + name_len + extra_len
        if len(raw) >= begin + info.compress_size:
            break
        slack *= 8
    payload = raw[begin:begin + info.compress_size]
    if method == zipfile.ZIP_STORED:
        data = payload
    elif method == zipfile.ZIP_DEFLATED:
        data = zlib.decompress(payload, -15)
    else:
        raise ValueError(f"unsupported compression method {method} for {info.filename} in {bundle_url}")
    if zlib.crc32(data) != info.CRC:
        raise ValueError(f"CRC mismatch for {info.filename} in {bundle_url}")
    return data


# --- Download --------------------------------------------------------------------

def output_path(out: Path, task: dict) -> Path:
    u = urlparse(task["url"])
    base = Path(out) / u.netloc / u.path.lstrip("/")
    return base / "day" / f"{task['day']}.zip" if task["day"] else base / "bundle" / f"{task['time']}.zip"


def _download_bundle(task: dict, tmp: Path, progress: bool = True, on_bytes=None) -> str:
    """`progress` False: no per-file bar (several bundles downloading at once).
    `on_bytes(n)`, if given, is called for every chunk written."""
    resp = _check(_session().get(f"{ARCHIVE_API}/get-file", params={"url": task["url"], "time": task["time"]},
                                 stream=True, timeout=TIMEOUT))
    total = int(resp.headers["Content-Length"]) if "Content-Length" in resp.headers else None
    with tmp.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=task["item"],
                                   position=1, leave=False, disable=not progress) as bar:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            bar.update(len(chunk))
            if on_bytes is not None:
                on_bytes(len(chunk))
    if total is not None and tmp.stat().st_size != total:
        raise OSError(f"got {tmp.stat().st_size} bytes, Content-Length said {total}")
    return f"bundle {_mb(tmp.stat().st_size)}"


def _download_day(task: dict, tmp: Path, workers: int | None) -> str:
    """`workers` None: max(1, min(ceil(files / 10), MAX_WORKERS))."""
    bundle_url = _resolve(task["url"], task["time"])
    prefix = f"{task['day']}-"
    members = [i for i in _members(bundle_url) if Path(i.filename).name.startswith(prefix)]
    if not members:
        raise LookupError(f"bundle time={task['time']} has no member named {prefix}..., nothing written")
    if workers is None:
        workers = max(1, min(math.ceil(len(members) / 10), MAX_WORKERS))
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        with zipfile.ZipFile(tmp, "w") as zf, \
                tqdm(total=len(members), unit="file", desc=task["item"], position=1, leave=False) as bar:
            # pool.map keeps member order (the bundle's own order)
            for info, data in zip(members, pool.map(lambda i: _read_member(bundle_url, i), members)):
                # a ZipInfo carries its own compression (default: stored), so set it here
                zf.writestr(zipfile.ZipInfo(info.filename, info.date_time), data,
                            compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
                bar.update()
    finally:
        # on an error, don't keep fetching the day's remaining members
        pool.shutdown(cancel_futures=True)
    return f"{len(members)} files from bundle time={task['time']} ({workers} workers), {_mb(tmp.stat().st_size)}"


def _run_one(t: dict, out: Path, workers: int | None, overwrite: bool, progress: bool, on_bytes=None) -> tuple:
    """Download one task. Returns ("skip", path, None) | ("ok", path, what was done)
    | ("error", full message, short message); never raises for the task's own failures.
    `on_bytes`: see _download_bundle (whole bundles only)."""
    path = output_path(out, t)
    if path.exists() and not overwrite:
        return "skip", path, None
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    try:
        done = _download_bundle(t, tmp, progress, on_bytes) if t["day"] is None else _download_day(t, tmp, workers)
    except Exception as exc:  # noqa: BLE001 -- one failed task must not stop the rest; reported by run()
        # the archive's own errors carry its response; anything else keeps its traceback
        msg = str(exc) if isinstance(exc, (requests.RequestException, LookupError)) else traceback.format_exc()
        tmp.unlink(missing_ok=True)
        return "error", msg, f"{type(exc).__name__}: {(str(exc).strip().splitlines() or [''])[0]}"
    tmp.replace(path)
    return "ok", path, done


def _parallel(size: int | None) -> int:
    """How many whole bundles of this size download at once (BUNDLE_PARALLEL); 1 if unknown."""
    if size is None:
        return 1
    return next((n for limit, n in BUNDLE_PARALLEL if size < limit), 1)


def run(all_tasks: list[dict], out: Path, workers: int | None = None, overwrite: bool = False,
        sizes: dict[int, int | None] | None = None) -> list[tuple]:
    """Download every task (from tasks()). A task that fails is printed and the
    rest continue; returns [(task, error message), ...] of the failed ones, also
    listed again at the end. `workers` None: see _download_day.

    `sizes` ({id(task): bytes}, from show()) sets how many whole bundles download
    at once, by BUNDLE_PARALLEL: < 10 MB 32, < 100 MB 4, else one at a time. Those
    go first, smallest group first, then the one-at-a-time rest in plan order:
    bundles >= 100 MB or of unknown size, and "YYYY-MM-DD" days (which already
    run their own parallel Range requests). Without `sizes`, all one at a time.

    Progress: the top bar counts bytes against the sizes from `sizes` (ETA from
    the recent speed), with tasks finished / failed; below it, a one-at-a-time
    task's bytes or files."""
    numbered = list(enumerate(all_tasks, 1))
    groups: dict[int, list] = {}
    for i, t in numbered:
        n = _parallel(sizes.get(id(t))) if sizes is not None and t["day"] is None else 1
        groups.setdefault(n, []).append((i, t))

    # The top bar counts bytes: its total is the known sizes of the bundles to download,
    # advanced as each chunk arrives, so its rate and ETA follow the recent download speed.
    # Tasks of unknown size ("YYYY-MM-DD" days, bundles coverage had no size for) join the
    # total only once finished, with their file size, so they don't distort the ETA.
    known = {id(t): sizes[id(t)] for t in all_tasks
             if sizes is not None and t["day"] is None and sizes.get(id(t)) is not None}
    lock = threading.Lock()
    overall = tqdm(total=sum(known.values()), unit="B", unit_scale=True, desc="total", position=0)
    errors, finished = [], 0

    def advance(n: int) -> None:
        with lock:
            overall.update(n)

    def run_task(t: dict, progress: bool) -> tuple:
        """_run_one, plus how many bytes it advanced the top bar by."""
        if id(t) not in known:
            return _run_one(t, out, workers, overwrite, progress), 0
        counted = [0]

        def on_bytes(n: int) -> None:
            counted[0] += n
            advance(n)
        return _run_one(t, out, workers, overwrite, progress, on_bytes), counted[0]

    def report(i: int, t: dict, result: tuple, counted: int) -> None:
        nonlocal finished
        status, a, b = result
        head = f"[{i}/{len(all_tasks)}] {t['url']} {t['item']}"
        with lock:
            if status == "skip":
                tqdm.write(f"{head} | skip, exists: {a}")
                overall.total -= known.get(id(t), 0)
            elif status == "error":
                tqdm.write(f"{head} | error:\n{a}")
                errors.append((t, b))
                overall.total -= known.get(id(t), 0)
                overall.update(-counted)
            else:
                tqdm.write(f"{head} | {b} -> {a}")
                if id(t) not in known:
                    size = a.stat().st_size
                    overall.total += size
                    overall.update(size)
            finished += 1
            overall.set_postfix_str(f"{finished}/{len(all_tasks)} tasks, {len(errors)} failed")

    for n in sorted(groups, reverse=True):  # most parallel (= smallest) first; 1 last
        if n == 1:
            for i, t in groups[n]:
                report(i, t, *run_task(t, progress=True))
            continue
        tqdm.write(f"-- {len(groups[n])} bundle(s), {n} at a time")
        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {pool.submit(run_task, t, False): (i, t) for i, t in groups[n]}
            for fut in as_completed(futures):
                report(*futures[fut], *fut.result())
    overall.close()
    print(f"{len(all_tasks)} request(s), {len(errors)} failed")
    for t, short in errors:
        print(f"failed: {t['url']} {t['item']} (time={t['time']}" + (f" day={t['day']}" if t["day"] else "")
              + f") | {short} (full error above)")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m hkdata.download", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="append one entry to a plan file (created if missing)")
    a.add_argument("plan", type=Path)
    a.add_argument("url", help="a resource's file URL, as in coverage")
    what = a.add_mutually_exclusive_group(required=True)
    what.add_argument("--dates", nargs="+", metavar="ITEM", help="YYYY-MM, YYYYMMDD (bundle timestamp) or YYYY-MM-DD")
    what.add_argument("--range", nargs=2, metavar=("FIRST", "LAST"), help="months, YYYY-MM YYYY-MM (inclusive)")
    a.add_argument("--exclude", nargs="+", metavar="YYYY-MM", help="months to leave out of --range")

    s = sub.add_parser("show", help="list a plan's requests with sizes from coverage")
    s.add_argument("plan", type=Path)
    s.add_argument("--out", type=Path,
                   help="output root as in run: files already there show their local size, not asked about")

    r = sub.add_parser("run", help="show the plan, confirm, then download")
    r.add_argument("plan", type=Path)
    r.add_argument("--out", type=Path, required=True, help="output root directory")
    r.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    r.add_argument("--overwrite", action="store_true", help="download again even if the output file exists")
    r.add_argument("--workers", type=int,
                   help=f"parallel Range requests for a YYYY-MM-DD day; "
                        f"default max(1, min(ceil(files / 10), {MAX_WORKERS}))")

    args = parser.parse_args()

    if args.command == "add":
        if args.exclude and not args.range:
            parser.error("--exclude only goes with --range")
        entry = {"url": args.url}
        if args.dates:
            entry["dates"] = args.dates
        else:
            entry["range"] = args.range
            if args.exclude:
                entry["exclude"] = args.exclude
        entry_tasks = add(args.plan, entry)
        print(f"added to {args.plan}: {json.dumps(entry, ensure_ascii=False)} ({len(entry_tasks)} request(s))")
    elif args.command == "show":
        plan = load(args.plan)
        show(plan, [tasks(e) for e in plan], args.out)
    elif args.command == "run":
        plan = load(args.plan)
        plan_tasks = [tasks(e) for e in plan]
        # with --overwrite every file is downloaded again, so every size is asked for
        sizes = show(plan, plan_tasks, None if args.overwrite else args.out)
        if not args.yes and input("download? [y/N] ").strip().lower() != "y":
            print("not downloaded")
            return
        if run([t for ts in plan_tasks for t in ts], args.out, args.workers, args.overwrite, sizes):
            # the failed tasks have been listed by run()
            sys.exit(1)


if __name__ == "__main__":
    main()
