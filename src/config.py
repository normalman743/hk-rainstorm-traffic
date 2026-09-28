"""Project-wide paths and source URLs."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

# Resources archived by the DATA.GOV.HK Historical Archive API.
# Keys are the short names used on the command line.
ARCHIVED_SOURCES = {
    # TD raw detector data: speed / volume / occupancy per lane, 30 s periods.
    "traffic": "https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml",
    # TD processed speed on road-network segments (2 min). Optional.
    "segments": "https://resource.data.one.gov.hk/td/traffic-detectors/irnAvgSpeed-all.xml",
    # HKO current weather report: past-hour rainfall range per district (hourly).
    "weather": "https://rss.weather.gov.hk/rss/CurrentWeather.xml",
}

# Static files downloaded as-is (always the latest version).
STATIC_SOURCES = {
    "td/traffic_speed_volume_occ_info.csv":
        "https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv",
    "td/speed_segments_info.csv":
        "https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv",
    "hko/daily_HKO_RF_ALL.csv":
        "https://data.weather.gov.hk/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv",
}

# Raw tab-separated files behind the HKO warning database web pages
# (https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml and warndb1.shtml).
RAINSTORM_DB_URL = "https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat"
TC_SIGNAL_DB_URL = "https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat"
