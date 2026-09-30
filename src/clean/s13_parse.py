"""S13 L1: every <message> of every distinct Special Traffic News file, as written.

    python -m src.clean.s13_parse

Needs data/interim/manifest/trafficnews.xml.csv (python -m src.clean.manifest ...).
One file per group of identical files is read; members that are not `*-trafficnews.xml`
(the bundle's data-dictionary.pdf pointer) are skipped and listed. The XSD allows a list of
messages; in 2024-05, 2025-07 and 2025-08 every file held exactly one (docs/raw_data.md, S13).

Output: data/interim/l1/s13/<bundle YYYYMM>.parquet, one row per <message>:
    bundle, index      the zip member (see the manifest)
    position           0-based place of the message in the file's <list>
    INCIDENT_NUMBER .. LONGITUDE   the 23 elements of the XSD (schema/20210608), text as written
A file with an empty <list> has no rows; the manifest still lists it.
Every value is a string; absent element = null, empty element = "".

Raises on a root other than <list>, a child of <list> other than <message>, and an element
in <message> that is not in the XSD or occurs twice.

Bare "&": a few files are not well-formed XML because a text has an unescaped "&"
("Kowloonbay International Trade & Exhibition Centre", 5 files in 2024-05). Before parsing,
every "&" that does not start an entity or character reference (`&name;`, `&#123;`, `&#x1F;`)
is written as "&amp;", so the value is the text as written. Any other error still raises.
The files where this happened are listed in data/interim/checks/s13_bare_ampersands.csv.
"""

from __future__ import annotations

import csv
import re
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
from lxml import etree

from src.clean.manifest import OUT_DIR as MANIFEST_DIR
from src.clean.s1_parse import _children, _text
from src.config import INTERIM_DIR, RAW_DIR

RESOURCE = "trafficnews.xml"
BUNDLES = RAW_DIR / "www.td.gov.hk/en/special_news/trafficnews.xml/bundle"
OUT_DIR = INTERIM_DIR / "l1" / "s13"
NOTES = INTERIM_DIR / "checks" / "s13_bare_ampersands.csv"
BARE_AMP = re.compile(rb"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")

FIELDS = ["INCIDENT_NUMBER", "INCIDENT_HEADING_EN", "INCIDENT_HEADING_CN", "INCIDENT_DETAIL_EN",
          "INCIDENT_DETAIL_CN", "LOCATION_EN", "LOCATION_CN", "DISTRICT_EN", "DISTRICT_CN",
          "DIRECTION_EN", "DIRECTION_CN", "ANNOUNCEMENT_DATE", "INCIDENT_STATUS_EN",
          "INCIDENT_STATUS_CN", "NEAR_LANDMARK_EN", "NEAR_LANDMARK_CN", "BETWEEN_LANDMARK_EN",
          "BETWEEN_LANDMARK_CN", "ID", "CONTENT_EN", "CONTENT_CN", "LATITUDE", "LONGITUDE"]
COLUMNS = ["bundle", "index", "position", *FIELDS]
SCHEMA = pa.schema([(c, pa.int32() if c in ("index", "position") else pa.string()) for c in COLUMNS])


def parse(data: bytes, where: str) -> tuple[list[tuple], int]:
    """(position, *FIELDS) of every message in one S13 file, and the number of bare "&"."""
    data, n_amp = BARE_AMP.subn(b"&amp;", data)
    try:
        root = etree.fromstring(data)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"{where}: {e}") from e
    if root.tag != "list":
        raise ValueError(f"{where}: root <{root.tag}>")
    rows = []
    for pos, msg in enumerate(root):
        if msg.tag != "message":
            raise ValueError(f"{where}: unexpected <{msg.tag}> in <list>")
        m = _children(msg, set(FIELDS), where)
        rows.append((pos, *(_text(m, f) for f in FIELDS)))
    return rows, n_amp


def build() -> None:
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        firsts = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    notes = []
    for bundle in sorted({r["bundle"] for r in firsts}):
        z = zipfile.ZipFile(BUNDLES / bundle)
        infos = z.infolist()
        rows, n_files, n_empty = [], 0, 0
        for r in (r for r in firsts if r["bundle"] == bundle):
            i = int(r["index"])
            if not r["member"].endswith(f"-{RESOURCE}"):
                print(f"skipped {bundle}:{i} {r['member']}: not {RESOURCE}")
                continue
            msgs, n_amp = parse(z.read(infos[i]), f"{bundle}:{i} {r['member']}")
            if n_amp:
                notes.append((bundle, i, r["member"], n_amp))
            rows += [(bundle, i, *m) for m in msgs]
            n_files += 1
            n_empty += not msgs
        out = OUT_DIR / f"{bundle[:6]}.parquet"
        table = pa.table({c: [row[k] for row in rows] for k, c in enumerate(COLUMNS)}, schema=SCHEMA)
        pq.write_table(table, out.with_suffix(".parquet.part"), compression="zstd")
        out.with_suffix(".parquet.part").replace(out)
        print(f"{bundle}: {n_files} distinct files ({n_empty} with no message), {len(rows)} message rows")
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    with NOTES.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["bundle", "index", "member", "n_bare_ampersands"])
        w.writerows(notes)
    print(f"{len(notes)} files with a bare '&': {NOTES}")


if __name__ == "__main__":
    build()
