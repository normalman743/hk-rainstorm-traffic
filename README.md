# hk-rainstorm-traffic

Which Hong Kong roads are most sensitive to rainstorms? Integrating HKO rainfall and warning data with Transport Department traffic detectors to study how preprocessing and feature engineering affect congestion prediction.

> Course project. The focus is **data preprocessing and integration**: every
> major cleaning / aggregation / matching decision is treated as an experimental
> variable, and we measure how it changes the downstream results.
> See [`PROPOSAL.md`](PROPOSAL.md) for the full research plan and
> [`docs/raw_data.md`](docs/raw_data.md) (every raw source and field),
> [`docs/processing.md`](docs/processing.md) (what each pipeline step does) and
> [`docs/database_description.md`](docs/database_description.md) (processed tables).
> Chinese versions: [`README.zh.md`](README.zh.md), [`docs/raw_data.zh.md`](docs/raw_data.zh.md),
> [`docs/processing.zh.md`](docs/processing.zh.md), [`docs/database_description.zh.md`](docs/database_description.zh.md).

## Status (2026-09-29)

- **Data: complete.** Every source the analysis needs, plus optional extensions, is downloaded
  for 2024-01 .. 2025-12 (~53 GB of raw monthly bundles), each with its official data dictionary.
  Inventory: [`docs/raw_data.md`](docs/raw_data.md#inventory-on-disk-2026-09-29).
- **Next: processing.** Writing the scripts that turn the raw bundles into the analysis tables.
  The [Pipeline](#pipeline) section below still describes the earlier day-by-day pipeline.

## Research questions

1. **Sensitivity:** Which road segments show the largest speed drop / occupancy rise during rainstorms, after controlling for time of day and day of week?
2. **Prediction:** Can road attributes plus rainfall features predict congestion during rainstorm periods better than a time-only baseline?
3. **Preprocessing impact:** How much do choices such as outlier handling, aggregation window, rainfall-to-road matching and warning encoding change the answers to Q1 and Q2?

## Data sources

All data is free Hong Kong government open data. Nothing large is committed: `data/` is
git-ignored and re-created by the download commands below. Full inventory, file locations,
fields and quirks: [`docs/raw_data.md`](docs/raw_data.md).

| ID | Data | Provider | Resolution | On disk | Tier |
|----|------|----------|------------|---------|------|
| S1 | [Traffic detector readings](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads) (speed, volume, occupancy) | TD | 30 s × lane × detector (~790) | 2024-01 .. 2025-12 | main |
| S2 | Traffic detector locations | TD | per detector, 8 versions | 2021-08 .. 2026-04 | main |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report): past-hour rainfall per district | HKO | hourly × 18 districts | 2024-01 .. 2025-12 | main |
| S4, S5 | [Rainstorm](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) / [tropical cyclone](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml) warning signals | HKO | per signal | since 1998 / 1946 | main |
| S6 | [Public holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) | 1823 | per day | 2018 .. 2027 | main |
| S8 | [Daily total rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) at HKO HQ | HKO | daily | since 1884 | main |
| S9, S10 | [Smart-lamppost detectors](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts): readings, locations | TD | 30 s × lane × detector (17) | 2024-01 .. 2025-12 | optional |
| S11, N1 | Segment speeds (TD processed), segment → route | TD | ~1 min × segment (~4,400) | 2024-01 .. 2025-12 | optional |
| S12 | [Road network (2nd gen.)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2) geometry | TD | per version (34) | 2024-01 .. 2025-12 | optional |
| S13 | [Special traffic news](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2) (incidents, closures) | TD | per message update | 2024-01 .. 2025-12 | optional |
| S7 | [Gridded rainfall nowcast](https://data.gov.hk/en-data/dataset/hk-hko-rss-gridded-rainfall-nowcast-in-hong-kong) (radar **forecast**) | HKO | 15 min × ~2 km grid | 2024-01 .. 2025-12 | optional |

Station-level hourly rainfall (`hourlyRainfall.php`) is **not** in the historical
archive, so rainfall is matched to roads by district.

### Downloading the data

```bash
pip install -r requirements.txt

# DATA.GOV.HK Historical Archive, driven by plans (skips files already there; shows sizes and asks first)
python -m hkdata.download run hkdata/plans/2024_2025_main.json --out data/raw          # 25.2 GB
python -m hkdata.download run hkdata/plans/2024_2025_optional.json --out data/raw      # 28.1 GB
python -m hkdata.download run hkdata/plans/road_network_2024_2025.json --out data/raw  #  0.6 GB

# Sources not in the archive, or versions the plans leave out (seconds)
python -m src.download warnings         # S4, S5
python -m src.download static           # S8, S2 live copy
python -m src.download static-history   # S2, N1 older versions
python -m src.download holidays         # S6
```

`hkdata` is a general DATA.GOV.HK library in this repository: `python -m hkdata.discover`
finds datasets and shows what the archive holds; `python -m hkdata.download` turns a plan
(which resources, which months) into archive requests. See the module docstrings.

### How the archive is accessed

Historical versions of DATA.GOV.HK resources come from the
[Historical Archive API](https://data.gov.hk/en/help/api-spec):

```bash
# List versions of a file for a date range: returns "timestamps" and "data-files" (monthly ZIP bundles)
curl -G "https://app.data.gov.hk/v1/historical-archive/list-file-versions" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "start=20250805&end=20250805"

# One snapshot (time = YYYYMMDD-HHMM) or a whole bundle (time = the bundle's YYYYMMDD timestamp)
curl -L -G "https://app.data.gov.hk/v1/historical-archive/get-file" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "time=20250805-0801" -o rawSpeedVol-20250805-0801.xml
```

A monthly traffic bundle is ~1 GB, and one day's XML unzipped is ~670 MB. The
plans keep whole monthly bundles under `data/raw/<url host>/<url path>/bundle/`, next to each
resource's data dictionaries (`data-dictionary/`). `hkdata.download` can also take single
days out of a bundle with HTTP range requests.

## Pipeline

> **Being rewritten.** This section describes the earlier pipeline, which downloads
> selected days itself and deletes the ZIPs after parsing. The new one will read the
> monthly bundles already in `data/raw/` (see [Status](#status-2026-09-29)).

Four steps. Every step skips work that is already done **with the current code
version** and rebuilds anything older, so any step can be re-run after an interruption
or a code change. Progress bars show days completed and files downloaded. After step 3,
`src.validate` checks all processed days and profiles every table (NA, unique values,
most frequent values); see [`docs/processing.md`](docs/processing.md).

```bash
pip install -r requirements.txt

# 1. Reference data (seconds)
python -m src.download warnings     # rainstorm + typhoon signals -> data/raw/hko/, data/interim/rainstorm_episodes.csv
python -m src.download static       # detector locations, road segments, HKO daily rainfall -> data/raw/td/, data/raw/hko/
python -m src.download holidays     # public holidays 2018-2027 -> data/raw/calendar/public_holidays.csv

# 2. Choose days -> data/interim/day_manifest.csv
python -m src.download select-days --min-level R      # Red/Black events + controls: 59 days (start here)
python -m src.download select-days                    # Amber and above: 298 days

# 3. Download -> Parquet -> delete ZIP, day by day -> data/processed/{traffic_lane,rainfall_district}/
python -m src.pipeline --manifest                     # or --days 2025-08-05 ... / --range START END

# 4. Detector x 15-min table -> data/processed/traffic_15min/
python -m src.aggregate --manifest

# Check everything -> data/processed/validation_report.md (step 3 also runs this automatically)
python -m src.validate --manifest
```

Then in Python:

```python
from datetime import date
import pandas as pd
from src.data import load_traffic_lane, load_rainfall_district

lanes = load_traffic_lane([date(2025, 8, 5)])       # ~3.6 M rows: time, detector_id, lane, speed, occupancy, volume, sd, valid
rain = load_rainfall_district([date(2025, 8, 5)])   # 24 h x 18 districts
t15 = pd.read_parquet("data/processed/traffic_15min/2025/20250805.parquet")
```

### Step details

**`select-days`** options: `--years` (default `2022-2025`; 2021 had only 42 detectors
until November), `--months` (default `4-10`), `--min-level` `A`/`R`/`B` (lowest
warning level that counts as an event), `--pad-hours` (default 3, before and after
each episode), `--controls` (default 2). A control day is the same weekday one or
two weeks before an event day, with no rainstorm warning and no typhoon signal.

| Setting (2022–2025, Apr–Oct) | Days (event + control) | Downloaded (deleted after) | Kept on disk | Time (step 3) |
|---|---|---|---|---|
| `--min-level B` | 20 (9 + 11) | ~0.6 GB | ~0.2 GB | ~10 min |
| `--min-level R` | 59 (28 + 31) | ~1.8 GB | ~0.7 GB | ~25 min |
| `--min-level A` (default) | 298 (129 + 169) | ~9.2 GB | ~3.3 GB | ~2 h |

**`pipeline`** downloads in the main process (16 threads per day, `--workers`) and
parses in `--jobs` worker processes (default 3; each needs ~1.6 GB RAM for a
traffic day). Downloads stay at most `--jobs` days ahead of parsing, so only a few
ZIPs are on disk at once. Measured: ~24 s per traffic day with `--jobs 3` (download-bound),
~34 s with `--jobs 1`. `--keep-raw` keeps the ZIPs. Per-day coverage (snapshots, rows,
periods, detectors, re-dated periods, bulletins, max rain, errors) goes to
`data/processed/coverage.csv`. A failed day is logged there and the run continues.
Then `src.validate` writes `data/processed/validation_report.md` and lists every FAIL / WARN
(`--no-validate` skips it).

**`aggregate`** writes one row per detector and 15-minute bin: reading counts
(`n_readings`, `n_periods`, `n_invalid`, `n_zero_volume`, `n_speed_over_130`),
`volume_sum`, `occupancy_mean`, and two speeds, so the basic cleaning rule can
be compared directly:
`speed_naive` (plain mean of all readings) and `speed_clean` (volume-weighted mean
over `valid == 'Y'` and `volume > 0`). ~10 s and ~0.9 MB per day.

`python -m src.download fetch <sources> --days|--range|--manifest` downloads ZIPs
without parsing, if you want the raw XML.

## Data quirks found so far

These are material for the preprocessing experiments. The full list is in
[`docs/database_description.md`](docs/database_description.md#5-known-data-issues).

- **Detector network grew:** 42 detectors (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025).
  807 are listed in the location table.
- **`s.d.` only from ~18 Nov 2021.**
- **Snapshot time ≠ measurement time:** a file archived at 08:01 holds 07:53:00–07:54:00.
  The parser uses `<period_from>`.
- **Midnight date quirk:** the 00:00 period carries the previous day's `<date>`. The parser
  re-dates it using the file's archive time (`n_periods_redated` in coverage).
- **Gaps:** snapshots per day vary by month (≈ 530–1,430). On 5 Aug 2025 only 1,730 of
  2,880 30-second periods are present.
- **Truncated files:** a few archived XML files are cut off (1 of 919 on 29 Jul 2025). The parser keeps
  the complete readings before the cut and counts such files (`n_truncated_files` in coverage).
- **Overlap:** adjacent snapshots repeat readings (~9 % of rows), and bundles sometimes store
  a file twice. Both are deduplicated.
- **Placeholder speeds:** when `volume = 0` (~28 % of readings), `speed` is the posted limit
  (70/80/100/50/110, s.d. = 0), not a measurement.
- **Out-of-range values:** speeds up to 300 km/h, occupancy = −1, speed 0 with volume > 0;
  `valid = N` on ~0.5 % of readings.
- **Names:** the detector table has both `Central & Western` and `Central and Western`, and
  most road names have trailing spaces. HKO writes `Southern District` where TD writes `Southern`.
- **Rainfall is a min–max range per district.** A district missing from a bulletin had no rain.
  A bulletin without the rainfall sentence means no rain anywhere. The rainfall hour is the one
  stated in the sentence (e.g. 06:45–07:45), not the bulletin's "At 8 a.m." time.
- **Warning DB:** `24:00` end times; rows after `UUUU` are provisional.
- **All times are HKT (UTC+8)** and are stored without a time zone.

### Key periods

2025 had four Black Rainstorm episodes, the first time this has happened in one
year under the current system ([arXiv:2508.07600](https://arxiv.org/pdf/2508.07600)).
Other notable events: the [7–8 Sep 2023 record rainstorm](https://en.wikipedia.org/wiki/2023_Hong_Kong_rainstorm_and_floods)
and the Black Rainstorm of 4–5 Aug 2025.

## Repository layout

```
.
├── README(.zh).md, PROPOSAL.md, requirements.txt
├── docs/               # raw_data(.zh).md, processing(.zh).md, database_description(.zh).md, data_sources_notes.md
├── hkdata/             # general DATA.GOV.HK library: discover (search, archive coverage), download (plans)
│   └── plans/          # the download plans used for data/raw
├── src/
│   ├── download/       # step 1-2 (+ fetch): archive client, warnings, static files, holidays, day selection
│   ├── parse/          # traffic XML and weather bulletins -> tables
│   ├── pipeline.py     # step 3: download -> Parquet -> delete ZIP, parallel, with progress bars
│   ├── aggregate.py    # step 4: detector x 15-min table
│   ├── validate.py     # checks + profiles of all tables -> validation_report.md
│   ├── storage.py      # Parquet files that record the code version that made them
│   ├── data.py         # loaders for processed tables
│   └── config.py       # paths and source URLs
├── tests/
├── data/               # git-ignored; raw/ from the download commands, interim/ and processed/ from the pipeline
├── notebooks/          # EDA and experiment reports (to come)
└── results/            # figures, tables (to come)
```

## Licence & attribution

Code: MIT (TBD). Data: © Transport Department and Hong Kong Observatory,
HKSAR Government, used under the [DATA.GOV.HK Terms and Conditions](https://data.gov.hk/en/terms-and-conditions).
HKO notes that AWS rainfall is provisional and differs from the official
climatological record. We report which source each figure uses.
