# Raw Data Dictionary

> 中文版：[`raw_data.zh.md`](raw_data.zh.md)

This document describes every **raw** data source as it is published: where it comes
from, how it is accessed, its format and structure, what every field means, which
values actually occur, and the quirks found when we inspected real data. Processed
tables are described in [`processing.md`](processing.md) and
[`database_description.md`](database_description.md).

Figures quoted as "observed" come from a read-only audit of real data in September 2026
(traffic: 5 Aug 2025, a Black Rainstorm day, unless stated otherwise).

All times are **Hong Kong Time (HKT, UTC+8)** unless stated otherwise.

## Inventory (on disk, 2026-09-29)

Everything below is under `data/raw/`. **Main** = needed by the core analysis;
**optional** = extensions (segment speeds, smart lampposts, incidents, radar nowcast).

| ID | Data | Provider | Time resolution | Spatial unit | On disk | Size | Tier |
|----|------|----------|-----------------|--------------|---------|------|------|
| [S1](#s1-traffic-detector-readings-rawspeedvol-allxml) | Traffic detector readings (speed, volume, occupancy) | TD | 30 s periods | lane × detector (~790 detectors) | 2024-01 .. 2025-12, monthly bundles | 23 GB | main |
| [S2](#s2-traffic-detector-locations-traffic_speed_volume_occ_infocsv) | Traffic detector locations | TD | versions | detector | 2021-08 .. 2026-04, 8 versions | 0.3 MB | main |
| [S3](#s3-current-weather-report-currentweatherxml) | Current Weather Report (district rainfall) | HKO | hourly | 18 districts (min–max mm) | 2024-01 .. 2025-12, monthly bundles | 28 MB | main |
| [S4](#s4-rainstorm-warning-signals-rstormdat) | Rainstorm warning signals | HKO | per signal | Hong Kong | 1998-04 .. 2026-08 | 37 kB | main |
| [S5](#s5-tropical-cyclone-warning-signals-tcdat) | Tropical cyclone signals | HKO | per signal | Hong Kong | 1946 .. 2026-09 | 136 kB | main |
| [S6](#s6-public-holidays-enjson) | Public holidays | 1823 | per day | Hong Kong | 10 versions 2019-07 .. 2026-05 (covering 2018 .. 2027) | 31 kB | main |
| [S8](#s8-daily-total-rainfall-daily_hko_rf_allcsv) | Daily total rainfall | HKO | daily | 1 station (HKO HQ) | 1884-03 .. 2026-08 | 0.8 MB | main |
| [S9](#s9-smart-lamppost-detector-readings-rawspeedvol_slp-allxml) | Smart-lamppost detector readings | TD | 30 s periods | lane × detector (17 reporting) | 2024-01 .. 2025-12, monthly bundles | 0.9 GB | optional |
| [S10](#s10-smart-lamppost-detector-locations-traffic_speed_volume_occ_info-slpcsv) | Smart-lamppost detector locations | TD | versions | detector | 2023-12, 2024-01 | 8 kB | optional |
| [S11](#s11-segment-speeds-irnavgspeed-allxml) | Segment speeds (TD processed) | TD | ~1 min snapshots | road segment (~4,400) | 2024-01 .. 2025-12, monthly bundles | 13 GB | optional |
| [S14](#s14-road-network-segments-speed_segments_infocsv) | Segment → route number | TD | versions | road segment | 2021-08 .. 2023-09, 6 versions | 0.2 MB | optional |
| [S12](#s12-road-network-2nd-generation-rdnet_irnpgdbzip) | Road network geometry (FGDB) | TD | versions (34 in 2024–25) | road centreline (35,837) | 2024-01 .. 2025-12, monthly bundles | 0.6 GB | optional |
| [S13](#s13-special-traffic-news-trafficnewsxml) | Special traffic news (incidents, closures) | TD | per message update | location text; some with district / lat-lon | 2024-01 .. 2025-12, monthly bundles | 61 MB | optional |
| [S7](#s7-gridded-rainfall-nowcast) | Gridded rainfall nowcast (radar **forecast**) | HKO | every 15 min, +30 .. +120 min | ~2 km grid, 121 × 121 | 2024-01 .. 2025-12, monthly bundles | 12 GB | optional |

IDs: **S** = a source we use; **N** = one we cannot or do not use. (S14 was N1 until
2026-09-29, when it came into use for S11.)

Since 2026-09-30 only three months of S1, S7, S9 and S11 are on disk: 2024-05, 2025-07 and 2025-08,
the months processed first (3.1, 1.8, 0.1 and 1.7 GB). The other 21 bundles of each (46.5 GB)
were deleted and can be downloaded again with the plans below; the list is in
`data/interim/deleted_bundles.txt`.

Not obtainable for the past: [N2 station hourly rainfall](#n2-automatic-weather-station-hourly-rainfall-hourlyrainfallphp)
and HKO's JSON Current Weather Report (`weather.php?dataType=rhrread`); neither is in the Historical Archive.

### Where the files are, and how they were downloaded

Two downloaders, by where the data comes from:

**`hkgovdata.download` (DATA.GOV.HK Historical Archive)** — S1, S2 (3 versions), S3, S6 (10 versions), S7, S9–S14 (S14: 1 version).
Driven by the plans in `plans/`; layout `data/raw/<url host>/<url path>/`:

| Plan | Contents | Size |
|------|----------|------|
| `2024_2025_main.json` | S1, S3, S13, S2 (2022-03, 2024-02, 2025-10), S14 (2023-09), S6 (10 versions, 2019-07 .. 2026-05) | 25.2 GB |
| `2024_2025_optional.json` | S11, S9, S7, S10 | 28.1 GB |
| `road_network_2024_2025.json` | S12 | 0.6 GB |

```bash
python -m hkgovdata.download run plans/2024_2025_main.json --out data/raw
```

The S6 entry was added on 2026-09-30 and downloaded one version per plan: run as one plan, its
10 size queries go out in parallel and the archive dropped some of the connections (SSL EOF).

```
<url host>/<url path>/bundle/<YYYYMMDD>.zip          the archive's monthly bundle, as downloaded
<url host>/<url path>/data-dictionary/<date>/<name>  the archive's data dictionary versions
<url host>/<url path>/schema/<date>/<name>           the archive's schema versions (S13 only)
```

Inside a bundle every member is `<url-encoded folder>/<YYYYMMDD-HHMM>-<file name>`: the
archive time of one snapshot. Each bundle also holds a ~3 kB `<date>-0000-data-dictionary.pdf`,
which only says "use get-data-dictionary"; the real dictionaries are in `data-dictionary/`.

**`src.download` (the older downloader)** — what the Historical Archive does not have, or
versions the plans do not include:

| Command | Writes | Data |
|---------|--------|------|
| `warnings` | `hko/rstorm.dat`, `hko/tc.dat` (+ parsed `rainstorm_warnings.csv`, `tc_signals.csv`) | S4, S5 (not on DATA.GOV.HK). The text is decoded and written back, which drops a byte-order mark; nothing else changes |
| `static` | `hko/daily_HKO_RF_ALL.csv`, `td/traffic_speed_volume_occ_info.csv` | S8; S2 live copy (= its 2026-04 version) |
| `static-history` | `td/traffic_speed_volume_occ_info/<YYYYMMDD>.csv`, `td/speed_segments_info/<YYYYMMDD>.csv` | S2 2021-08 .. 2021-12 and 2026-04; S14 2021-08 .. 2022-10 |
| `holidays` | `calendar/public_holidays.csv` | S6, all archived versions merged (later versions win). Derived, not raw: L1 reads the archived versions |

Versions in both places were checked byte for byte and the `src.download` copies deleted.
Their data dictionaries were saved by hand into `hko/data-dictionary/`,
`calendar/data-dictionary/` and `td/data-dictionary/` (see [Data dictionaries](#data-dictionaries)).
The 4 S6 dictionaries in `calendar/data-dictionary/` are byte-identical to the ones the plan now
downloads.

---

## How historical files are obtained

The live URLs of S1 and S3 always return the *latest* file. Past versions come from the
[DATA.GOV.HK Historical Archive API](https://data.gov.hk/en/help/api-spec):

| Endpoint | Parameters | Returns |
|----------|------------|---------|
| `https://app.data.gov.hk/v1/historical-archive/list-file-versions` | `url` (live URL), `start`, `end` (`YYYYMMDD`) | JSON: `timestamps` (one per archived version, `YYYYMMDD-HHMM`), `data-files` (ZIP bundles, usually one per month), `data-dictionary-dates` |
| `https://app.data.gov.hk/v1/historical-archive/get-file` | `url`, `time` | HTTP 302 redirect to the file. `time=YYYYMMDD-HHMM` gives one snapshot; `time=YYYYMMDD` (a bundle's timestamp) gives the whole bundle ZIP |
| `https://app.data.gov.hk/v1/historical-archive/get-data-dictionary` | `url`, `date` | HTTP 302 to the data dictionary in force on `date` (the latest version on or before it) |
| `https://app.data.gov.hk/v1/historical-archive/get-schema` | `url`, `date` | Same, for the schema (e.g. XSD) |

A traffic bundle is ~1 GB per month. Its members are named
`<url-encoded live URL>/<YYYYMMDD-HHMM>-rawSpeedVol-all.xml`. `hkgovdata.download` keeps whole
monthly bundles (see [Inventory](#inventory-on-disk-2026-09-29)); it can also take single days
out of a bundle with HTTP range requests. Its module docstring records how every endpoint
answered in tests.

**Archive time ≠ measurement time.** A version's timestamp is when the archive captured the
file, not when it was measured (see S1 and S3).

---

## Data dictionaries

Every source has its official data dictionary next to it, in a `data-dictionary/` folder
(file names keep the archive's `<date>-` prefix). Several versions are kept where the
dictionary changed during 2024–2025. Many versions are byte-identical after text extraction;
the table names the distinct ones.

| Source | Dictionary (under `data/raw/`) | Distinct content |
|--------|--------------------------------|------------------|
| S1, S2, S11, S14 | `dataspec-traffic-data-strategic-major-roads.pdf` in each resource folder and `td/data-dictionary/` (20210812, 20211118, 20240418) | 20211118 → 20240418 (last update 30 Nov 2022): only wording (`valid`, occupancy definition); structure unchanged |
| S9, S10 | `dataspec-traffic-data-slp.pdf` (20231228, 20240418) | one: same XML structure as S1 |
| S3 | `HKO_Open_Data_API_Documentation.pdf` (11 versions) | three; it documents the JSON API, **not the RSS file** we use |
| S4, S5 | `hko/data-dictionary/hko-webpage-warndb3.shtml.html`, `…warndb1.shtml.html` | **no official dictionary**: the HKO database web pages, saved 2026-09-29 (notes on provisional records, signal-number history) |
| S6 | `www.1823.gov.hk/common/ical/en.json/data-dictionary/…-1823_cal_dictionary.pdf` (4 versions; identical copies in `calendar/data-dictionary/`) | – |
| S7 | `HKO_gridded_rainfall_nowcast_documentation.pdf` (6 versions) | one |
| S8 | `hko/data-dictionary/20250227-data_dictionary_daily_total_rainfall.pdf` | – |
| S12 | `rdnet_dataspec.zip` (5 versions): one PDF each for FGDB, GML, KML | – |
| S13 | `Data_Specification_for_STN_Eng_v4.0.pdf` (2 versions) + `schema/20210608/20210608-trafficnews.xsd` | one |

Found while reading them:

| Finding | Detail |
|---------|--------|
| `valid` = detector online / offline | S1/S9: the 2022 dictionary defines `Y` as "Detector Online" and `N` as "Detector Offline" (2021: "valid / non-valid") |
| Dictionary column names ≠ files | S2 is documented as `Device_ID`, the file has `AID_ID_Number`; S14 as `segment_id`, `road name`, the file has `irn_id`, `ucase(route)`. The files are what we use |
| S3 format undocumented | The RSS bulletin is free text; our parser fails loudly on anything unexpected (see S3) |
| Truncated dictionary files in the archive | 6 versions lack the PDF end marker `%%EOF` (HKO API documentation 20240921, 20241022, 20241116, 20250311; gridded nowcast 20240921, 20241010); the next day's version is complete |
| Broken archive links | Dictionary versions 20221214 (TD strategic roads) and 20240229 (HKO API) redirect to files the storage host does not have (404), so they are not on disk; S14 has 20211118 and 20240418 instead |

---

## S1. Traffic detector readings (`rawSpeedVol-all.xml`)

| | |
|---|---|
| Dataset | [Traffic Data of Strategic / Major Roads](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), resource "Traffic Speed, Volume and Road Occupancy (Raw Data)" |
| Live URL | `https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml` |
| Schema | [`SpeedVolOcc-BR.xsd`](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/SpeedVolOcc-BR.xsd) |
| Published | every minute; each file holds **two 30-second periods** |
| Archived | from **June 2021**. Snapshots per day vary by month, ≈ 530–1,430 (e.g. 946 on 5 Aug 2025) |
| Size | ~710 kB per file; ~670 MB per day uncompressed, ~31 MB compressed |
| Detectors | 42 (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025) |

### Structure

```xml
<raw_speed_volume_list>
  <date>2025-08-05</date>
  <periods>
    <period>
      <period_from>07:53:00</period_from><period_to>07:53:30</period_to>
      <detectors>
        <detector>
          <detector_id>AID01101</detector_id>
          <direction>South East</direction>
          <lanes>
            <lane>
              <lane_id>Middle Lane</lane_id>
              <speed>43</speed><occupancy>1</occupancy><volume>2</volume>
              <s.d.>5.7</s.d.><valid>Y</valid>
            </lane>
            ... one <lane> per lane ...
          </lanes>
        </detector>
        ... ~770 detectors ...
      </detectors>
    </period>
    <period> ... the next 30 seconds ... </period>
  </periods>
</raw_speed_volume_list>
```

One reading = one lane of one detector in one 30-second period (~4,200 readings per file).

### Fields

| Level | Field | Type | Unit | Official description (XSD) | Meaning and observed values |
|-------|-------|------|------|----------------------------|-----------------------------|
| file | `date` | date | – | Date of the data | Measurement date. **Wrong for the 00:00 period** (see quirks) |
| period | `period_from` | time | – | Timestamp of data period starts | Start of the 30-s period, `HH:MM:00` or `HH:MM:30` |
| period | `period_to` | time | – | Timestamp of data period ends | Always `period_from` + 30 s (redundant) |
| detector | `detector_id` | string | – | Reference ID for AID | e.g. `AID01101`, `TDS90070`, `TDSIEC10001`. Joins to S2 `AID_ID_Number` |
| detector | `direction` | string | – | Direction of AID | e.g. `South East`; the 8 values of S2 `Direction`, and `North ` / `South ` with a trailing space (3 detectors each). One direction per detector within a month. **Not always the S2 `Direction`** (see quirks) |
| lane | `lane_id` | string | – | Reference ID for Lane of AID | 7 labels: `Fast Lane` (37 %), `Slow Lane` (35 %), `Middle Lane` (20 %), `Middle Lane 1`–`4` (wide roads) |
| lane | `speed` | integer | km/h | Average speed of lane | 0–300, median 70. **When `volume = 0` it is a placeholder** (see quirks) |
| lane | `occupancy` | integer | % | Occupancy of lane | Share of the period a vehicle is over the detector. 0–100; 37 % of readings are 0; also `-1` |
| lane | `volume` | integer | vehicles / 30 s | – | 0–61; 27.7 % of readings are 0 |
| lane | `s.d.` | decimal | km/h | – | Standard deviation of speed; 55 % are 0 (no or one vehicle). **Missing before ~18 Nov 2021** |
| lane | `valid` | `Y`/`N` | – | Data validity: Detector Online `Y`, Detector Offline `N` (data dictionary, 2022) | `N` on 0.5 % of readings. `N` rows have normal-looking values, so only the flag identifies them |

### Quirks (observed)

| Quirk | Evidence | Consequence |
|-------|----------|-------------|
| Archive time ≠ measurement time | File archived 08:01 holds 07:53:00–07:54:00 (lag ~5–10 min) | Use `period_from`, never the file name |
| Missing periods | 1,730 of 2,880 periods per day present on 5 Aug 2025 (~40 % missing). Over the three checked months 27.0 % (2024-05), 46.6 % (2025-07), 41.0 % (2025-08) are missing; the longest gap is 35 min (2024-05-30), at most 10 min in 2025. Every distinct file holds two periods, so the missing periods are the minutes the archive did not fetch | Missing data = **absent rows**, not NA |
| Identical copies | The archive often stores the same file at two or more fetch times (e.g. 00:07 and 00:10 on 5 Aug 2025): 113 extra copies of 32,718 members in 2024-05, 2,261 of 26,101 in 2025-07, 2,096 of 28,445 in 2025-08. The same member name also occurs twice (30 / 6 / 43 names), always with the same bytes | Read one file per group of identical files (`src.clean.manifest`); the file names keep every fetch time |
| No overlap between distinct files | Once identical copies are grouped, each 30-s period is in exactly one file (all three months), except the periods of the truncated files below. The ~9 % repeated rows seen on 5 Aug 2025 came from identical copies, not from overlapping files | Nothing to deduplicate by (time, detector, lane) |
| Midnight date | The 00:00 period carries the **previous day's** `<date>`: all 83 files holding 00:00:00 and 00:00:30 in the three months, fetched 00:06–00:10, say the day before | Re-date using the archive time |
| Truncated files | A few files end mid-document: 3 in the three months (fetched 2025-07-17 14:18, 2025-07-29 10:28, 2025-08-11 02:00). Each is cut after exactly 393,216 or 196,608 bytes (384 / 192 KiB) and is a byte-for-byte prefix of a complete file fetched 1–3 minutes away | Skip them |
| Same lane twice | TDS90026 lists two lanes called `Middle Lane` (direction `West`), with different values, in nearly every file of 2025-07 and 2025-08 (49,590 files). AID02215 lists `Fast Lane` and `Slow Lane` twice in one period (2024-05-30 08:25:00) | The lanes cannot be told apart by `lane_id`; open question |
| Direction missing | `<direction>` is absent for AID09115, AID09116, AID90008 and AID90009 (four new detectors on Tai Po Road, Sha Tin) in every file up to 2025-07-25 10:34:30 (268,072 readings; AID09115 from the start of the 2025-07 bundle, the others from 07-03). From 10:36:00 it is present: `East`, `East`, `West`, `West`. S2 lists them only from its 2025-10 version, with the same directions. No other S1 field is ever absent or empty, and every number, date and time is well-formed | Direction from S2 2025-10 or the later S1 files; open question |
| Direction ≠ S2 | Against S2 2024-02 and 2025-10 (same result for both), `direction` differs from `Direction` for 139 detectors in 2024-05 and 142 in 2025-07 / 2025-08: 123–126 by 45° (e.g. AID04107 `North East`, S2 `East`), 8 by 90°, 1 by 135°, 1 by 180° (AID10120 `North East`, S2 `South West`, "Shenzhen Bay Bridge - Northbound"); 6 only by the trailing space (AID05114/5115/5117 `North `, AID05210/5221/5222 `South `). `data/interim/checks/versions_directions.csv` | Which one to use is open |
| Schema change | `<s.d.>` appears from ~18 Nov 2021 (data dictionary `20211118`) | `sd` missing earlier |
| Placeholder speed | With `volume = 0`, `speed` is 70 / 80 / 100 / 50 / 110 (the speed limit) and `s.d.` = 0 in 99.9 % of cases | Not a measurement |
| Contradictions | `speed = 0` with `volume > 0`: 5,991 readings; `occupancy = -1`: 60 | Cleaning rule needed |
| Out of range | `speed > 130`: 15,711 readings (0.4 %), mostly 131–136 in the fast lane; max 300 | Cleaning rule needed |
| Stuck sensor or standstill? | `occupancy = 100`: 1,533 readings, 1,415 with speed = volume = 0. TDSLTR20004 reads 100 % from 06:34 to 15:26 on 5 Aug 2025, during the Black Rainstorm | Needs judgement: sensor fault or flooded road |
| Partial reporting | AID01133 reports only after 20:45 on 5 Aug 2025 (219 periods) | Per-detector coverage matters |

The figures for the three months (2024-05, 2025-07, 2025-08; 332.9 M readings) come from
`python -m src.clean.manifest`, `src.clean.s1_periods` and `src.clean.s1_rows`; their tables are in
`data/interim/checks/`.

---

## S2. Traffic detector locations (`traffic_speed_volume_occ_info.csv`)

| | |
|---|---|
| URL | `https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv` |
| Format | CSV, UTF-8 with BOM, 807 rows × 11 columns (2026-04 version), one row per detector |
| History | 8 archived versions on disk: 2021-08, 2021-09, 2021-11, 2021-12, 2022-03 (700 rows), 2024-02 (786), 2025-10 (790), 2026-04 (807). Use the version in force at the time analysed |

| Field | Type | Description | Observed |
|-------|------|-------------|----------|
| `AID_ID_Number` | string | Detector ID; joins to S1 `detector_id` | 807 unique, no NA. Every detector seen in S1 is listed; 35 listed detectors did not report on 5 Aug 2025 |
| `District` | string | One of the 18 districts | 19 spellings: `Central & Western` (13) **and** `Central and Western` (1). Largest: Yuen Long 131, Sha Tin 105 |
| `Road_EN`, `Road_TC`, `Road_SC` | string | Location text: road, landmark, direction | 97 % end with a **trailing space**. Two names are shared by two detectors each (AID04108/AID04121, AID04109/AID04122, ~30 m apart), so join on the ID, never on the name |
| `Easting`, `Northing` | integer | Hong Kong 1980 Grid coordinates | metres |
| `Latitude`, `Longitude` | float | WGS84 | 22.25–22.51 N, 113.94–114.27 E |
| `Direction` | string | "Direction of the detector" (data dictionary; S1 `direction` is described the same way) | 8 values: `West` 127, `North West` 117, `South East` 114, `East` 108, `North East` 105, `South` 85, `South West` 79, `North` 72 |
| `Rotation` | integer | "Direction of the detector in degree" (data dictionary, which gives the type as string) | 0–355 |

**Checked on all 8 versions** (`src.clean.versions_parse` → `data/interim/l1/s2/<version>.parquet`,
`src.clean.versions_checks` → `data/interim/checks/versions_*.csv`):

| Check | Result |
|-------|--------|
| Files | Every version: UTF-8 with BOM, comma-separated, CRLF, the same 11 columns; every row has 11 fields; no value empty. The live copy (`data/raw/td/traffic_speed_volume_occ_info.csv`) is byte-identical to 2026-04 |
| Values | `AID_ID_Number` unique in every version. `Easting`, `Northing`, `Rotation` always integers, `Latitude`, `Longitude` always decimals |
| Spaces | `Road_EN` ends with a space (never starts with one) in every row of 2021-08 .. 2021-11 and 2024-02; in 582 of 614 (2021-12), 647 of 700 (2022-03), 786 of 790 (2025-10), 786 of 807 (2026-04): the detectors added later have none. `Road_TC`, `Road_SC`: 4–7 fewer rows with a leading or trailing space. `Direction` `South ` with a trailing space in 2021-11 .. 2022-03 (TDS30004, TDS30005; also TDS30002 in 2022-03) |
| Spellings | `District` in 2022-03 only: `Yeun Long` (21 rows), `Island` (2), `Kwai Chung` (1). `Central and Western` (TDSIEC10001, from 2024-02) beside `Central & Western` |
| IDs with slashes | 2022-03 only: 54 IDs are written with slashes (`TDS/IEC/20001`); 2024-02 has the same 54 without them (`TDSIEC20001`), same road names apart from the trailing space, 53 at the same coordinates. S1 of the three months has no ID with a slash |
| Changes | 2021-08 → 2021-09 → 2021-11 → 2021-12 → 2022-03: only additions (79, 147, 36, 86) and 2, 13 changed rows. 2022-03 → 2024-02: 141 added (54 of them the renamed IDs above), 55 removed, 231 changed (`Road_EN` 177, 100 of them only the trailing space; `Rotation` 26; `Direction` 20; `Latitude`/`Longitude` 17; `District` 16). 2024-02 → 2025-10: 4 added (AID09115, AID09116, AID90008, AID90009). 2025-10 → 2026-04: 17 added (AID09301 .. AID09409). Nothing else changed |
| Against S1 | Every detector of S1 2024-05 is in 2024-02; the 4 detectors added in 2025-10 report in S1 2025-07 / 2025-08, so for those months 2024-02 lacks them. No S1 detector is missing from every version. `Direction` differs from S1 `direction` for 139–142 detectors (S1 quirks) |

---

## S3. Current Weather Report (`CurrentWeather.xml`)

| | |
|---|---|
| Dataset | [Current weather report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report) |
| Live URL | `https://rss.weather.gov.hk/rss/CurrentWeather.xml` |
| Format | RSS 2.0; the content is **free text in HTML** inside `<description><![CDATA[ ... ]]>` |
| Published | hourly bulletin, archived ~24 times a day from June 2021 |
| Size | ~2 kB per file |

### Structure

| Element | Content | Example |
|---------|---------|---------|
| `item/title` | Issue time of the bulletin (HKT) | `Bulletin updated at 08:02 HKT 05/08/2025` |
| `item/pubDate` | Same moment, in **GMT** | `Tue, 05 Aug 2025 00:02:00 GMT` |
| `item/category` | Weather category code | `R` |
| `description` | Observation hour, HKO temperature, humidity | `At 8 a.m. at the Hong Kong Observatory: Air temperature: 25 degrees Celsius; Relative Humidity: 95 per cent` |
| `description` | Warning messages in force | `The Black Rainstorm Warning Signal has been issued.` |
| `description` | Temperatures at ~25 stations | `King's Park 24 degrees; ...` |
| **`description`** | **Past-hour rainfall by district** | `Between 6:45 and 7:45 a.m., lightning was detected over all regions. The rainfall recorded in various regions were: Southern District 27 to 60 mm; Wan Chai 24 to 38 mm; Kwun Tong 1 mm; ...` |

The rainfall sentence is what we use. Its format is identical in samples from 2021 to 2025.
- Each entry is `<District> <min> to <max> mm`, or `<District> <value> mm` when all gauges agree.
  The values are the minimum and maximum over the rain gauges in that district.
- Districts **without rain are not listed**. When no district had rain, **the whole sentence is
  missing**. This was checked against S8: 0.0 mm on the dry days whose bulletins lack the sentence.
- The period is stated in the sentence and ends at HH:45. It is **not** the "At 8 a.m." hour.
  Periods can cross midnight or noon: `Between 11:45 p.m. and 0:45 a.m.`, `Between 11:45 a.m. and 12:45 p.m.`.
- District names use the HKO spelling: `Southern District`, `Eastern District`, `Islands District`,
  `North District`, `Central & Western District`. The other 13 match S2.
- Bulletins are usually issued ~17 min after the period ends, occasionally later (e.g. 01:46).
  The archive can capture a bulletin up to an hour after it was issued (the file archived at 20:02 held the 19:02 bulletin).

As written in the file, the sentence is followed by an HTML table, one row per district:

```html
Between 6:45 and 7:45 a.m., lightning was detected over all regions. The rainfall recorded in various regions were:<br/><br/>
<table border="0" cellspacing="0" cellpadding="0">
  <tr><td>Islands District</td><td width="100" align="right">7 to 50&nbsp;mm;</td></tr>
  ...
  <tr><td>Tuen Mun</td><td width="100" align="right">1 to 13&nbsp;mm.</td></tr>
</table>
```

Without lightning the sentence reads `Between 6:45 and 7:45 a.m., the rainfall recorded in various regions were:`.
The lightning part names regions (`over all regions`, `within Lantau, New Territories East, Hong Kong and Kowloon`, ...).

**Checked on 2024-05, 2025-07, 2025-08** (`src.clean.s3_parse`, `src.clean.s3_checks`; 2,231 bulletins, 6,818 rain rows):

| Check | Result |
|-------|--------|
| Structure | Every file: one `<item>` with `author`, `guid`, `pubDate`, `title`, `category`, `link`, `description`; nothing absent or empty. `category` is always `R`. Every rainfall sentence has one of the two forms above, every row `<District> <n> to <n> mm` or `<District> <n> mm` |
| Times | `title`, `pubDate` (+ 8 h) and the time in `guid` always agree. Updated at HH:02 in 2,215 bulletins; also HH:06 (12), :04 (2), :00 and :11 (1 each, 2025-07-18). Fetched 0–63 min after the update, median 4–5 min |
| Hours | Every hour has a bulletin except 2025-07-18 18:00 (the 17:11 bulletin was still current at 18:06), 2025-08-18 23:00 (the file fetched 23:05 held the 22:02 bulletin again, see below) and 2025-08-23 12:00 (no file fetched between 11:05 and 13:05) |
| Same bulletin twice | 2025-08-18 22:02 is in two files; the descriptions differ only in the weather icon (`pic63.png` → `pic64.png`) |
| Rain period | Always HH:45 to HH:45, 60 min, ending 10–29 min before the update (one 75 min: the 17:00 bulletin of 2025-07-18 repeats the 16:02 bulletin's period, with the same values) |
| Districts | 18 names in the HKO spelling (above); none twice in one bulletin; `low` ≤ `high`; single values (`high` absent) in 218 rows. 812 bulletins have rain, 129 of them in all 18 districts |

---

## S4. Rainstorm warning signals (`rstorm.dat`)

| | |
|---|---|
| Web page | [Rainstorm Warning Signals database](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) |
| Data file | `https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat` (the file behind the page) |
| Format | Tab-separated, **no header**, one line per signal; 974 signals since 12 Apr 1998 |

Example line: `R	2026	8	27	5	5	2026	8	27	9	20	04	15` (Red, 27 Aug 2026 05:05 – 09:20, 4 h 15 min).

| Column | Description | Observed |
|--------|-------------|----------|
| 1 | Colour: `A` Amber, `R` Red, `B` Black | 778 Amber, 161 Red, 35 Black |
| 2–6 | Start: year, month, day, hour, minute | – |
| 7–11 | End: year, month, day, hour, minute | Midnight can be written **`24:00`** (2 cases) |
| 12–13 | Duration: hours, minutes | 10 min – 17 h 25 min |

A line `UUUU` marks where provisional records begin; currently it is the last line, so no
record is provisional. An upgrade (Amber → Red → Black) ends one signal at the minute the
next starts; we merge such chains into **episodes**. For 2022–2025 the episodes by highest
level are:

| Year | Amber | Red | Black |
|------|-------|-----|-------|
| 2022 | 19 | 2 | 0 |
| 2023 | 23 | 5 | 2 |
| 2024 | 37 | 4 | 0 |
| 2025 | 24 | 6 | 4 |

**L1** (`src.clean.signals_parse`): `data/interim/l1/s4/rstorm.parquet`, one row per line: `line`,
the 13 columns above (named `colour`, `start_year` .. `duration_minutes`), `trailing_tabs`;
strings as written.

| Check (`src.clean.structure`) | Result |
|-------|--------|
| Lines | 975: 974 signals, then `UUUU` (line 975). Every value has the presumed form: colour `A` / `R` / `B`, years 4 digits, all other fields 1–2 digits |
| Trailing tabs | Lines 1–28 (1998) end with a tab, i.e. an empty 14th field |

---

## S5. Tropical cyclone warning signals (`tc.dat`)

| | |
|---|---|
| Web page | [Tropical Cyclone Warning Signals database](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml) |
| Data file | `https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat` |
| Format | Tab-separated, **no header**, 2,512 lines since 1946 (1,262 cyclone signals + 1,250 other rows), then `UUUU`. Served as UTF-8 with BOM; `src.download warnings` saves it without the BOM |

Example line: `202603	SuperT	SAUDEL	1	X	1810	31	8	2026	X	010	4	9	2026	X	7800`.

| Column | Description | Observed |
|--------|-------------|----------|
| 1 | Cyclone code (year + number) | 483 cyclones |
| 2 | Intensity: `TD` tropical depression, `TS` tropical storm, `STS` severe tropical storm, `T` typhoon, `ST` severe typhoon, `SuperT` super typhoon; combined codes such as `TST`, `TSupT`, `TD/TD` also occur (not documented). **`MSN` rows are not cyclone signals** (1,250 rows; skipped) | `T` 394, `STS` 231, `TSupT` 178, `TS` 177, `TST` 113, `SuperT` 71, `TD` 56, `ST` 41 |
| 3 | Name; `NIL` = unnamed | 109 unnamed |
| 4 | Signal: 1, 3, 8, 9, 10 | 1: 538, 3: 428, 8: 242, 9: 35, 10: 19 |
| 5 | Direction of No. 8 signal (`NE`/`NW`/`SE`/`SW`); `X` otherwise; `*` in some old records; a compass point in `MSN` rows | see the checks below |
| 6 | Start time `HHMM` (leading zeros dropped: `10` = 00:10; `2400` = midnight) | – |
| 7–9 | Start day, month, year | – |
| 10 | Flag `X` / `S` (undocumented; `S` only in old records) | – |
| 11 | End time `HHMM` | – |
| 12–14 | End day, month, year | – |
| 15 | Flag, as column 10 | – |
| 16 | Duration `HHHMM` (`7800` = 78 h 00 min) | – |

**L1** (`src.clean.signals_parse`): `data/interim/l1/s5/tc.parquet`, one row per line: `line`, the
16 columns above (named `cyclone`, `intensity`, `name`, `signal`, `direction`, `start_time` ..
`duration`), `trailing_tabs`; strings as written, nothing trimmed.

| Check (`src.clean.structure`) | Result |
|-------|--------|
| `MSN` rows | 1,250, all with `cyclone` `0` and `signal` `0`. Their `direction` is a compass point in 1,116: `E` 659, `N` 426, `ENE` 14, `S` 10, `NNE` 5, `SSW` 1, `SSE` 1; the other 134 have one of `NE` / `NW` / `SE` / `SW` / `X` |
| `*` direction | 24, all in cyclone rows (`TS` 10, `TD` 7, `TSupT` 3, `T` 2, `TST` 2) |
| Names | 20 with a hyphen (e.g. `KAI-TAK`, `MA-ON`, `NOCK-TEN`). Line 2290: intensity `TD/TD`, name `no name(E)(5-6Jul2021)/ no name(W)(5-8Jul2021)`, two unnamed depressions in one record |
| Trailing spaces | In lines 1695–1702 (2005, `MSN` rows): days `3 `, `4 `; times `915 `, `445 `; durations `900 `, `550 `, `200 ` |
| Trailing tabs | Lines 1681 and 1732 end with one tab, line 1733 with two |
| Otherwise | Every value has the presumed form: times 1–4 digits, days and months 1–2, years 4, flags `X` / `S`, durations 1–5 digits |

---

## S6. Public holidays (`en.json`)

| | |
|---|---|
| Dataset | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) |
| Live URL | `https://www.1823.gov.hk/common/ical/en.json` (also `tc.json`, `sc.json`) |
| Format | iCalendar-style JSON, UTF-8 with BOM |
| Coverage | **Each file covers three years** (the live file: 2025–2027). The 10 archived versions since 2019 together cover 2018–2027 |
| On disk | The 10 archived versions: `www.1823.gov.hk/common/ical/en.json/bundle/<YYYYMMDD>.zip`, 2019-07 .. 2026-05, one `<YYYYMMDD-HHMM>-en.json` each. `calendar/public_holidays.csv` merges them (derived) |

Structure: `vcalendar[0].vevent[]`, one object per holiday:

| Field | Description | Example |
|-------|-------------|---------|
| `dtstart` | `[date, {"value": "DATE"}]`, the holiday | `["20250101", {"value": "DATE"}]` |
| `dtend` | Next day (exclusive end) | `["20250102", ...]` |
| `summary` | Holiday name | `The first day of January` |
| `uid` | `YYYYMMDD@1823.gov.hk` | – |
| `dtstamp`, `transp` | Calendar metadata | unused |

Observed: 17 holidays in every year 2018–2027; 29 of 170 fall on a weekend.
The same holiday is spelled differently across versions (e.g. curly vs straight apostrophe
in "Lunar New Year’s Day"), giving 30 distinct names. **Use the date, not the name.**

**L1** (`src.clean.s6_parse`): `data/interim/l1/s6/en.parquet`, one row per event of every version
(510 = 10 × 51): `bundle`, `member`, `position`, the 6 calendar properties, the event properties
as written; `dtstart` and `dtend` are split into the value and `dtstart_params` / `dtend_params`
(JSON text). Any other property that is not a plain string raises.

| Check (`src.clean.structure`) | Result |
|-------|--------|
| Every version | One calendar (`prodid`, `version` `2.0`, `calscale` `GREGORIAN`, `x-wr-timezone` `Asia/Hong_Kong`, `x-wr-calname`, `x-wr-caldesc`) with 51 events. `dtstart` / `dtend` always `[8 digits, {"value": "DATE"}]`; `transp` always `TRANSPARENT`; `uid` always `<date>@1823.gov.hk`; `summary` never has a space at either end |
| Versions differ in | `dtstamp`: only in 2025-05 and 2026-05 (e.g. `20250506T032740Z`). `prodid`, 4 spellings: `-//1823, Efficiency Office, HKSARG//…` (2019-07, 2019-10), `-//1823 Call Centre, Efficiency Office, HKSARG//…` (2020-06 .. 2024-05), `-//1823 Call Centre, HKSARG//…` (2025-03), `-//1823 Contact Centre, HKSARG//…` (2025-05, 2026-05) |

---

## S8. Daily total rainfall (`daily_HKO_RF_ALL.csv`)

| | |
|---|---|
| Dataset | [Daily total rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) |
| URL | `https://data.weather.gov.hk/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv` (used by `src.download static`) |
| Dataset URL | The dataset lists `https://data.weather.gov.hk/weatherAPI/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv`. Only this one is in the Historical Archive (monthly bundles, 2024–2025: 24); the URL above has no archived version |
| Format | CSV, UTF-8 with BOM: 2 title lines, a bilingual header, data, then footnote lines |
| Coverage | HKO headquarters, daily since 1884 (49,492 days) |

| Column | Description | Observed |
|--------|-------------|----------|
| `年/Year`, `月/Month`, `日/Day` | Date | – |
| `數值/Value` | Daily rainfall (mm) **as text** | `0.0` 22,756; **`Trace`** 6,926 (< 0.05 mm); **`***`** 1 (unavailable) |
| `數據完整性/data Completeness` | `C` complete, `#` incomplete | All `C` except the `***` day (empty) |

Converting `Value` with a plain numeric cast turns `Trace` into NaN; it should become ~0.
2022–2025 contain 238 `Trace` days and no `***`.

**L1** (`src.clean.s8_parse`): `data/interim/l1/s8/daily_HKO_RF_ALL.parquet`, one row per day: `line`
and the 5 columns with the header's names; strings as written. The 2 title lines, the header,
the empty line and the 4 legend lines after the data (`*** 沒有數據/unavailable`,
`# 數據不完整/data incomplete`, `微量表示少於 0.05 毫米/Trace means rainfall less than 0.05 mm`,
`C 數據完整/data Complete`) are checked word for word instead of kept: any change raises.

| Check (`src.clean.structure`) | Result |
|-------|--------|
| Days | 49,492, 1884-03-01 .. 2026-08-31; year 4 digits, month and day 1–2 |
| `數值/Value` | 42,565 numbers with one decimal; `Trace` 6,926 (first 1884-12-06, line 284); `***` 1: line 5847, **1900-02-29, a date that does not exist** (1900 was not a leap year) |
| `數據完整性/data Completeness` | `C`, except line 5847 (empty) |

---

## Optional sources

Downloaded for 2024–2025 (see [Inventory](#inventory-on-disk-2026-09-29)). Parsed to L1
(`data/interim/l1/`) and checked for 2024-05, 2025-07 and 2025-08: S9, S11, S13, S7, S12 (its 4
versions in those months); S10 and S14 in all their versions.
"Observed" figures here come from one monthly bundle (2025-08) unless stated otherwise;
"Checked" rows give the figures of the three months.

### S9. Smart-lamppost detector readings (`rawSpeedVol_SLP-all.xml`)

| | |
|---|---|
| Dataset | [Traffic Data collected by Traffic Detectors Installed at Smart Lampposts](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts) |
| Live URL | `https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol_SLP-all.xml` |
| Format | **Same as S1**: same root element and same schema (`SpeedVolOcc-BR.xsd`), same fields and codes (data dictionary 20231228) |
| Observed | 28,465 snapshots in 2025-08 (up to 948 a day), 0.34 GB uncompressed per month; 17 detectors reporting (`AID20011` .. `AID20060`, in 57 sampled snapshots), of the 20 listed in S10 |
| Checked (2024-05, 2025-07, 2025-08; 5.5 M readings) | Same file pattern as S1: identical copies (142 / 2,260 / 2,028 extra), two periods per file, each period in one distinct file, 26.9 / 46.3 / 40.8 % of periods missing (longest gap 42, 15, 9 min). No truncated file. Detectors: 20, 18, 17 (all in S10); each keeps one direction; lanes `Fast`, `Middle`, `Slow Lane`. Nothing absent or empty, every value well-formed. `valid = N`: 9,162 / 84 / 36 readings |
| Same lane twice | In 49 files a detector lists a lane twice, usually next to each other (622 keys: 568 in 2024-05, 26 in one 2025-07 file, 28 in one 2025-08 file). 615 keys have identical readings; 7 differ (AID20031 2024-05-02 07:34:00, AID20022 05-16 08:02:00 and 05-17 17:55:30, AID20054 05-20 17:22:00) |

### S10. Smart-lamppost detector locations (`traffic_speed_volume_occ_info-slp.csv`)

| | |
|---|---|
| URL | `https://static.data.gov.hk/td/traffic-data-slp/info/traffic_speed_volume_occ_info-slp.csv` |
| Columns | Same 11 as S2 (`AID_ID_Number`, `District`, `Road_EN`, …, `Rotation`) |
| Versions | Only two archived. **Their encodings differ**: 2023-12 (13 rows) is **UTF-16 with BOM, tab-separated**; 2024-01 (20 rows) is UTF-8 with BOM, comma-separated. Read by BOM, not with a fixed encoding |
| Observed | Districts Kwun Tong, Wan Chai, Yau Tsim Mong. `Road_EN` ends with the ID in brackets |
| Checked (both versions; `src.clean.versions_parse`, `src.clean.versions_checks`) | Every row has the header's 11 fields; nothing empty, no leading or trailing space; IDs unique; coordinates and `Rotation` well-formed. 2024-01 has no final newline. 2023-12 → 2024-01: 7 added (AID20054 .. AID20060), none removed, **`Direction` changed for all 13** (e.g. AID20051 `East` → `West`, its `Road_EN` says "Westbound"), `Rotation` for 7, `Road_EN` for 1. In 2023-12 every `Direction` contradicts the "…bound" of `Road_EN`; in 2024-01 none does. Every S9 detector of the three months is in 2024-01, and S9 `direction` equals its `Direction` for all of them |

### S11. Segment speeds (`irnAvgSpeed-all.xml`)

| | |
|---|---|
| Dataset | [Traffic Data of Strategic / Major Roads](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), resource "Traffic Speeds of Road Network Segments (Processed Data)" |
| Live URL | `https://resource.data.one.gov.hk/td/traffic-detectors/irnAvgSpeed-all.xml` |
| Structure | `<segment_speed_list>`: `date`, `time`, `irn_version`, then `<segments>` with one `<segment>` each: `segment_id`, `speed` (float, km/h, "current average speed"), `valid` (`Y` online / `N` offline) |
| Observed | 21,414 snapshots in 2025-08 (~1–2 min apart), 7.9 GB uncompressed per month; 4,405 segments per file, `valid = N` on 41 of them in one sample. File archived 17:02 held `time` 16:55. `irn_version` was `20221210` |
| Link | `segment_id` is `ROUTE_ID` of the S12 road centreline. Every segment of S11 2024-05 is in the S12 version of 2024-05-28. Of 2025-07 / 2025-08, 9 / 10 segments are not in the S12 version of the same month (2025-07-30, 2025-08-29) but are in older ones: 56821, 60813, 62346, 63794, 63796, 63797, 8797 last in 2024-06-05; 261807 in 2025-04-28; 105473 in 2025-06-26; 59042 in 2025-07-30. S11 keeps reporting them (62346 and 63797 until 2025-08-06, the others all month). Checked with an ad-hoc read of every S12 version's CENTERLINE `ROUTE_ID`, before S12 was parsed (its L1 holds only the versions of the three months) |
| Checked (2024-05, 2025-07, 2025-08; 253.7 M segment rows) | `src.clean.s11_parse`, `src.clean.s11_checks`. 21,619 / 17,415 / 18,674 distinct files. 3 are truncated (two cut at 64 KiB, one missing only the closing `segment_speed_list>`); each is a byte prefix of the complete file with the same time and is skipped. One `date`, `time`, `irn_version` per file; `irn_version` always `20221210`; each (`date`, `time`) in one complete file only. Nothing absent or empty; `segment_id` always digits, `speed` a decimal number, `valid` `Y` or `N`; no segment twice in a file |
| Times | `time` is HH:MM:00 at an odd minute (every 2 min), except 2 files (2025-07-02 02:14, 2025-08-01 22:16; the next file is 02:15 / 22:17). Of the 720 odd-minute times of a day, missing: 704 (3.2 %) in 2024-05, 4,909 (22.0 %) in 2025-07, 3,651 (16.4 %) in 2025-08. Longest gaps: 120 min (2025-08-23 19:25 → 21:25), 62 min (2025-08-31 01:47 → 02:49), 50 min (2024-05-30 19:59 → 20:49); all others ≤ 18 min. A file is fetched 4–12 min after its `time` (median 6) |
| Segments | 4,376 per file until 2024-05-08 17:21, then 4,388 (12 added, 282434 .. 282486). 4,413 until 2025-07-29 11:11, then 4,405 (8 removed). On 2025-08-06: 4,405 → 4,404 → 4,403 → 4,391 (segments removed after 15:55, 16:05, 16:11). 4,414 segment IDs over the three months |
| Speed | 0.0 – 121.0, one decimal place. 121.0 occurs 2,843 times (on 60–65 segments a month), far more than any value just below it (each of 120.1 .. 120.9: 94–220). 0.0 with `valid = Y`: 76 / 145 / 360 rows |
| `valid = N` | 4.24 M / 0.91 M / 0.77 M rows (4.5 / 1.2 / 0.9 %). The speed is then always `50`, `70`, `80`, `100` or `110`, written without a decimal point, and always the same value for a segment within a month; 39 / 29 / 27 segments are `N` in every file. `valid = Y` with a speed without a decimal point: 9,793 / 782 / 1,013 rows, on 16 / 11 / 12 segments that are never `N` that month, again one of these values per segment |

### S14. Road network segments (`speed_segments_info.csv`)

`https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv`,
4,255 rows × 2 columns (2023-09): `irn_id` (segment ID) and `ucase(route)` (the **route number** the
segment belongs to; 174 values, e.g. `9` has 423 segments). No coordinates: the geometry is S12.
6 versions on disk (2021-08 .. 2023-09).

**Checked on all 6 versions** (`src.clean.versions_parse`, `src.clean.versions_checks`):

| Check | Result |
|-------|--------|
| Files | UTF-8 without BOM, comma-separated; line ends CRLF (2021-08, 2022-03, 2022-10) or LF (2021-11, 2022-02, 2023-09). Every row has 2 fields; nothing empty, no leading or trailing space; the segment ID is always digits and unique in every version |
| Headers | **Three headers**: `Road Name,Segment ID` (2021-08: 63 rows, all `Route 8`), `route,irn_id` (2021-11 .. 2022-10), `irn_id,ucase(route)` (2023-09; columns swapped and renamed). Every `route` value (2021-11 .. 2022-10) is already upper case |
| Rows | 63, 2,684, 3,719, 3,831, 4,135, 4,255. Each version adds segments (2,621, 1,039, 112, 334, 120); removed only 4 (2022-02) and 30 (2022-10); `route` changed for 277 segments 2022-03 → 2022-10. The 63 segments of 2021-08 are all in 2021-11. 2022-10 → 2023-09 (headers differ, so not compared by the check; by hand, `route` against `ucase(route)`): all 4,135 segments kept, 4,128 with the same route, 7 changed (e.g. 163685 `SHENZHEN BAY BRIDGE` → `10`, 276283 `UNNAMED ROAD` → `CASTLE PEAK ROAD - CHAU TAU`) |
| Against S11 | The newest version (2023-09) lacks 136 / 162 / 156 of the S11 segments of 2024-05 / 2025-07 / 2025-08; 135 / 161 / 155 are in no version (e.g. 104153, 104169, 104171). No version is later than the three months, so these segments have no route in S14 |

### S12. Road network, 2nd generation (`RdNet_IRNP.gdb.zip`)

| | |
|---|---|
| Dataset | [Road Network (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2) |
| URL | `https://static.data.gov.hk/td/road-network-v2/RdNet_IRNP.gdb.zip` — the only resource of the dataset in the Historical Archive (its per-layer GML / KMZ files are not) |
| Format | Esri File Geodatabase in a ZIP, inside the bundle as `<YYYYMMDD-HHMM>-RdNet_IRNP.gdb.zip`; ~17 MB per version, 34 versions in 2024–2025 |
| Layers | 17: `CENTERLINE`, `INTERSECTION`, `SPEED_LIMIT`, `BUS_ONLY_LANE`, `TURN`, `ROUNDABOUT`, `TRAFFIC_FEATURES`, `PEDESTRIAN_ZONE`, `NSR`, `PERMIT`, `PROHIBITION`, `VEHICLE_RESTRICTION`, `RUN_IN_OUT`, `ONSTREETPARK`, `GISP_ON_STREET_PARKING`, `TUN_BRIDGE_TOLL`, `TUN_BRIDGE_TV_TOLL` |
| CENTERLINE | 35,837 lines (2025-08); columns `STREET_ENAME`, `STREET_CNAME`, `ELEVATION`, `ST_CODE`, `EXIT_NUM`, `ROUTE_NUM`, `REMARKS`, `ROUTE_ID`, `TRAVEL_DIRECTION`, `CRE_DATE`, `LAST_UPD_DATE_V`, `ALIAS_ENAME`, `ALIAS_CNAME`, `SHAPE_Length`; CRS EPSG:2326 (HK1980 Grid, as S2 `Easting` / `Northing`) |
| Reading | `pyogrio` (conda base) drops M values, which 6 layers carry, with a warning; its non-Arrow read also turns curves into lines. `src.clean.s12_parse` therefore takes the attributes from `pyogrio.raw.read_arrow` and the geometry from GDAL's C API (see its docstring) |

**L1** (`src.clean.s12_parse`): `data/interim/l1/s12/<LAYER>/<YYYYMM>.parquet`, one row per feature
of every version in the bundle: `bundle`, `index`, `OBJECTID`, the attributes with GDAL's types,
`SHAPE` as ISO WKB with Z / M and curves; `data/interim/checks/s12_layers.csv`, one row per
version and layer. Versions in the three months: 2024-05-28, 2025-07-25, 2025-07-30, 2025-08-29.

| Check (`src.clean.structure`) | Result |
|-------|--------|
| Layers | All 17 in every version. 14 have geometry, all EPSG:2326; `TUN_BRIDGE_TOLL`, `TUN_BRIDGE_TV_TOLL` and `GISP_ON_STREET_PARKING` are tables without geometry |
| M values | `VEHICLE_RESTRICTION`, `PROHIBITION`, `PERMIT` (Point M); `SPEED_LIMIT`, `PEDESTRIAN_ZONE`, `BUS_ONLY_LANE` (MultiLineString M) |
| Curves | Stored as MultiCurve, though the layer type says MultiLineString (4 versions together): `NSR` 2,094, `CENTERLINE` 1,664, `SPEED_LIMIT` 32 (M), `TURN` 20, `BUS_ONLY_LANE` 8 (M) |
| Field changes 2024-05 → 2025 | `GISP_ON_STREET_PARKING`: 4 fields added (`OT_OPER_HR_DESC`, `OT_OPER_HR_DESC_CHI`, `OT_IRNP_REMARKS_ENG`, `OT_IRNP_REMARKS_CHI`), `X_COOR` / `Y_COOR` int32 → double. `TRAFFIC_FEATURES`: `RD_ID_7` .. `RD_ID_9` double → int32. `TUN_BRIDGE_TOLL`, `TUN_BRIDGE_TV_TOLL`: `LAST_UPDATED_DATE` string → timestamp. The months cannot be stacked without handling these |
| Features | E.g. `CENTERLINE` 35,141 / 35,760 / 35,775 / 35,837. `ONSTREETPARK` and `GISP_ON_STREET_PARKING` have the same count in every version (36,167 .. 37,184) |

### S13. Special traffic news (`trafficnews.xml`)

| | |
|---|---|
| Dataset | [Special Traffic News (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2) |
| Live URL | `https://www.td.gov.hk/en/special_news/trafficnews.xml` |
| Structure | `<list>` of `<message>`, fields as in the XSD: `INCIDENT_NUMBER`, `INCIDENT_HEADING_EN/CN`, `INCIDENT_DETAIL_EN/CN`, `LOCATION_EN/CN`\*, `DISTRICT_EN/CN`\*, `DIRECTION_EN/CN`\*, `ANNOUNCEMENT_DATE` (`YYYY-MM-DDTHH:MM:SS`), `INCIDENT_STATUS_EN/CN` (`NEW` / `UPDATED` / `CLOSED`), `NEAR_LANDMARK_EN/CN`\*, `BETWEEN_LANDMARK_EN/CN`\*, `ID`, `CONTENT_EN/CN`, `LATITUDE`\*, `LONGITUDE`\* (\* optional) |
| Snapshots | 2,837 / 3,104 / 3,388 fetches in 2024-05 / 2025-07 / 2025-08 (every day; up to 166 a day), 1,737 / 2,020 / 2,151 distinct files. **Every file holds exactly one `<message>`** although the XSD allows a list, so the archive does not show all messages in force at a moment. Fetches are irregular (the longest gap within a day is 460–536 min), so a message replaced between two fetches is not in the archive |

**Checked on 2024-05, 2025-07, 2025-08** (`src.clean.s13_parse`, `src.clean.s13_checks`; 5,908 message rows, 4,759 distinct IDs):

| Check | Result |
|-------|--------|
| Structure | Root `<list>`, children `<message>`, only the XSD elements, none twice. 5 files of 2024-05 (16 and 25 May) are not well-formed XML: `Kowloonbay International Trade & Exhibition Centre` has an unescaped `&`. The parser reads it as `&` and lists the files in `data/interim/checks/s13_bare_ampersands.csv` |
| Absent / empty | No element is absent: optional fields are present but empty. `LATITUDE`, `LONGITUDE` always empty; `DISTRICT` empty in all rows but one (`Yau Tsim Mong`, 2025-07). Also empty: `DIRECTION` 324 / 505 / 557 rows, `NEAR_LANDMARK` 383 / 520 / 535, `BETWEEN_LANDMARK` 1,686 / 1,953 / 2,132, `LOCATION` 84 / 89 / 118, `CONTENT` once (ID 118838, heading `Highwind Incident`). EN and CN are always both empty or both non-empty |
| Formats | `ANNOUNCEMENT_DATE` always `YYYY-MM-DDTHH:MM:SS`; `ID` always an integer |
| Versions of an ID | An ID is in 1 distinct file (3,611 IDs), 2 (1,147) or 3 (1). Closing an ID keeps its `ANNOUNCEMENT_DATE`: 1,147 (ID, `ANNOUNCEMENT_DATE`) pairs are in two files, and in 1,144 only `INCIDENT_STATUS` changed. The other 3 also changed one field when closed: ID 119051 `DIRECTION` `Chung Hom Kok Road` → empty; ID 119481 `INCIDENT_DETAIL` `Fallen Tree` → `Tree trimming`; ID 120623 `LOCATION` empty → `Special traffic arrangement may be implemented at Lok Ma Chau Control Point`. In time order an ID's statuses are one of `NEW`, `UPDATED`, `CLOSED`, `UPDATED > CLOSED` (359 / 376 / 401), `NEW > CLOSED` (2 / 3 / 5); a status never follows `CLOSED` |
| Incidents | Each update of an incident is a new `ID`: an `INCIDENT_NUMBER` has 1 / 2 / 3 / 4 / 5+ IDs in 458 / 1,429 / 226 / 62 / 68 incidents |
| ID reused | On 2025-07-12/13 two IDs belong to two incidents each. ID 118305 is IN-25-04136 (Sai Yee Street queue, announced 07-12 21:40) and IN-25-04137 (Lion Rock Tunnel accident, 07-13 07:59). ID 118306 is IN-25-04137 with `CONTENT` `DR Testing` (07-12 21:56) and IN-25-04097 (Gascoigne Road, 07-13 08:06). IN-25-04136 also covers a Lung Cheung Road accident (IDs 118303, 118304), and IN-25-04137 the Lion Rock Tunnel accident |
| IDs not seen | Between the smallest and largest ID of a month, 513 (2024-05) and 331 (2025-08) integers are never seen. The 2025-07 range is not comparable: two old messages were fetched on 2025-07-12 22:13 / 22:16 (ID 99753 announced 2024-07-06, ID 116872 announced 2025-06-20). Whether TD numbers IDs without gaps is not known |
| Timing | Announcement → first fetch: median 8 min; over 60 min for 27 / 65 / 70 messages. Two messages were fetched before their `ANNOUNCEMENT_DATE`: ID 96671 (announced 2024-05-11 23:19, fetched 12:17; the incident's previous ID 96668 was announced 11:19, the next ID 96685 15:36) and ID 120705 (announced 2025-08-15 22:00, fetched 21:56; its content says "announces at 9:50 pm") |

### N2. Automatic weather station hourly rainfall (`hourlyRainfall.php`)

`https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en`: JSON with
`obsTime` and, for each of 36 stations, `automaticWeatherStation`, `automaticWeatherStationID`,
`value`, `unit`. **It is not in the Historical Archive** (the API returns `Not Found` for every
date range), so it can only be collected live. This is why rainfall is matched to roads by district (S3).

### S7. Gridded rainfall nowcast

`https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv`, archived
from ~July 2022, ~96 files per day (every 15 min). Each file is a 121 × 121 grid (≈ 2 km) × 4 lead times (+30 to
+120 min) = 58,564 rows, with columns `Updated Date and Time`, `Ending Date and Time`, `Latitude`,
`Longitude`, `Half-hourly Nowcast Accumulated Rainfall (mm)`; times as `YYYYMMDDHHMM`. It is a radar-based
**forecast**, not a gauge measurement, so at most it could serve as a finer-grained sensitivity check.
The data dictionary calls the data provisional.

Observed (2025-08): the grid spans 21.328–23.487 °N, 112.956–115.291 °E (well beyond Hong Kong);
a file archived 02:30 was updated 02:12 and ends at 02:42, 03:12, 03:42, 04:12; 8 GB uncompressed per month.

**Checked on 2024-05, 2025-07, 2025-08** (`src.clean.s7_parse`, `src.clean.s7_checks`; 8,910 files, 518.4 M rows from the 8,852 parsed files):

| Check | Result |
|-------|--------|
| Fetches | At :00, :15, :30, :45 (a few 1–4 min later); 96 a day on 29 / 25 / 29 days, 91–95 on 2024-05-24, 05-30, 2025-07-02, 07-11, 07-20 (91), 07-23, 07-28, 07-31, 08-04, 08-05. No identical copies |
| Not well-formed, not parsed | 58 files (19 / 24 / 15). 44 have something after the last complete row: an empty line, or the end of a longer version (`5.291,1.73`, `,21.328,115.291,0.00`; one has two rows of the next update, 202507151012). 6 have merged lines inside (`202405200824,202405201024,22.106,1405201024,22.106,114.104,2.86`). 8 are cut at a multiple of 32 KiB (32 KiB .. 1,664 KiB) and have no final newline. Listed in `data/interim/checks/s7_files.csv`. Only one of them has an `updated` that a parsed file also has: 20250715-1030 and 20250715-1015 both say 202507151000, and their first 58,564 rows differ in 515 rainfall values (by −0.05 .. +0.01 mm). The other 57 forecasts are not in L1 |
| Parsed files | 8,852. Each has 58,564 rows = 4 endings (30, 60, 90, 120 min after `updated`) × 14,641 cells (121 latitudes × 121 longitudes, 21.328–23.487 °N, 112.956–115.291 °E), one `updated`, no cell twice. No `updated` in two files. Nothing empty; `updated` / `ending` 12 digits, latitude / longitude 3 decimals, rainfall 2 decimals, except in the 3 files below |
| Corrupted rows with 5 fields | 3 parsed files: 20250723-0530 (6 rows, e.g. `updated` `2025072230512`, longitude `114202`), 20250815-1315 (latitude `21.60`, `22..825`), 20250824-0830 (longitude `114.1143`). They show in the formats and because their cells differ from every other file. A corrupted rainfall value that keeps the format cannot be seen |
| Times | `updated` is at :00, :12, :24, :36, :48 (every 12 min). The archive holds :00, :12, :24 about 736 times a month each, :48 656–692 times, :36 only 50 / 79 / 53 times. Fetched 11–33 min after `updated` (median 18). Longest time between successive `updated` within a day: 24 min (65 days), 36 (25), 48 (3) |
| Rainfall | `0.00` in 80.8 / 84.7 / 82.1 % of rows. Maximum 583.39 mm (2024-05), 4,149.47 (2025-07), 5,406.92 (2025-08). Values ≥ 1,000 mm: none in 2024-05, 649 rows (58 files) in 2025-07, 1,493 rows (77 files) in 2025-08, more at longer lead times (2025-08, ≥ 500 mm: 546 / 946 / 1,295 / 1,525 rows at +30 / 60 / 90 / 120 min) |
