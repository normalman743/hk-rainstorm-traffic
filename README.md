# hk-rainstorm-traffic

Which Hong Kong roads are most sensitive to rainstorms? Integrating HKO rainfall and warning data with Transport Department traffic detectors to study how preprocessing and feature engineering affect congestion prediction.

> Course project. The focus is **data preprocessing and integration**: every
> major cleaning / aggregation / matching decision is treated as an experimental
> variable, and we measure how it changes the downstream results.
> See [`PROPOSAL.md`](PROPOSAL.md) for the full research plan and
> [`docs/database_description.md`](docs/database_description.md) for every source, field and table.

## Research questions

1. **Sensitivity:** Which road segments show the largest speed drop / occupancy rise during rainstorms, after controlling for time of day and day of week?
2. **Prediction:** Can road attributes plus rainfall features predict congestion during rainstorm periods better than a time-only baseline?
3. **Preprocessing impact:** How much do choices such as outlier handling, aggregation window, rainfall-to-road matching and warning encoding change the answers to Q1 and Q2?

## Data sources

All data is free Hong Kong government open data. Nothing is committed to this
repo. Download it into `data/raw/` (git-ignored).

| # | Dataset | Provider | What we use | Resolution | History |
|---|---------|----------|-------------|------------|---------|
| 1 | [Traffic Data of Strategic / Major Roads](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads) | Transport Department | Per-lane speed, volume, occupancy, validity flag | 30-second periods, published every 1 min, ~800 detectors | Archived on DATA.GOV.HK from **mid-2021** |
| 2 | [Traffic detector locations](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv) (CSV) | Transport Department | Detector ID, road name, **district**, lat/lon, direction | Static | – |
| 3 | [Current Weather Report (RSS)](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report): `CurrentWeather.xml` | Hong Kong Observatory | **Past-hour rainfall range (mm) per district**, warning text | Hourly | Archived on DATA.GOV.HK from **mid-2021** |
| 4 | [Rainstorm Warning Signals Database](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) | Hong Kong Observatory | Amber / Red / Black start & end times | Per event | Since March 1998 |
| 5 | [Daily total rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) (e.g. `daily_HKO_RF_ALL.csv`) | Hong Kong Observatory | Daily rainfall at HKO HQ and other stations | Daily | Decades |
| 6 | [Rainfall in the past hour from automatic weather stations](https://data.gov.hk/en-data/dataset/hk-hko-rss-rainfall-in-the-past-hour) (`hourlyRainfall.php`) | Hong Kong Observatory | Station-level hourly rainfall | Every 15 min | **Real-time only**: not in the historical archive; optional live collection |

Optional extensions: [Processed road-segment speeds](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads) (`irnAvgSpeed-all.xml`, 2-min), [HKO Open Data API docs](https://www.hko.gov.hk/en/weatherAPI/doc/files/HKO_Open_Data_API_Documentation.pdf), [HKO daily data download page](https://www.hko.gov.hk/en/cis/downloadpage.htm).

### Downloading historical files

Historical versions of DATA.GOV.HK resources are served by the
[Historical Archive API](https://data.gov.hk/en/help/api-spec):

```bash
# 1. List available versions of a file for a date range (YYYYMMDD)
curl -G "https://app.data.gov.hk/v1/historical-archive/list-file-versions" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "start=20250805&end=20250805"

# 2. Fetch one snapshot (time = YYYYMMDD-HHMM, must match a listed timestamp)
curl -L -G "https://app.data.gov.hk/v1/historical-archive/get-file" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "time=20250805-0801" -o rawSpeedVol-20250805-0801.xml

# Same API for hourly district rainfall
curl -L -G "https://app.data.gov.hk/v1/historical-archive/get-file" \
  --data-urlencode "url=https://rss.weather.gov.hk/rss/CurrentWeather.xml" \
  --data "time=20250805-0809" -o CurrentWeather-20250805-0809.xml
```

Bulk downloads: `list-file-versions` also returns **monthly ZIP bundles**
(`data-files`). The raw traffic file is about **1 GB per month** compressed
(~30k snapshots). You can also download monthly/daily archives from the
dataset page on DATA.GOV.HK ("Historical Data" tab).

**Storage note:** 5 rainy seasons (Apr–Sep, 2021–2025) of raw detector data
is roughly 30 GB zipped. We therefore download only rainstorm event days plus
matched dry control days (see below), about 11 GB in total.

### Download scripts

```bash
pip install -r requirements.txt

python -m src.download warnings     # HKO rainstorm + typhoon signal DBs -> data/raw/hko/*.csv,
                                    #   data/interim/rainstorm_episodes.csv
python -m src.download static       # detector locations, road segments, HKO daily rainfall
python -m src.download select-days --years 2021-2025 --months 4-10 --min-level A \
       --pad-hours 3 --controls 2   # -> data/interim/day_manifest.csv (event + control days)

python -m src.download fetch weather traffic --manifest        # everything in the manifest
python -m src.download fetch traffic --days 2025-08-05         # or specific days
python -m src.download fetch weather --range 2025-08-01 2025-08-31
```

`fetch` writes one ZIP per source and day to `data/raw/<source>/<YYYY>/<YYYYMMDD>.zip`
and skips days that already exist, so it can be re-run safely after an interruption. It
does not download the 1 GB monthly bundle. Instead it reads the bundle's index with
HTTP range requests and pulls only that day's snapshots (~30 MB, ~40 s per day of
traffic data). Sources: `traffic` (raw detectors), `weather` (district rainfall),
`segments` (processed segment speeds, optional).

With the defaults (2021–2025, April–October, any warning level, 2 control
weeks) the manifest has 362 days: 155 event days and 207 control days.

A control day is the same weekday one or two weeks before an event day, with no
rainstorm warning and no typhoon signal.

### Data quirks found so far

These matter for the cleaning step:

- **Snapshot time ≠ measurement time.** A traffic snapshot archived at 08:01 holds
  the two 30-second periods 07:53:00–07:54:00. Always use `<period_from>` inside the XML.
- **Gaps.** About 947 snapshots per day (≈ one every 1.5 min), each covering 1 min,
  so roughly a third of the minutes are missing even before any sensor faults.
- **Duplicate snapshots.** Bundles sometimes store the same file twice. `fetch` drops exact duplicates.
- **`24:00` timestamps.** The HKO warning files write midnight as 24:00. The parser rolls it over to 00:00 the next day.
- **Provisional records.** In the HKO warning files, rows after the `UUUU` marker are provisional (flagged in the CSVs).
- **All times are HKT (UTC+8)** and are stored without a time zone.

### Key periods

2025 had four Black Rainstorm episodes, the first time this has happened in
one year under the current system ([arXiv:2508.07600](https://arxiv.org/pdf/2508.07600)).
Other notable events: the [7–8 Sep 2023 record rainstorm](https://en.wikipedia.org/wiki/2023_Hong_Kong_rainstorm_and_floods)
and the Black Rainstorm on the morning of 5 Aug 2025. We confirmed that both the
traffic and the district-rainfall archives contain snapshots for 5 Aug 2025.
The full event list comes from dataset #4.

## Repository layout (`src/download/` done, rest planned)

```
.
├── README.md
├── PROPOSAL.md
├── data/
│   ├── raw/            # downloaded XML/ZIP/CSV (git-ignored)
│   ├── interim/        # parsed Parquet
│   └── processed/      # modelling tables
├── src/
│   ├── download/       # archive API clients
│   ├── parse/          # XML -> tabular
│   ├── clean/          # validity flags, outliers, gaps
│   ├── integrate/      # time alignment, detector <-> rainfall matching
│   └── features/       # rainstorm / temporal / road features
├── notebooks/          # EDA and experiment reports
└── results/            # figures, tables
```

## Licence & attribution

Code: MIT (TBD). Data: © Transport Department and Hong Kong Observatory,
HKSAR Government, used under the [DATA.GOV.HK Terms and Conditions](https://data.gov.hk/en/terms-and-conditions).
HKO notes that AWS rainfall is provisional and differs from the official
climatological record. We report which source each figure uses.
