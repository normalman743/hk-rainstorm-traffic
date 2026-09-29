# Database Description

This document describes every data source used in the project and the tables
we build from them: where each source comes from, what its raw fields mean, how it
is stored after preprocessing, and how the tables link together.

All sources were checked against the live services and the DATA.GOV.HK
Historical Archive in September 2026. All times are **Hong Kong Time (HKT, UTC+8)**,
stored without a time zone, unless stated otherwise.

---

## 1. Source inventory

"Downloaded" is what is on disk under `data/raw/` (inventory, locations and data dictionaries:
[`raw_data.md`](raw_data.md#inventory-on-disk-2026-09-29)). "Parsed" means `src.download` also derives
a table from it (§3). The processing pipeline is being rewritten; no source has processed tables yet.

| ID | Source (provider) | Access | Frequency | Downloaded | Role | Status |
|----|-------------------|--------|-----------|------------|------|--------|
| S1 | [Traffic Speed, Volume and Road Occupancy (Raw Data)](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), `rawSpeedVol-all.xml` (TD) | Historical Archive (`hkdata.download`) | 30 s periods, published every 1 min | 2024-01 .. 2025-12 (archive from Jun 2021; only 42 detectors until ~Nov 2021) | Target variables | **Required**; downloaded |
| S2 | [Locations of Traffic Detectors](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv), CSV (TD) | Historical Archive (`hkdata.download`, `src.download static-history`) | Versions | 8 versions, 2021-08 .. 2026-04 | Detector attributes, spatial join | **Required**; downloaded |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report), `CurrentWeather.xml` (HKO) | Historical Archive (`hkdata.download`) | Hourly | 2024-01 .. 2025-12 (archive from Jun 2021) | **District** past-hour rainfall | **Required**; downloaded |
| S4 | [Rainstorm Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml), `rstorm.dat` (HKO) | Direct download (`src.download warnings`) | Per event | since Mar 1998 | Warning state at each time | **Required**; downloaded; parsed |
| S5 | [Tropical Cyclone Warning Signals DB](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml), `tc.dat` (HKO) | Direct download (`src.download warnings`) | Per event | since 1946 | Exclude typhoon periods | **Required**; downloaded; parsed |
| S6 | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal), `en.json` (1823) | Direct download + Historical Archive (`src.download holidays`) | Yearly | 2018–2027 across archived versions | Working day / weekend / holiday | **Required**; downloaded; parsed |
| S8 | [Daily Total Rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall), `daily_HKO_RF_ALL.csv` (HKO) | Direct download (`src.download static`) | Daily | since 1884 | Day-level sanity checks | Auxiliary; downloaded |
| S9 | [Smart-lamppost traffic detectors](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts), `rawSpeedVol_SLP-all.xml` (TD) | Historical Archive (`hkdata.download`) | 30 s periods | 2024-01 .. 2025-12 | Extra detectors (same format as S1) | Optional; downloaded |
| S10 | Smart-lamppost detector locations, CSV (TD) | Historical Archive (`hkdata.download`) | Versions | 2023-12, 2024-01 | Attributes of S9 detectors | Optional; downloaded |
| S11 | Traffic Speeds of Road Network Segments (Processed Data), `irnAvgSpeed-all.xml` (TD) | Historical Archive (`hkdata.download`) | ~1 min | 2024-01 .. 2025-12 | TD's own segment speeds, cross-check | Optional; downloaded |
| S14 | [Road Network Segments](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv), `speed_segments_info.csv` (TD) | Historical Archive (`hkdata.download`, `src.download static-history`) | Versions | 6 versions, 2021-08 .. 2023-09 | Segment → route number for S11 | Optional; downloaded |
| S12 | [Road Network (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2), `RdNet_IRNP.gdb.zip` (TD) | Historical Archive (`hkdata.download`) | Versions | 2024-01 .. 2025-12 (34 versions) | Geometry of S11 segments (`ROUTE_ID`) | Optional; downloaded |
| S13 | [Special Traffic News (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2), `trafficnews.xml` (TD) | Historical Archive (`hkdata.download`) | Per message update | 2024-01 .. 2025-12 | Flag incidents / closures as confounders | Optional; downloaded |
| S7 | [Gridded Rainfall Nowcast](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv), CSV (HKO) | Historical Archive (`hkdata.download`) | ~every 15 min | 2024-01 .. 2025-12 (archive from ~Jul 2022) | Local (~2 km) rainfall proxy | Optional; downloaded |

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

**Processed tables: to be designed with the new pipeline.** The earlier ones (`traffic_lane`,
`traffic_15min`, `rainfall_district`, the planned `detectors`, `rainfall_grid` and `calendar`, the
`coverage` log and the validation report) were removed on 2026-09-29 with the code that built
them; their definitions are in the git history before that date.

What is on disk now, besides the raw files, are the small tables `src.download` derives
(how: [`processing.md`](processing.md)). PK = primary key.

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
`episode_ids`, `max_level`, `max_level_name`. Not used by the new pipeline; kept for later analysis.

---

## 4. Relationships

The earlier design, to be revisited with the new pipeline:

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

"Handling" is what the earlier pipeline did; the new pipeline decides again.

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
| S1 / S2 | 772 detectors report but S2 lists 807 (2026-04 version); S2 has 8 versions on disk (2021-08 .. 2026-04) | Use the version in force; inner join; report unmatched IDs |
| S2 | District spelling: `Central & Western` vs `Central and Western` (1 row); 97 % of `Road_EN` values have trailing spaces | Normalise, strip |
| S2 / S3 | TD uses `Southern`, HKO uses `Southern District` (also Eastern, Islands, North, Central & Western) | Strip the ` District` suffix, normalise `and` → `&` |
| S3 | Rainfall is a min–max range per district, not a point value | Choice of min / mid / max = experiment P7 |
| S3 | Free-text format; wording may vary over the years | Regex parser with unit tests on samples from each year |
| S4 / S5 | `24:00` end times; provisional rows after `UUUU` | Handled in parser |
| S3 | Archive time ≠ bulletin time (file archived 20:02 holds the 19:02 bulletin); some bulletins are late (01:46) | Use the bulletin's own timestamp; anchor the period to it |
| S6 | Each file covers only 3 years | Merge archived versions, deduplicate by date |
| S7 | Forecast, not observation; starts ~Jul 2022 | Optional sensitivity check only |
