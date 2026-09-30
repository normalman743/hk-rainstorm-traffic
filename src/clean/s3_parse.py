"""S3 L1: every Current Weather Report bulletin, and its district rainfall rows, as written.

    python -m src.clean.s3_parse

Needs data/interim/manifest/CurrentWeather.xml.csv (python -m src.clean.manifest ...).
One file per group of identical files is read; members that are not `*-CurrentWeather.xml`
(the bundle's data-dictionary.pdf pointer) are skipped and listed.

Output, one Parquet file per bundle (all values strings, as written; absent = null, empty = ""):
- data/interim/l1/s3_bulletins/<YYYYMM>.parquet, one row per file (= per <item>):
      bundle, index, author, guid, pubDate, title, category, link, description
  `description` is the whole CDATA text. The <channel> metadata around the item (title, link,
  copyright, image, ...) is not kept; its element list is checked.
- data/interim/l1/s3_rain/<YYYYMM>.parquet, one row per district in the rainfall table:
      bundle, index, period, district, low, high
  from the sentence "Between <period>, [lightning was detected <where>. The|the] rainfall
  recorded in various regions were:" and the table after it, whose rows are
  `<District> <low> to <high> mm` or `<District> <low> mm` (then `high` is null).
  A bulletin without that sentence has no rain rows (no district had rain, see docs/raw_data.md).

Raises on: a root or channel structure other than the one below, not exactly one <item>, an
unknown or repeated element in <item>, "rainfall recorded" more than once, a rainfall sentence
or table row in any other form, or anything left in the table besides its rows.
    rss > channel > title, link, description, language, copyright, image, atom:link, item
    item > author, guid, pubDate, title, category, link, description
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

RESOURCE = "CurrentWeather.xml"
BUNDLES = RAW_DIR / "rss.weather.gov.hk/rss/CurrentWeather.xml/bundle"
OUT_BULLETINS = INTERIM_DIR / "l1" / "s3_bulletins"
OUT_RAIN = INTERIM_DIR / "l1" / "s3_rain"

CHANNEL = ["title", "link", "description", "language", "copyright", "image",
           "{http://www.w3.org/2005/Atom}link", "item"]
ITEM = ["author", "guid", "pubDate", "title", "category", "link", "description"]
BULLETIN_COLUMNS = ["bundle", "index", *ITEM]
RAIN_COLUMNS = ["bundle", "index", "period", "district", "low", "high"]

RAIN = re.compile(
    r"Between (?P<period>[^,<>]+), "
    r"(?:the rainfall|lightning was detected (?:over all regions|within [A-Za-z ,]+)\. The rainfall)"
    r" recorded in various regions were:<br/><br/>\s*"
    r'<table border="0" cellspacing="0" cellpadding="0">(?P<rows>.*?)</table>', re.S)
ROW = re.compile(r'<tr><td>(?P<district>[^<]*)</td><td width="100" align="right">'
                 r"(?P<low>\d+)(?: to (?P<high>\d+))?&nbsp;mm[;.]</td></tr>")


def _schema(columns: list[str]) -> pa.Schema:
    return pa.schema([(c, pa.int32() if c == "index" else pa.string()) for c in columns])


def rain_rows(description: str, where: str) -> list[tuple]:
    """(period, district, low, high) of the rainfall table; [] if the bulletin has none."""
    n = description.count("rainfall recorded")
    if n == 0:
        return []
    if n > 1:
        raise ValueError(f"{where}: 'rainfall recorded' {n} times")
    m = RAIN.search(description)
    if m is None:
        i = description.index("rainfall recorded")
        raise ValueError(f"{where}: rainfall sentence in another form: {description[i - 200:i + 200]!r}")
    rows = [(m["period"], r["district"], r["low"], r["high"]) for r in ROW.finditer(m["rows"])]
    rest = ROW.sub("", m["rows"])
    if rest.strip():
        raise ValueError(f"{where}: unexpected text in the rainfall table: {rest.strip()[:300]!r}")
    return rows


def parse(data: bytes, where: str) -> tuple[tuple, list[tuple]]:
    """(item fields, rain rows) of one S3 file."""
    root = etree.fromstring(data)
    if root.tag != "rss" or [c.tag for c in root] != ["channel"]:
        raise ValueError(f"{where}: root <{root.tag}> with {[c.tag for c in root]}")
    tags = [c.tag for c in root[0]]
    if tags != CHANNEL:
        raise ValueError(f"{where}: <channel> holds {tags}")
    item = _children(root[0].find("item"), set(ITEM), where)
    fields = tuple(_text(item, t) for t in ITEM)
    description = fields[ITEM.index("description")]
    return fields, rain_rows(description, where) if description else []


def build() -> None:
    with (MANIFEST_DIR / f"{RESOURCE}.csv").open() as f:
        firsts = [r for r in csv.DictReader(f) if r["group"] == f"{r['bundle']}:{r['index']}"]
    OUT_BULLETINS.mkdir(parents=True, exist_ok=True)
    OUT_RAIN.mkdir(parents=True, exist_ok=True)
    for bundle in sorted({r["bundle"] for r in firsts}):
        z = zipfile.ZipFile(BUNDLES / bundle)
        infos = z.infolist()
        bulletins, rain = [], []
        for r in (r for r in firsts if r["bundle"] == bundle):
            i = int(r["index"])
            if not r["member"].endswith(f"-{RESOURCE}"):
                print(f"skipped {bundle}:{i} {r['member']}: not {RESOURCE}")
                continue
            fields, rows = parse(z.read(infos[i]), f"{bundle}:{i} {r['member']}")
            bulletins.append((bundle, i, *fields))
            rain += [(bundle, i, *row) for row in rows]
        for out_dir, columns, rows in ((OUT_BULLETINS, BULLETIN_COLUMNS, bulletins),
                                       (OUT_RAIN, RAIN_COLUMNS, rain)):
            out = out_dir / f"{bundle[:6]}.parquet"
            table = pa.table({c: [row[k] for row in rows] for k, c in enumerate(columns)},
                             schema=_schema(columns))
            pq.write_table(table, out.with_suffix(".parquet.part"), compression="zstd")
            out.with_suffix(".parquet.part").replace(out)
        print(f"{bundle}: {len(bulletins)} bulletins, {len(rain)} rain rows "
              f"({len({x[1] for x in rain})} bulletins with rain)")


if __name__ == "__main__":
    build()
