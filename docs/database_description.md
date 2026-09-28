# Database Description

This document describes every data source used in the project and the tables
we build from them: where each source comes from, what its raw fields mean, how it
is stored after preprocessing, and how the tables link together.

All sources were checked against the live services and the DATA.GOV.HK
Historical Archive in September 2026. All times are **Hong Kong Time (HKT, UTC+8)**,
stored without a time zone, unless stated otherwise.

---

## 1. Source inventory

| ID | Source (provider) | Access | Frequency | History available | Role | Status |
|----|-------------------|--------|-----------|-------------------|------|--------|
| S1 | [Traffic Speed, Volume and Road Occupancy (Raw Data)](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), `rawSpeedVol-all.xml` (TD) | Historical Archive API | 30 s periods, published every 1 min | from Jun 2021 (but only 42 detectors until ~Nov 2021) | Target variables | **Required**, done (download + parse) |
| S2 | [Locations of Traffic Detectors](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv), CSV (TD) | Direct download | Static | Latest version only | Detector attributes, spatial join | **Required**, downloader done |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report), `CurrentWeather.xml` (HKO) | Historical Archive API | Hourly | from Jun 2021 | **District** past-hour rainfall | **Required**, done (download + parse) |
| S4 | [Rainstorm Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml), `rstorm.dat` (HKO) | Direct download | Per event | since Mar 1998 | Warning state at each time | **Required**, done |
| S5 | [Tropical Cyclone Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml), `tc.dat` (HKO) | Direct download | Per event | since 1946 | Exclude typhoon periods | **Required**, done |
| S6 | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal), `en.json` (1823) | Direct download (2025–27) + Historical Archive (older versions) | Yearly | 2018–2027 across archived versions | Working day / weekend / holiday | **Required**, done |
| S7 | [Gridded Rainfall Nowcast](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv), CSV (HKO) | Historical Archive API | ~every 15 min | from ~Jul 2022 | Local (~2 km) rainfall proxy | Optional, downloader to do |
| S8 | [Daily Total Rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall), `daily_HKO_RF_ALL.csv` (HKO) | Direct download | Daily | since 1884 | Day-level sanity checks | Auxiliary, done |

### Sources considered and not used

| Source | Why not |
|--------|---------|
| [Rainfall in the past hour from automatic weather stations](https://data.gov.hk/en-data/dataset/hk-hko-rss-rainfall-in-the-past-hour) (`hourlyRainfall.php`, 36 stations) | **Not archived.** The Historical Archive API returns `Not Found` for this resource in any date range, so only live data can be collected (from now on). This is why station-level matching is replaced by **district** rainfall (S3). Optionally, gridded nowcasts (S7) give sub-district detail. |
| [HKO weather station locations](https://www.hko.gov.hk/en/cis/stn.htm) | Only needed for station-level rainfall. With the station feed unavailable historically, it is not required. It becomes relevant only if we add daily per-station rainfall (`daily_<STN>_RF_ALL.csv`). |
| [Road Network Segments](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv) (`speed_segments_info.csv`) | Contains only `irn_id` and `ucase(route)`, the route number (174 values). It has no geometry and no detector mapping, and it belongs to the processed segment-speed feed (`irnAvgSpeed-all.xml`). Our unit of analysis is the detector, so it is not needed. |

---

## 2. Raw data dictionary

Every raw source (format, access, structure, each field with its official description,
observed values and quirks) is documented in **[`raw_data.md`](raw_data.md)**, using the
same IDs S1–S8. How each source is turned into the tables below is described in
**[`processing.md`](processing.md)**.

---

## 3. Processed database schema

Every processed Parquet file stores a JSON record in its schema metadata (key `hkrt`) with the
table name, the **code version** that produced it, the date and the parse statistics.
Read it with `src.storage.read_meta(path)`. Outdated files are rebuilt by the pipeline and flagged by
`src.validate` (see [`processing.md`](processing.md#versioning-rules)).

Tables are stored as Parquet (large, partitioned by day) or CSV (small).
PK = primary key.

### `traffic_lane` — cleaned-input fact table (from S1)

`data/processed/traffic_lane/<YYYY>/<YYYYMMDD>.parquet` (one file per archive day), ~3.6 M rows and ~11 MB per day.
Built by `src/parse/traffic.py` via `python -m src.pipeline`; read with `src.data.load_traffic_lane`.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `time` | timestamp | ✓ | Period start (`date` + `period_from`) |
| `detector_id` | category | ✓ | FK → `detectors` |
| `lane` | category | ✓ | Lane label from `lane_id` |
| `speed` | int16 | | km/h, as published |
| `occupancy` | int16 | | %, as published |
| `volume` | int16 | | vehicles / 30 s |
| `sd` | float32 | | speed s.d.; missing before ~18 Nov 2021 |
| `valid` | category | | `Y`/`N`, as published |

Only exact duplicates are removed at this stage. All other cleaning choices
(invalid rows, zero-volume speeds, outliers, gaps) are applied later as
experiment variables P1–P6 in `PROPOSAL.md`. `direction` and `period_to` are
dropped because S2 and `time` + 30 s already provide them.

### `traffic_15min` — detector × 15-min table (from `traffic_lane`)

`data/processed/traffic_15min/<YYYY>/<YYYYMMDD>.parquet`, built by `python -m src.aggregate`. ~74 k rows and ~0.9 MB per day.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `detector_id` | category | ✓ | |
| `t_bin` | timestamp | ✓ | start of the 15-min bin |
| `n_readings` | int32 | | lane readings in the bin |
| `n_periods` | int32 | | distinct 30-s periods (max 30) |
| `n_invalid`, `n_zero_volume`, `n_speed_over_130` | int32 | | quality counts |
| `speed_naive` | float32 | | plain mean of all readings |
| `speed_clean` | float32 | | volume-weighted mean over `valid == 'Y'` and `volume > 0` |
| `volume_sum` | float32 | | vehicles, valid readings only |
| `occupancy_mean` | float32 | | %, valid readings only |

### `detectors` — dimension (from S2)

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `detector_id` | string | ✓ | from `AID_ID_Number` |
| `district` | string | | normalised to the 18 standard names (see §5) |
| `road_en`, `road_tc` | string | | location text |
| `latitude`, `longitude` | float | | WGS84 |
| `easting`, `northing` | float | | HK1980 grid (m) |
| `direction`, `rotation` | string, int | | traffic direction |
| `n_lanes` | int | | derived from `traffic_lane` |
| `road_type` | string | | derived later, e.g. expressway / trunk / urban (feature for RQ2) |

### `rainfall_district` — fact (from S3)

`data/processed/rainfall_district/<YYYY>/<YYYYMMDD>.parquet`, one row per bulletin × 18 districts.
Built by `src/parse/weather.py`; read with `src.data.load_rainfall_district`.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `period_end` | timestamp | ✓ | End of the 1-h accumulation window, e.g. 07:45 |
| `district` | category | ✓ | 18 standard names (TD spelling, see §5) |
| `period_start` | timestamp | | `period_end` − 1 h |
| `rain_min_mm` | float32 | | lowest gauge in the district (0 if not listed) |
| `rain_max_mm` | float32 | | highest gauge in the district (0 if not listed) |
| `bulletin_time` | timestamp | | when the bulletin was issued (from its title, not the archive time) |
| `listed` | bool | | district appeared in the rainfall sentence |
| `section_present` | bool | | bulletin had a rainfall sentence at all |

A district not listed in a bulletin that has the rainfall sentence recorded no
rain. A bulletin without the sentence means no rain anywhere. Its period is
inferred as the last HH:45 at least 15 min before `bulletin_time`.

### `rainfall_grid` — optional fact (from S7)

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `issue_time` | timestamp | ✓ | nowcast issue time |
| `cell_id` | int | ✓ | grid cell (lat/lon index) |
| `rain_30min_mm` | float | | first lead time only |

Plus `detector_cell` (`detector_id` → nearest `cell_id`, distance), so we keep only cells near detectors.

### `rainstorm_warnings` — event (from S4)

`data/raw/hko/rainstorm_warnings.csv`

| Column | Type | Description |
|--------|------|-------------|
| `level` | int | 1 Amber, 2 Red, 3 Black |
| `level_name` | string | |
| `start`, `end` | timestamp | `24:00` rolled over to next-day 00:00 |
| `duration_min` | int | |
| `provisional` | bool | row after `UUUU` |

### `rainstorm_episodes` — event (derived from S4)

`data/interim/rainstorm_episodes.csv`. Consecutive signals (end = next start)
are merged, e.g. Amber → Red → Black → Amber.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `episode_id` | int | ✓ | |
| `start`, `end` | timestamp | | |
| `max_level`, `max_level_name` | int, string | | highest level reached |
| `n_signals` | int | | signals merged |
| `duration_min` | int | | |
| `provisional` | bool | | |

### `tc_signals` — event (from S5)

`data/raw/hko/tc_signals.csv`: `tc_code`, `name`, `intensity`, `signal`,
`direction`, `start`, `end`, `provisional`.

### `public_holidays` — dimension (from S6)

`data/raw/calendar/public_holidays.csv`, 2018–2027 (17 per year), merged from 10 archived versions + the live file.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `date` | date | ✓ | |
| `name` | string | | |

### `calendar` — derived dimension

One row per date: `date` (PK), `weekday`, `is_weekend`, `is_holiday`,
`day_type` (`workday` / `saturday` / `sunday_holiday`), `has_rainstorm_warning`,
`has_tc_signal`, `manifest_role` (`event` / `control` / none).

### `coverage` — pipeline log

`data/processed/coverage.csv`, one row per (`source`, `date`): `status` (`ok` / `no_data` / `failed`),
`version`, `n_snapshots`, `n_rows_raw`, `n_rows`, `n_periods`, `n_detectors`, `has_sd`, `n_periods_redated`, `n_truncated_files` (traffic),
`n_bulletins`, `n_with_rain_section`, `max_rain_mm` (weather), `error`.

### `validation_report.md` / `validation_checks.csv` — data checks

`data/processed/`, written by `python -m src.validate` (and after every `src.pipeline` run).
The CSV has one row per check: `table`, `day`, `name`, `level` (`FAIL` / `WARN` / `INFO` / `OK`),
`value`, `detail`. The Markdown report adds a profile of each table (NA, unique values, most
frequent values). See [`processing.md`](processing.md#validation-srcvalidatepy).

### `day_manifest` — download plan (existing)

`data/interim/day_manifest.csv`: `date`, `role` (`event` / `control`),
`episode_ids`, `max_level`, `max_level_name`.

---

## 4. Relationships

```
                         calendar (date) ◀──── public_holidays (date)
                              ▲
                              │ date(time)
traffic_lane ──detector_id──▶ detectors ──district──▶ rainfall_district
  (time, detector_id, lane)        │                  (period_end, district)
        │                          │  nearest cell         ▲
        │                          └──────────────▶ rainfall_grid (optional)
        │                                                  │
        └──────── time aligned to rainfall window ─────────┘
        │
        └── time ∈ [start, end) ──▶ rainstorm_warnings / rainstorm_episodes / tc_signals
```

The modelling table (next stage) is `traffic_lane` aggregated per detector
and time bin, joined to the other tables through these keys. Each join choice
(aggregation window, rain value = min / mid / max, time lag, warning encoding)
is a preprocessing experiment.

---

## 5. Known data issues

| Source | Issue | Handling |
|--------|-------|----------|
| S1 | Detector network grew: 42 detectors (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025) | Study years 2022–2025; per-detector baselines |
| S1 | `s.d.` element missing before ~18 Nov 2021 | Parser treats it as optional (`sd` = NaN) |
| S1 | Snapshots per day vary by month (≈ 530–1,430) | Coverage recorded per day in `data/processed/coverage.csv` |
| S1 | File time ≠ measurement time: a file archived at 08:01 holds 07:53–07:54 | Use `period_from` |
| S1 | A few archived files are truncated mid-document (1 of 919 on 29 Jul 2025) | Keep complete readings before the cut; count in `n_truncated_files` |
| S1 | The 00:00 period is published with the previous day's `<date>` | Re-dated using the file's archive time (`n_periods_redated` in coverage) |
| S1 | Adjacent files overlap (~9 % duplicate rows); bundles occasionally store a file twice | Deduplicate on (`time`, `detector_id`, `lane`) |
| S1 | Only 1,730 of 2,880 periods per day present (~40 % missing) | Gap handling = experiment P6 |
| S1 | When `volume = 0` (27.7 % of rows), `speed` holds a placeholder equal to the speed limit (70/80/100/50/110, s.d. = 0), not a measurement | Treat as missing / free-flow, part of experiment P3 |
| S1 | `occupancy = -1` (60 rows), `speed` up to 300, `speed = 0` with `volume > 0` (5,991 rows on 5 Aug 2025) | Physical-bound filter, experiment P2 |
| S1 / S2 | 772 detectors report but S2 lists 807; S2 is only the latest version | Inner join; report unmatched IDs |
| S2 | District spelling: `Central & Western` vs `Central and Western` (1 row); 97 % of `Road_EN` values have trailing spaces | Normalise, strip |
| S2 / S3 | TD uses `Southern`, HKO uses `Southern District` (also Eastern, Islands, North, Central & Western) | Strip the ` District` suffix, normalise `and` → `&` |
| S3 | Rainfall is a min–max range per district, not a point value | Choice of min / mid / max = experiment P7 |
| S3 | Free-text format; wording may vary over the years | Regex parser with unit tests on samples from each year |
| S4 / S5 | `24:00` end times; provisional rows after `UUUU` | Handled in parser |
| S3 | Archive time ≠ bulletin time (file archived 20:02 holds the 19:02 bulletin); some bulletins are late (01:46) | Use the bulletin's own timestamp; anchor the period to it |
| S6 | Each file covers only 3 years | Merge archived versions, deduplicate by date |
| S7 | Forecast, not observation; starts ~Jul 2022 | Optional sensitivity check only |

---

## 6. Volume

| Scope | Days | S1 ZIP (download) | `traffic_lane` Parquet | S3 |
|-------|------|-------------------|------------------------|----|
| 1 day | 1 | 31 MB | 10 MB | 50 kB |
| Red+ events + controls, 2022–2025 | 59 | ~1.8 GB | ~0.7 GB | ~3 MB |
| Amber+ events + controls, 2022–2025 | 298 | ~9.2 GB | ~3.3 GB | ~15 MB |
| Full archive (Jun 2021 – Sep 2026) | ~1,950 | ~64 GB | ~21 GB | ~0.1 GB |

The pipeline converts each day's ZIP to Parquet and then deletes the ZIP, so
disk usage is roughly the Parquet column.
