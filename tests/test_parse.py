import io
import zipfile
from datetime import date, datetime

import pandas as pd
import pytest

from src.download.holidays import parse_holidays
from src.parse import traffic, weather

XML_2025 = b"""<?xml version="1.0" encoding="utf-8"?><raw_speed_volume_list><date>2025-08-05</date><periods>
<period><period_from>07:53:00</period_from><period_to>07:53:30</period_to><detectors>
<detector><detector_id>AID01101</detector_id><direction>South East</direction><lanes>
<lane><lane_id>Fast Lane</lane_id><speed>70</speed><occupancy>0</occupancy><volume>0</volume><s.d.>0</s.d.><valid>Y</valid></lane>
<lane><lane_id>Middle Lane</lane_id><speed>43</speed><occupancy>1</occupancy><volume>2</volume><s.d.>5.7</s.d.><valid>N</valid></lane>
</lanes></detector>
<detector><detector_id>AID01102</detector_id><direction>North East</direction><lanes>
<lane><lane_id>Slow Lane</lane_id><speed>46</speed><occupancy>-1</occupancy><volume>2</volume><s.d.>14.1</s.d.><valid>Y</valid></lane>
</lanes></detector></detectors></period>
<period><period_from>07:53:30</period_from><period_to>07:54:00</period_to><detectors>
<detector><detector_id>AID01101</detector_id><direction>South East</direction><lanes>
<lane><lane_id>Fast Lane</lane_id><speed>65</speed><occupancy>3</occupancy><volume>1</volume><s.d.>0</s.d.><valid>Y</valid></lane>
</lanes></detector></detectors></period></periods></raw_speed_volume_list>"""

# Pre-Nov-2021 schema: no <s.d.> element.
XML_2021 = (b"<raw_speed_volume_list><date>2021-07-01</date><periods><period><period_from>09:23:00</period_from>"
            b"<period_to>09:23:30</period_to><detectors><detector><detector_id>AID08101</detector_id>"
            b"<direction>South West</direction><lanes><lane><lane_id>Slow Lane</lane_id><speed>75</speed>"
            b"<occupancy>0</occupancy><volume>1</volume><valid>Y</valid></lane></lanes></detector>"
            b"</detectors></period></periods></raw_speed_volume_list>")


def _bulletin(updated: str, body: str) -> bytes:
    return (f"<rss><channel><item><title>Bulletin updated at {updated}</title><description><![CDATA["
            f"<p>At 8 a.m. at the Hong Kong Observatory :<br/>Air temperature : 25 degrees Celsius<br/>"
            f"{body} ]]></description></item></channel></rss>").encode()


def test_parse_traffic_snapshot():
    df = traffic.parse_snapshots([XML_2025])
    assert list(df.columns) == traffic.COLUMNS
    assert len(df) == 4
    first = df.iloc[1]
    assert first["time"] == pd.Timestamp("2025-08-05 07:53:00")
    assert (first["detector_id"], first["lane"], first["speed"], first["volume"], first["valid"]) == \
        ("AID01101", "Middle Lane", 43, 2, "N")
    assert first["sd"] == pytest.approx(5.7)
    assert df.iloc[2]["occupancy"] == -1  # kept as published; cleaned later
    assert df.iloc[3]["time"] == pd.Timestamp("2025-08-05 07:53:30")


def test_parse_traffic_without_sd():
    df = traffic.parse_snapshots([XML_2021])
    assert len(df) == 1 and df["sd"].isna().all() and df.iloc[0]["speed"] == 75


def test_parse_traffic_day_zip_drops_overlap(tmp_path):
    path = tmp_path / "20250805.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("20250805-0801-rawSpeedVol-all.xml", XML_2025)
        zf.writestr("20250805-0802-rawSpeedVol-all.xml", XML_2025)  # overlapping snapshot
    df, stats = traffic.parse_day_zip(path)
    assert stats["n_rows_raw"] == 8 and stats["n_rows"] == 4 and stats["n_periods_redated"] == 0 and stats["n_truncated_files"] == 0
    assert stats["n_periods"] == 2 and stats["n_detectors"] == 2 and stats["has_sd"]


def test_truncated_file_keeps_complete_readings(tmp_path):
    cut = XML_2025[:XML_2025.index(b"<lane><lane_id>Slow Lane")] + b"<lane><lane_id>Slow La"
    path = tmp_path / "20250805.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("20250805-0801-rawSpeedVol-all.xml", cut)
        zf.writestr("20250805-0802-rawSpeedVol-all.xml", XML_2021.replace(b"2021-07-01", b"2025-08-05"))
    df, stats = traffic.parse_day_zip(path)
    assert stats["n_truncated_files"] == 1
    assert set(df["detector_id"]) == {"AID01101", "AID08101"}  # the cut lane is dropped, earlier ones kept


def test_midnight_period_is_redated():
    xml = XML_2025.replace(b"<date>2025-08-05</date>", b"<date>2025-08-04</date>") \
                  .replace(b"07:53:00", b"00:00:00").replace(b"07:53:30", b"00:00:30")
    fixed = traffic.parse_snapshots([xml], [datetime(2025, 8, 5, 0, 8)])
    assert fixed["time"].min() == pd.Timestamp("2025-08-05 00:00:00")
    # a normal late-evening period archived just after midnight stays on its day
    late = XML_2025.replace(b"<date>2025-08-05</date>", b"<date>2025-08-04</date>").replace(b"07:53:00", b"23:54:00")
    kept = traffic.parse_snapshots([late], [datetime(2025, 8, 5, 0, 2)])
    assert pd.Timestamp("2025-08-04 23:54:00") in set(kept["time"])
    assert traffic.archive_time("x/20250805-0801-rawSpeedVol-all.xml") == datetime(2025, 8, 5, 8, 1)


def test_parse_bulletin_rainfall():
    rows = weather.parse_bulletin(_bulletin(
        "08:02 HKT 05/08/2025",
        "Between 6:45 and 7:45 a.m., lightning was detected over all regions. The rainfall recorded in "
        "various regions were: Southern District 27 to 60&nbsp;mm; Wan Chai 3 mm; "
        "Central &amp; Western District 20 to 28 mm. The air temperatures at other places were:"))
    by = {r["district"]: r for r in rows}
    assert len(rows) == 18
    assert by["Southern"]["period_end"] == datetime(2025, 8, 5, 7, 45)
    assert by["Southern"]["period_start"] == datetime(2025, 8, 5, 6, 45)
    assert (by["Southern"]["rain_min_mm"], by["Southern"]["rain_max_mm"]) == (27, 60)
    assert (by["Wan Chai"]["rain_min_mm"], by["Wan Chai"]["rain_max_mm"]) == (3, 3)
    assert by["Central & Western"]["listed"]
    assert not by["Sha Tin"]["listed"] and by["Sha Tin"]["rain_max_mm"] == 0
    assert all(r["section_present"] for r in rows)


def test_parse_bulletin_across_midnight():
    rows = weather.parse_bulletin(_bulletin(
        "01:46 HKT 08/09/2023",
        "Between 11:45 p.m. and 0:45 a.m., the rainfall recorded in various regions were: Wong Tai Sin 82 to 99 mm. "))
    assert rows[0]["period_end"] == datetime(2023, 9, 8, 0, 45)
    assert rows[0]["period_start"] == datetime(2023, 9, 7, 23, 45)


def test_parse_bulletin_noon_and_previous_day():
    rows = weather.parse_bulletin(_bulletin(
        "13:02 HKT 08/09/2023",
        "Between 11:45 a.m. and 12:45 p.m., the rainfall recorded in various regions were: Sha Tin 3 to 5 mm. "))
    assert rows[0]["period_end"] == datetime(2023, 9, 8, 12, 45)
    rows = weather.parse_bulletin(_bulletin(
        "00:02 HKT 08/09/2023",
        "Between 10:45 and 11:45 p.m., the rainfall recorded in various regions were: Sha Tin 3 to 5 mm. "))
    assert rows[0]["period_end"] == datetime(2023, 9, 7, 23, 45)


def test_parse_bulletin_without_rain_section():
    rows = weather.parse_bulletin(_bulletin("19:02 HKT 08/09/2023", "The air temperatures at other places were:"))
    assert all(not r["section_present"] and r["rain_max_mm"] == 0 for r in rows)
    assert rows[0]["period_end"] == datetime(2023, 9, 8, 18, 45)


def test_parse_bulletin_rejects_unknown_district():
    with pytest.raises(ValueError, match="unknown district"):
        weather.parse_bulletin(_bulletin(
            "08:02 HKT 05/08/2025",
            "Between 6:45 and 7:45 a.m., the rainfall recorded in various regions were: Atlantis 5 mm. "))


@pytest.mark.parametrize("raw, expected", [
    ("Southern District", "Southern"), ("Central & Western District", "Central & Western"),
    ("Central and Western", "Central & Western"), ("Sha Tin", "Sha Tin"), ("North District", "North"),
])
def test_normalise_district(raw, expected):
    assert weather.normalise_district(raw) == expected


def test_parse_holidays():
    raw = ('﻿{"vcalendar":[{"vevent":[{"dtstart":["20250101",{"value":"DATE"}],'
           '"dtend":["20250102",{"value":"DATE"}],"summary":"The first day of January"}]}]}').encode()
    assert parse_holidays(raw) == {date(2025, 1, 1): "The first day of January"}
