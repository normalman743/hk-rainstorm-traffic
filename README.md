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
  The earlier day-by-day pipeline was removed (see [Processing](#processing)).

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
| S11, S14 | Segment speeds (TD processed), segment → route | TD | ~1 min × segment (~4,400) | 2024-01 .. 2025-12 | optional |
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
python -m src.download static-history   # S2, S14 older versions
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

## Processing

**Being rewritten.** The earlier pipeline (download selected days → parse → Parquet → delete
the ZIPs, plus a detector × 15-min table and validation) was removed on 2026-09-29 with its
output; it is in the git history before that date. The new one will read the monthly bundles
already in `data/raw/`. What `src.download` itself derives (warning signals, rainstorm episodes,
holidays, and the optional day selection `select-days`) is described in
[`docs/processing.md`](docs/processing.md).

## Data quirks found so far

These are material for the preprocessing experiments. The full list is in
[`docs/database_description.md`](docs/database_description.md#5-known-data-issues).

- **Detector network grew:** 42 detectors (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025).
  807 are listed in the location table.
- **`s.d.` only from ~18 Nov 2021.**
- **Snapshot time ≠ measurement time:** a file archived at 08:01 holds 07:53:00–07:54:00;
  the measurement time is `<period_from>`.
- **Midnight date quirk:** the 00:00 period carries the previous day's `<date>`; the file's
  archive time tells the real day.
- **Gaps:** snapshots per day vary by month (≈ 530–1,430). On 5 Aug 2025 only 1,730 of
  2,880 30-second periods are present.
- **Truncated files:** a few archived XML files are cut off (1 of 919 on 29 Jul 2025).
- **Overlap:** adjacent snapshots repeat readings (~9 % of rows), and bundles sometimes store
  a file twice.
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
├── docs/               # raw_data(.zh).md, processing(.zh).md, database_description(.zh).md, data_sources_notes.md, course_project.md
├── hkdata/             # general DATA.GOV.HK library: discover (search, archive coverage), download (plans)
│   └── plans/          # the download plans used for data/raw
├── src/
│   ├── download/       # sources not in the plans: warnings, static files, holidays; day selection; fetch
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
