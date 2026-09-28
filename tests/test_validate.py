from datetime import date, datetime, timedelta

import pandas as pd

from src.parse import weather
from src.storage import file_version, read_meta, write_parquet
from src.validate import Checks, check_rainfall_day, check_traffic_day, check_traffic_file, profile

DAY = date(2025, 8, 5)


def _lanes(times, lanes=("Fast Lane",), valid="Y"):
    rows = [(t, "AID01101", lane, 60, 5, 3, 1.0, valid) for t in times for lane in lanes]
    df = pd.DataFrame(rows, columns=["time", "detector_id", "lane", "speed", "occupancy", "volume", "sd", "valid"])
    for col in ("detector_id", "lane", "valid"):
        df[col] = df[col].astype("category")
    for col in ("speed", "occupancy", "volume"):
        df[col] = df[col].astype("Int16")
    return df


def _levels(checks):
    return {c.name: c.level for c in checks}


def test_storage_roundtrip(tmp_path):
    path = tmp_path / "x.parquet"
    write_parquet(pd.DataFrame({"a": [1, 2]}), path, {"table": "t", "version": 3})
    assert read_meta(path) == {"table": "t", "version": 3}
    assert file_version(path) == 3
    pd.DataFrame({"a": [1]}).to_parquet(tmp_path / "old.parquet")   # written before versioning
    assert file_version(tmp_path / "old.parquet") is None
    assert file_version(tmp_path / "missing.parquet") is None


def test_file_check_catches_misdated_midnight_rows():
    ok = [datetime(2025, 8, 4, 23, 55), datetime(2025, 8, 5, 8, 0)]      # late previous-day rows are expected
    c = Checks()
    check_traffic_file(c, DAY, _lanes(ok))
    assert set(_levels(c).values()) == {"OK"}

    c = Checks()
    check_traffic_file(c, DAY, _lanes(ok + [datetime(2025, 8, 4, 0, 0)]))  # 00:00 with the previous day's date
    assert _levels(c)["misdated midnight rows (previous day 00:xx)"] == "FAIL"


def test_day_checks_flag_duplicates_and_unknown_values():
    times = [datetime(2025, 8, 5) + timedelta(seconds=30 * i) for i in range(2880)]
    good = _lanes(times)
    c = Checks()
    check_traffic_day(c, DAY, good, {"AID01101"}, next_day_present=True)
    levels = _levels(c)
    assert levels["duplicate keys (time, detector_id, lane)"] == "OK"
    assert levels["share of 30-s periods present"] == "OK"
    assert "FAIL" not in levels.values() and "WARN" not in levels.values()

    bad = pd.concat([good, good.head(1)], ignore_index=True)
    bad["valid"] = bad["valid"].cat.add_categories("X")
    bad.loc[0, "valid"] = "X"
    c = Checks()
    check_traffic_day(c, DAY, bad, {"OTHER"}, next_day_present=False)
    levels = _levels(c)
    assert levels["duplicate keys (time, detector_id, lane)"] == "FAIL"
    assert levels["unknown valid values"] == "FAIL"
    assert levels["detectors missing from the location table"] == "WARN"
    assert levels["next day processed"] == "WARN"


def test_rainfall_checks():
    ends = [datetime(2025, 8, 5, h, 45) for h in range(24)]
    rows = [{"bulletin_time": e + timedelta(minutes=17), "period_start": e - timedelta(hours=1), "period_end": e,
             "district": d, "rain_min_mm": 0.0, "rain_max_mm": 0.0, "listed": False, "section_present": False}
            for e in ends for d in weather.DISTRICTS]
    df = pd.DataFrame(rows)
    c = Checks()
    check_rainfall_day(c, DAY, df)
    assert "FAIL" not in _levels(c).values()

    c = Checks()
    check_rainfall_day(c, DAY, df.iloc[1:])      # one district missing in one hour
    assert _levels(c)["hours without exactly 18 districts"] == "FAIL"


def test_profile_lists_na_unique_and_top_values():
    md = profile(pd.DataFrame({"x": [1, 1, None], "y": ["a", "b", "b"]}))
    assert "| x | float64 | 1 | 33.3% | 1 |" in md
    assert "`b` (2)" in md
