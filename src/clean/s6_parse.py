"""S6 L1: every holiday of every archived version of the 1823 public-holiday calendar, as written.

    python -m src.clean.s6_parse

Files: data/raw/www.1823.gov.hk/common/ical/en.json/bundle/<YYYYMMDD>.zip, downloaded with
plans/2024_2025_main.json (10 versions, 2019-07 .. 2026-05). Each bundle holds one
`<YYYYMMDD-HHMM>-en.json` member (the archive time of that version) and the bundle's pointer
PDF, which is skipped. Every version is read, not only the months of the manifest: one version
covers three years (docs/raw_data.md, S6).

Output: data/interim/l1/s6/en.parquet, one row per event:
    bundle, member             the zip and the member the row comes from
    position                   0-based place of the event in `vevent`
    CALENDAR                   the calendar's own properties (the same on every row of a file)
    EVENT                      the event's properties, as written; absent = null (`dtstamp`
                               appears in 2025-05)
    dtstart_params, dtend_params   the parameters of the properties in PARAMS
The properties in PARAMS are written as [value, {parameters}]: <p> = value, <p>_params = the
parameters as JSON text (re-serialised by json.dumps). Every other property is a string.

Raises on: JSON with a repeated key, a top level other than {"vcalendar": [one calendar]}, a
calendar or event key not listed below, a property in another form (e.g. parameters on a
property not in PARAMS: then decide whether it needs a column), and a bundle without exactly
one en.json member.
"""

from __future__ import annotations

import json
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq

from src.clean.s1_parse import L1_DIR
from src.config import RAW_DIR

RESOURCE = "en.json"
BUNDLES = RAW_DIR / "www.1823.gov.hk/common/ical/en.json/bundle"
OUT = L1_DIR / "s6" / "en.parquet"
CALENDAR = ["prodid", "version", "calscale", "x-wr-timezone", "x-wr-calname", "x-wr-caldesc"]
EVENT = ["dtstart", "dtend", "dtstamp", "transp", "uid", "summary"]
PARAMS = ["dtstart", "dtend"]  # written as [value, {parameters}]; every other property is a string
COLUMNS = ["bundle", "member", "position", *CALENDAR,
           *[c for p in EVENT for c in ((p, f"{p}_params") if p in PARAMS else (p,))]]
SCHEMA = pa.schema([(c, pa.int32() if c == "position" else pa.string()) for c in COLUMNS])


def _no_repeats(pairs: list[tuple]) -> dict:
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"repeated key {k!r}")
        out[k] = v
    return out


def _property(obj: dict, key: str, where: str) -> tuple:
    """(value,) of a string property, (value, parameters as JSON text) of one in PARAMS; nulls if absent."""
    if key not in obj:
        return (None, None) if key in PARAMS else (None,)
    v = obj[key]
    if key in PARAMS:
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], dict):
            return v[0], json.dumps(v[1], ensure_ascii=False)
        raise ValueError(f"{where}: {key} = {v!r} is not [value, {{parameters}}]")
    if isinstance(v, str):
        return (v,)
    raise ValueError(f"{where}: {key} = {v!r} is not a string; only {', '.join(PARAMS)} may have parameters")


def parse(data: bytes, where: str) -> list[tuple]:
    """(position, *CALENDAR, *event values) of every event in one en.json file."""
    try:
        doc = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_no_repeats)
    except ValueError as e:
        raise ValueError(f"{where}: {e}") from e
    if not (isinstance(doc, dict) and list(doc) == ["vcalendar"] and isinstance(doc["vcalendar"], list)
            and len(doc["vcalendar"]) == 1 and isinstance(doc["vcalendar"][0], dict)):
        raise ValueError(f'{where}: top level is not {{"vcalendar": [one calendar]}}')
    cal = doc["vcalendar"][0]
    if set(cal) - {*CALENDAR, "vevent"}:
        raise ValueError(f"{where}: unknown calendar keys {sorted(set(cal) - {*CALENDAR, 'vevent'})}")
    if not isinstance(cal.get("vevent"), list):
        raise ValueError(f"{where}: vevent is not a list")
    head = [_property(cal, k, where)[0] for k in CALENDAR]
    rows = []
    for pos, ev in enumerate(cal["vevent"]):
        if not isinstance(ev, dict):
            raise ValueError(f"{where}: event {pos} is not an object")
        if set(ev) - set(EVENT):
            raise ValueError(f"{where}: event {pos} has unknown keys {sorted(set(ev) - set(EVENT))}")
        rows.append((pos, *head, *[x for p in EVENT for x in _property(ev, p, f"{where} event {pos}")]))
    return rows


def build() -> None:
    rows = []
    for bundle in sorted(BUNDLES.glob("*.zip")):
        z = zipfile.ZipFile(bundle)
        members = [i for i in z.infolist() if i.filename.endswith(f"-{RESOURCE}")]
        if len(members) != 1:
            raise ValueError(f"{bundle.name}: {len(members)} members ending in -{RESOURCE}")
        for i in z.infolist():
            if i is not members[0] and not i.is_dir():
                print(f"skipped {bundle.name} {i.filename.rsplit('/', 1)[-1]}: not {RESOURCE}")
        m = members[0]
        events = parse(z.read(m), f"{bundle.name} {m.filename}")
        rows += [(bundle.name, m.filename, *e) for e in events]
        print(f"{bundle.name} {m.filename.rsplit('/', 1)[-1]}: {len(events)} events")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({c: [r[k] for r in rows] for k, c in enumerate(COLUMNS)}, schema=SCHEMA)
    pq.write_table(table, OUT.with_suffix(".parquet.part"), compression="zstd")
    OUT.with_suffix(".parquet.part").replace(OUT)
    print(f"s6: {len(rows)} event rows -> {OUT}")


if __name__ == "__main__":
    build()
