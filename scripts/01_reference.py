"""Download the small, static reference tables into data/reference/ (committed).

- detectors.csv            TD detector locations (ID, district, road, lat/lon)
- rainstorm_warnings.csv   HKO Amber/Red/Black signal periods since 1998
- public_holidays.csv      HK general holidays 2021-2027
- daily_rainfall_HKO.csv   Daily rainfall at HKO headquarters (full history)

Usage:  python scripts/01_reference.py
"""
import io
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from hkrt.archive import _get  # noqa: E402
from hkrt.parse import parse_holidays_json, parse_rainstorm_db  # noqa: E402

OUT = ROOT / "data" / "reference"
OUT.mkdir(parents=True, exist_ok=True)

DETECTORS = "https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv"
RSTORM = "https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat"
HOLIDAYS = "https://www.1823.gov.hk/common/ical/en.json"
DAILY_RF = "https://data.weather.gov.hk/weatherAPI/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv"


def main():
    # Detector table: kept as published (trailing spaces, district spellings)
    # so that the cleaning step can document what it fixes.
    det = pd.read_csv(io.BytesIO(_get(DETECTORS)), encoding="utf-8-sig")
    det.to_csv(OUT / "detectors.csv", index=False)
    print("detectors", det.shape)

    w = parse_rainstorm_db(_get(RSTORM))
    w.to_csv(OUT / "rainstorm_warnings.csv", index=False)
    print("warnings", w.shape, w.start.min(), "->", w.end.max())

    # 1823 calendar only covers the current year onward; fill earlier years
    # from the `holidays` package (python -m pip install holidays).
    hol = parse_holidays_json(_get(HOLIDAYS))
    hol["source"] = "1823.gov.hk"
    try:
        import holidays

        first = min(hol.date).year
        extra = [(d, n) for y in range(2021, first) for d, n in holidays.HK(years=y, categories=("public", "optional"), language="en_HK").items()]
        hol = pd.concat([pd.DataFrame(extra, columns=["date", "name"]).assign(source="python-holidays"), hol])
    except ImportError:
        print("! `holidays` not installed: only", min(hol.date), "onward")
    hol.sort_values("date").to_csv(OUT / "public_holidays.csv", index=False)
    print("holidays", len(hol))

    (OUT / "daily_rainfall_HKO.csv").write_bytes(_get(DAILY_RF))
    print("daily rainfall saved")


if __name__ == "__main__":
    main()
