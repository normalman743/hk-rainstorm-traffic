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
| S1 | [Traffic Speed, Volume and Road Occupancy (Raw Data)](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), `rawSpeedVol-all.xml` (TD) | Historical Archive API | 30 s periods, published every 1 min | from Jun 2021 | Target variables | **Required**, downloader done |
| S2 | [Locations of Traffic Detectors](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv), CSV (TD) | Direct download | Static | Latest version only | Detector attributes, spatial join | **Required**, downloader done |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report), `CurrentWeather.xml` (HKO) | Historical Archive API | Hourly | from Jun 2021 | **District** past-hour rainfall | **Required**, downloader done, parser to do |
| S4 | [Rainstorm Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml), `rstorm.dat` (HKO) | Direct download | Per event | since Mar 1998 | Warning state at each time | **Required**, done |
| S5 | [Tropical Cyclone Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml), `tc.dat` (HKO) | Direct download | Per event | since 1946 | Exclude typhoon periods | **Required**, done |
| S6 | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal), `en.json` (1823) | Direct download (2025–27) + Historical Archive (older versions) | Yearly | 2020–2027 across archived versions | Working day / weekend / holiday | **Required**, downloader to do |
| S7 | [Gridded Rainfall Nowcast](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv), CSV (HKO) | Historical Archive API | ~every 15 min | from ~Jul 2022 | Local (~2 km) rainfall proxy | Optional, downloader to do |
| S8 | [Daily Total Rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall), `daily_HKO_RF_ALL.csv` (HKO) | Direct download | Daily | since 1884 | Day-level sanity checks | Auxiliary, done |

### Sources considered and not used

| Source | Why not |
|--------|---------|
| [Rainfall in the past hour from automatic weather stations](https://data.gov.hk/en-data/dataset/hk-hko-rss-rainfall-in-the-past-hour) (`hourlyRainfall.php`, 36 stations) | **Not archived.** The Historical Archive API returns `Not Found` for this resource in any date range, so only live data can be collected (from now on). This is why station-level matching is replaced by **district** rainfall (S3). Optionally, gridded nowcasts (S7) give sub-district detail. |
| [HKO weather station locations](https://www.hko.gov.hk/en/cis/stn.htm) | Only needed for station-level rainfall. With the station feed unavailable historically, it is not required. It becomes relevant only if we add daily per-station rainfall (`daily_<STN>_RF_ALL.csv`). |
| [Road Network Segments](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv) (`speed_segments_info.csv`) | Contains only `irn_id` and a route flag. It has no geometry and no detector mapping, and it belongs to the processed segment-speed feed (`irnAvgSpeed-all.xml`). Our unit of analysis is the detector, so it is not needed. |

---

## 2. Raw data dictionary

### S1 — Traffic detector readings (`rawSpeedVol-all.xml`)

Nested XML: file → period → detector → lane. Each published file holds **two
30-second periods**. Official descriptions are quoted from the TD schema
[`SpeedVolOcc-BR.xsd`](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/SpeedVolOcc-BR.xsd).

| Level | Field | Type | Official description | Notes / observed values (5 Aug 2025) |
|-------|-------|------|----------------------|------------------------------|
| file | `date` | date | Date of the data | e.g. `2025-08-05` |
| period | `period_from` | time | Timestamp of data period starts | `07:53:00` |
| period | `period_to` | time | Timestamp of data period ends | always `period_from` + 30 s |
| detector | `detector_id` | string | Reference ID for AID | `AID01101`; 772 detectors report on this day |
| detector | `direction` | string | Direction of AID | `South East`; duplicated in S2 |
| lane | `lane_id` | string | Reference ID for Lane of AID | `Fast Lane`, `Middle Lane`, `Slow Lane`, `Middle Lane 1`–`4` |
| lane | `speed` | integer | Average speed of lane | km/h; median 70; max 300 (outlier) |
| lane | `occupancy` | integer | Occupancy of lane | % of time the detector is occupied; 0–100, plus `-1` in 60 rows |
| lane | `volume` | integer | – | vehicles in the 30 s period; 0–61 |
| lane | `s.d.` | decimal | – | standard deviation of speed |
| lane | `valid` | `Y`/`N` | – | TD validity flag; `N` = 0.5 % of rows |

### S2 — Detector locations (`traffic_speed_volume_occ_info.csv`)

One row per detector (807 rows).

| Field | Description |
|-------|-------------|
| `AID_ID_Number` | Detector ID; joins to S1 `detector_id` |
| `District` | One of the 18 districts (TD spelling, e.g. `Southern`, `Central & Western`) |
| `Road_EN` / `Road_TC` / `Road_SC` | Location text, e.g. "Aberdeen Praya Road near Abba House - Eastbound" |
| `Easting` / `Northing` | HK 1980 Grid coordinates (m) |
| `Latitude` / `Longitude` | WGS84 |
| `Direction` | Traffic direction |
| `Rotation` | Bearing in degrees (for map arrows) |

### S3 — Current Weather Report (`CurrentWeather.xml`)

An RSS 2.0 feed. The data is free text inside an HTML `<description>`
(CDATA), so it must be parsed with regular expressions.

| Element | Content |
|---------|---------|
| `item/title` | "Bulletin updated at 08:02 HKT 05/08/2025" |
| `item/pubDate` | Same moment, in GMT |
| `item/category` | Weather category code |
| `description` → HKO temperature, humidity | "Air temperature : 25 degrees Celsius", "Relative Humidity : 95 per cent" |
| `description` → warning reminder | "The Black Rainstorm Warning Signal has been issued." |
| `description` → temperatures at ~25 stations | table of station name → °C |
| **`description` → district rainfall** | "Between 6:45 and 7:45 a.m. … The rainfall recorded in various regions were: Southern District 27 to 60 mm; …", i.e. the **min–max past-hour rainfall across gauges in each of the 18 districts** |

### S4 — Rainstorm warning signals (`rstorm.dat`)

Tab-separated, no header, one row per signal. Rows after a `UUUU` line are
provisional.

| Col | Description |
|-----|-------------|
| 1 | Colour: `A` Amber, `R` Red, `B` Black |
| 2–6 | Start: year, month, day, hour, minute |
| 7–11 | End: year, month, day, hour, minute (midnight may be written `24:00`) |
| 12–13 | Duration: hours, minutes |

### S5 — Tropical cyclone signals (`tc.dat`)

Tab-separated, no header, UTF-8 BOM, one row per signal.

| Col | Description |
|-----|-------------|
| 1 | Cyclone code, e.g. `202603` |
| 2 | Intensity, e.g. `T`, `ST`, `SuperT`; rows with `MSN` are not cyclone signals and are skipped |
| 3 | Name (`NIL` = unnamed) |
| 4 | Signal number: 1, 3, 8, 9, 10 |
| 5 | Direction for No. 8 (`NE`/`NW`/`SE`/`SW`), else `X` or `*` |
| 6 / 7 / 8 / 9 | Start: `HHMM` (leading zeros dropped), day, month, year |
| 10 | Flag (`X`/`S`, undocumented; appears only in old records) |
| 11 / 12 / 13 / 14 | End: `HHMM`, day, month, year |
| 15 | Flag, as col 10 |
| 16 | Duration (`HHHMM`) |

### S6 — Public holidays (`en.json`)

iCalendar-style JSON: `vcalendar[0].vevent[]`. Each file covers three years. The
current file covers 2025–2027; archived versions cover 2020–2022, 2021–2023
and 2023–2025.

| Field | Description |
|-------|-------------|
| `dtstart` | `["YYYYMMDD", {"value": "DATE"}]`, holiday date |
| `dtend` | Following day (exclusive end) |
| `summary` | Holiday name, e.g. "The first day of January" |
| `uid` | `YYYYMMDD@1823.gov.hk` |
| `dtstamp`, `transp` | Calendar metadata (unused) |

### S7 — Gridded rainfall nowcast (optional)

CSV, ~58,000 rows per file: a 121 × 121 lat/lon grid (≈ 2 km spacing) × 4 lead times.

| Field | Description |
|-------|-------------|
| `Updated Date and Time (in Hong Kong Time)` | Issue time, `YYYYMMDDHHMM` |
| `Ending Date and Time (in Hong Kong Time)` | End of the 30-min window being forecast (+30, +60, +90, +120 min) |
| `Latitude (degree)` / `Longitude (degree)` | Grid-cell centre |
| `Half-hourly Nowcast Accumulated Rainfall (mm)` | Rainfall forecast for that 30-min window |

This is a **radar-based forecast**, not a gauge measurement. We would use only the
first lead time, as a proxy for current local rainfall.

### S8 — Daily total rainfall at HKO (`daily_HKO_RF_ALL.csv`)

Two title lines, then `年/Year, 月/Month, 日/Day, 數值/Value, 數據完整性/data Completeness`,
then footnote lines. `Value` is in mm; `微量/Trace` means < 0.05 mm, `***` means unavailable.
Completeness: `C` = complete, `#` = incomplete.

---

## 3. Processed database schema

Tables are stored as Parquet (large, partitioned by day) or CSV (small).
PK = primary key.

### `traffic_lane` — cleaned-input fact table (from S1)

`data/processed/traffic_lane/date=YYYY-MM-DD/part.parquet`, ~3.6 M rows and ~10 MB per day.

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `time` | timestamp | ✓ | Period start (`date` + `period_from`) |
| `detector_id` | category | ✓ | FK → `detectors` |
| `lane` | category | ✓ | Lane label from `lane_id` |
| `speed` | int16 | | km/h, as published |
| `occupancy` | int16 | | %, as published |
| `volume` | int16 | | vehicles / 30 s |
| `sd` | float32 | | speed s.d. |
| `valid` | category | | `Y`/`N`, as published |

Only exact duplicates are removed at this stage. All other cleaning choices
(invalid rows, zero-volume speeds, outliers, gaps) are applied later as
experiment variables P1–P6 in `PROPOSAL.md`. `direction` and `period_to` are
dropped because S2 and `time` + 30 s already provide them.

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

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `period_end` | timestamp | ✓ | End of the 1-h accumulation window, e.g. 07:45 |
| `district` | string | ✓ | 18 standard names |
| `period_start` | timestamp | | usually `period_end` − 1 h |
| `rain_min_mm` | float | | lowest gauge in the district |
| `rain_max_mm` | float | | highest gauge in the district |
| `bulletin_time` | timestamp | | time the bulletin was issued |

A district is absent when no rain was reported there. Treat an absence as
0 mm only when the bulletin exists.

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

| Column | Type | PK | Description |
|--------|------|----|-------------|
| `date` | date | ✓ | |
| `name` | string | | |

### `calendar` — derived dimension

One row per date: `date` (PK), `weekday`, `is_weekend`, `is_holiday`,
`day_type` (`workday` / `saturday` / `sunday_holiday`), `has_rainstorm_warning`,
`has_tc_signal`, `manifest_role` (`event` / `control` / none).

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
| S1 | File time ≠ measurement time: a file archived at 08:01 holds 07:53–07:54 | Use `period_from` |
| S1 | Adjacent files overlap (~9 % duplicate rows); bundles occasionally store a file twice | Deduplicate on (`time`, `detector_id`, `lane`) |
| S1 | Only 1,730 of 2,880 periods per day present (~40 % missing) | Gap handling = experiment P6 |
| S1 | When `volume = 0` (27.7 % of rows), `speed` holds a placeholder equal to the speed limit (70/80/100/50/110, s.d. = 0), not a measurement | Treat as missing / free-flow, part of experiment P3 |
| S1 | `occupancy = -1` (60 rows), `speed` up to 300 | Physical-bound filter, experiment P2 |
| S1 / S2 | 772 detectors report but S2 lists 807; S2 is only the latest version | Inner join; report unmatched IDs |
| S2 | District spelling: `Central & Western` vs `Central and Western` (1 row) | Normalise |
| S2 / S3 | TD uses `Southern`, HKO uses `Southern District` (also Eastern, Islands, North, Central & Western) | Strip the ` District` suffix, normalise `and` → `&` |
| S3 | Rainfall is a min–max range per district, not a point value | Choice of min / mid / max = experiment P7 |
| S3 | Free-text format; wording may vary over the years | Regex parser with unit tests on samples from each year |
| S4 / S5 | `24:00` end times; provisional rows after `UUUU` | Handled in parser |
| S6 | Each file covers only 3 years | Merge archived versions, deduplicate by date |
| S7 | Forecast, not observation; starts ~Jul 2022 | Optional sensitivity check only |

---

## 6. Volume

| Scope | Days | S1 ZIP (download) | `traffic_lane` Parquet | S3 |
|-------|------|-------------------|------------------------|----|
| 1 day | 1 | 31 MB | 10 MB | 50 kB |
| Red+ events + controls, 2021–2025 | 75 | ~2.3 GB | ~0.8 GB | ~4 MB |
| Amber+ events + controls, 2021–2025 | 362 | ~11 GB | ~3.8 GB | ~18 MB |
| Full archive (Jun 2021 – Sep 2026) | ~1,950 | ~64 GB | ~20 GB | ~0.1 GB |

The pipeline converts each day's ZIP to Parquet and then deletes the ZIP, so
disk usage is roughly the Parquet column.
