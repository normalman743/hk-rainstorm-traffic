# Database Description

This document describes every data source used in the project and the tables
we build from them: where each source comes from, what its raw fields mean, how it
is stored after preprocessing, and how the tables link together.

All sources were checked against the live services and the DATA.GOV.HK
Historical Archive in September 2026. All times are **Hong Kong Time (HKT, UTC+8)**,
stored without a time zone, unless stated otherwise.

---

## 1. Source inventory

"Downloaded" is what was downloaded under `data/raw/` (inventory, locations and data dictionaries:
[`raw_data.md`](raw_data.md#inventory-on-disk-2026-09-29)); since 2026-09-30 only the three study
months (2024-05, 2025-07, 2025-08) of the S1, S7, S9 and S11 bundles are kept on disk. "Status"
gives the layers built (L1 raw as written, L2 cleaned; §3 and [`processing.md`](processing.md));
L3 is built from the L2 of the main sources.

| ID | Source (provider) | Access | Frequency | Downloaded | Role | Status |
|----|-------------------|--------|-----------|------------|------|--------|
| S1 | [Traffic Speed, Volume and Road Occupancy (Raw Data)](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), `rawSpeedVol-all.xml` (TD) | Historical Archive (`hkgovdata.download`) | 30 s periods, published every 1 min | 2024-01 .. 2025-12 (archive from Jun 2021; only 42 detectors until ~Nov 2021) | Target variables | **Required**; L1, L2 |
| S2 | [Locations of Traffic Detectors](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv), CSV (TD) | Historical Archive (`hkgovdata.download`, `src.download static-history`) | Versions | 8 versions, 2021-08 .. 2026-04 | Detector attributes, spatial join | **Required**; L1, L2 |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report), `CurrentWeather.xml` (HKO) | Historical Archive (`hkgovdata.download`) | Hourly | 2024-01 .. 2025-12 (archive from Jun 2021) | **District** past-hour rainfall | **Required**; L1, L2 |
| S4 | [Rainstorm Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml), `rstorm.dat` (HKO) | Direct download (`src.download warnings`) | Per event | since Mar 1998 | Warning state at each time | **Required**; L1, L2 |
| S5 | [Tropical Cyclone Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml), `tc.dat` (HKO) | Direct download (`src.download warnings`) | Per event | since 1946 | Exclude typhoon periods | **Required**; L1, L2 |
| S6 | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal), `en.json` (1823) | Direct download + Historical Archive (`src.download holidays`) | Yearly | 2018–2027 across archived versions | Working day / weekend / holiday | **Required**; L1, L2 |
| S8 | [Daily Total Rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall), `daily_HKO_RF_ALL.csv` (HKO) | Direct download (`src.download static`) | Daily | since 1884 | Day-level sanity checks | Auxiliary; L1, L2 |
| S9 | [Smart-lamppost traffic detectors](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts), `rawSpeedVol_SLP-all.xml` (TD) | Historical Archive (`hkgovdata.download`) | 30 s periods | 2024-01 .. 2025-12 | Extra detectors (same format as S1) | Optional; L1 |
| S10 | Smart-lamppost detector locations, CSV (TD) | Historical Archive (`hkgovdata.download`) | Versions | 2023-12, 2024-01 | Attributes of S9 detectors | Optional; L1 |
| S11 | Traffic Speeds of Road Network Segments (Processed Data), `irnAvgSpeed-all.xml` (TD) | Historical Archive (`hkgovdata.download`) | ~1 min | 2024-01 .. 2025-12 | TD's own segment speeds, cross-check | Optional; L1 |
| S14 | [Road Network Segments](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv), `speed_segments_info.csv` (TD) | Historical Archive (`hkgovdata.download`, `src.download static-history`) | Versions | 6 versions, 2021-08 .. 2023-09 | Segment → route number for S11 | Optional; L1 |
| S12 | [Road Network (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2), `RdNet_IRNP.gdb.zip` (TD) | Historical Archive (`hkgovdata.download`) | Versions | 2024-01 .. 2025-12 (34 versions) | Geometry of S11 segments (`ROUTE_ID`) | Optional; L1 |
| S13 | [Special Traffic News (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2), `trafficnews.xml` (TD) | Historical Archive (`hkgovdata.download`) | Per message update | 2024-01 .. 2025-12 | Flag incidents / closures as confounders | Optional; L1 |
| S7 | [Gridded Rainfall Nowcast](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv), CSV (HKO) | Historical Archive (`hkgovdata.download`) | ~every 15 min | 2024-01 .. 2025-12 (archive from ~Jul 2022) | Local (~2 km) rainfall proxy | Optional; L1 |

### Sources considered and not used

| Source | Why not |
|--------|---------|
| [Rainfall in the past hour from automatic weather stations](https://data.gov.hk/en-data/dataset/hk-hko-rss-rainfall-in-the-past-hour) (`hourlyRainfall.php`, 36 stations) | **Not archived.** The Historical Archive API returns `Not Found` for this resource in any date range, so only live data can be collected (from now on). This is why station-level matching is replaced by **district** rainfall (S3). Optionally, gridded nowcasts (S7) give sub-district detail. |
| [HKO weather station locations](https://www.hko.gov.hk/en/cis/stn.htm) | Only needed for station-level rainfall. With the station feed unavailable historically, it is not required. It becomes relevant only if we add daily per-station rainfall (`daily_<STN>_RF_ALL.csv`). |
| HKO JSON Current Weather Report (`weather.php?dataType=rhrread`) | Structured per-district rainfall, but **not archived** (`Not Found`), so S3's RSS text is parsed instead. |
| [Weather Warning Summary / Information](https://data.gov.hk/en-data/dataset/hk-hko-rss-weather-warning-summary) (RSS) | Archived, but only about **one snapshot a day** (~10:20), so warnings issued and cancelled between snapshots are missed; S4 / S5 give exact start and end times. |

---

## 2. Raw data dictionary

Every raw source (format, access, structure, each field with its official description,
observed values and quirks) is documented in **[`raw_data.md`](raw_data.md)**, using the
same IDs S1–S14, together with where each source's data dictionary is. How each source is turned into the tables below is described in
**[`processing.md`](processing.md)**.

---

## 3. Tables

All under `data/interim/`, Parquet, built by the scripts in [`processing.md`](processing.md).
PK = primary key (checked: the scripts raise on a repeated key). Times are HKT without a time
zone.

**L1** (`l1/<source>/`): every raw file as written, all values strings, one column per element
or field; each row keeps its file (`bundle`, `index`). The columns of each source are in the
docstring of its parser (`src/clean/*_parse.py`) and in [`raw_data.md`](raw_data.md).

### L2 (`l2/`)

| Table | Rows | PK | Columns |
|-------|------|----|---------|
| `s1/<YYYYMM>.parquet` | 123.1 M / 99.9 M / 109.9 M | `detector_id`, `time`, `lane_id` | `time` (start of the 30-s period), `detector_id`, `direction`, `lane_id`, `speed` (km/h), `volume` (vehicles in 30 s), `occupancy` (%), `sd`, `valid` (bool), `l2_rule` (rules that changed or made the row), `bundle`, `index` (the L1 file) |
| `s2/detectors.parquet` | 790 | `AID_ID_Number` | S2 version 2025-10, field names as written: `AID_ID_Number`, `District`, `Road_EN`, `Road_TC`, `Road_SC`, `Easting`, `Northing`, `Latitude`, `Longitude`, `Direction`, `Rotation`; plus `rain_district` (the S3 name of `District`, D11) |
| `s3/rain.parquet` | 40,176 | `period_end`, `district` | `period_start`, `period_end` (the hour HH:45 → HH:45), `district` (HKO name), `low`, `high` (mm), `l2_rule` (D8 interpolated, D9 not listed = 0 mm) |
| `s4/rainstorm.parquet` | 974 | `line` | `line`, `colour`, `level` (1 Amber, 2 Red, 3 Black), `start`, `end`, `provisional` |
| `s5/tc.parquet` | 1,262 | `line` | `line`, `cyclone`, `intensity`, `name`, `signal` (int), `direction`, `start`, `end` |
| `s6/holidays.parquet` | 170 | `date` | `date`, `name`, `version` (the latest version that lists the date) |
| `s8/daily.parquet` | 49,491 | `date` | `date`, `rain_mm`, `trace` (`Trace` = 0 mm), `completeness` |

### L3 (`l3/<name>.parquet`)

`default.parquet`: 6,430,886 rows; variants are named by their changed options (e.g.
`speed_agg=mean.parquet`). PK `detector_id`, `slot`.

| Group | Columns |
|-------|---------|
| Time | `slot` (start), `month` (YYYYMM), `date`, `slot_of_day` (minutes since 00:00), `day_type` (weekday / saturday / sunday_holiday), `holiday`, `season` |
| Detector | `detector_id`, `direction` (S1), `district` (S2), `rain_district`, `latitude`, `longitude`, `road`, `n_lanes` |
| Traffic | `periods` (30-s periods seen), `coverage` (periods / possible), `speed` (km/h), `flow` (vehicles per hour, all lanes), `occupancy` (%), `interpolated` (P6) |
| Rain | `rain` (the value P7 / P8 choose), `rain_mid`, `rain_high`, `rain_max` (highest `high` of the 18 districts), `rain_lag1` (hour before), `rain_rule` (S3 `l2_rule`) |
| Warnings | `warn_level` (0–3), `warn_minutes` (since the warning episode began), `tc_signal` (0 or the highest signal in force) |
| Baseline | `dry`, `base_speed`, `base_flow`, `base_occupancy`, `base_n` (dry slots behind the baseline), `ratio` (speed / base speed), `flow_ratio` |

### Tables from `src.download` (reference; not read by L2 / L3)

Derived while downloading ([`processing.md`](processing.md), "Reference data").

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

### `day_manifest` — selected days (from `select-days`)

`data/interim/day_manifest.csv`: `date`, `role` (`event` / `control`),
`episode_ids`, `max_level`, `max_level_name`. Not used by the current pipeline; kept for later analysis.

---

## 4. Relationships

How L3 joins the L2 tables (`src/l3.py`):

```
l2/s1  (detector_id, time, lane_id)
   │  lane readings → detector × slot (P1–P6)
   ▼
l3 slot ──detector_id = AID_ID_Number──▶ l2/s2 detectors   (every S1 detector must be in S2)
   │                                        │ rain_district = district
   │  slot ∈ [period_start, period_end)     ▼
   ├────────────────────────────────▶ l2/s3 rain  (and the period before: rain_lag1)
   ├── slot ∈ [start, end) ─────────▶ l2/s4 rainstorm  (signals → episodes: warn_level, warn_minutes)
   ├── slot ∈ [start, end) ─────────▶ l2/s5 tc  (tc_signal)
   └── date ────────────────────────▶ l2/s6 holidays  (day_type)
```

`l2/s8` (daily rainfall at HKO HQ) is not joined; it is for day-level checks. The baseline
joins each slot to the dry slots of the same detector, season, day type and slot of day.

---

## 5. Known data issues

"Handling" is what the current pipeline does; the rules (D…, P…) are in
[`cleaning.md`](cleaning.md), which also lists the issues found while cleaning (e.g.
TDS90026, TDS90036, missing S3 hours, S5 summer time).

| Source | Issue | Handling |
|--------|-------|----------|
| S1 | Detector network grew: 42 detectors (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025) | Study months 2024-05, 2025-07, 2025-08; per-detector baselines (P10) |
| S1 | `s.d.` element missing before ~18 Nov 2021 | Outside the study months; L2 has no null `sd` |
| S1 | Snapshots per day vary by month (≈ 530–1,430) | Missing periods stay absent (not filled); L3 records `periods` / `coverage` per slot; 1–2 missing slots interpolated and flagged (P6) |
| S1 | File time ≠ measurement time: a file archived at 08:01 holds 07:53–07:54 | `time` = start of the period; L2 checks it is 0–60 min before the fetch time |
| S1 | A few archived files are truncated mid-document (1 of 919 on 29 Jul 2025) | The 3 truncated files stay out of L1 (D7) |
| S1 | The 00:00 period is published with the previous day's `<date>` | One day added (D6) |
| S1 | Adjacent files overlap (~9 % duplicate rows); bundles occasionally store a file twice | Byte-identical files are parsed once (manifest); L2 raises on a (detector, time, lane) twice |
| S1 | Only 1,730 of 2,880 periods per day present (~40 % missing) | As for snapshots above |
| S1 | When `volume = 0` (27.7 % of rows), `speed` holds a placeholder equal to the speed limit (70/80/100/50/110, s.d. = 0), not a measurement | Volume-weighted detector speed (P4) gives them no weight; a slot with no vehicle has no speed and is left out |
| S1 | `occupancy = -1` (60 rows), `speed` up to 300, `speed = 0` with `volume > 0` (5,991 rows on 5 Aug 2025) | `-1` (always with volume 0) → 0 (D21); speed 0 or > 130 with volume > 0 left out (P2) |
| S1 / S2 | 772 detectors report but S2 lists 807 (2026-04 version); S2 has 8 versions on disk (2021-08 .. 2026-04) | S2 version 2025-10 for all months (D2); every S1 detector must be in it (L3 raises otherwise); S1 `direction` is used (D1) |
| S2 | District spelling: `Central & Western` vs `Central and Western` (1 row); 97 % of `Road_EN` values have trailing spaces | Trimmed (D3); both spellings mapped to the HKO name (D11) |
| S2 / S3 | TD uses `Southern`, HKO uses `Southern District` (also Eastern, Islands, North, Central & Western) | Fixed map from the S2 name to the HKO name; an unknown name raises (D11) |
| S3 | Rainfall is a min–max range per district, not a point value | Midpoint by default; upper bound or territory maximum as alternatives (P7) |
| S3 | Free-text format; wording may vary over the years | A title or period in another form raises (L2 S3) |
| S4 / S5 | `24:00` end times; provisional rows after `UUUU` | `24:00` = next day 00:00 (D20); `provisional` kept as a column |
| S3 | Archive time ≠ bulletin time (file archived 20:02 holds the 19:02 bulletin); some bulletins are late (01:46) | The period comes from the rainfall sentence, dated by the bulletin's own time; bulletins for one period must agree (D10) |
| S6 | Each file covers only 3 years | All versions in L1; for each date the latest version that lists it (L2) |
| S7 | Forecast, not observation; starts ~Jul 2022 | Optional; L1 only, not used yet |
