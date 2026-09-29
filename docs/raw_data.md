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
| [S6](#s6-public-holidays-enjson) | Public holidays | 1823 | per day | Hong Kong | 2018 .. 2027 (merged) | 8 kB | main |
| [S8](#s8-daily-total-rainfall-daily_hko_rf_allcsv) | Daily total rainfall | HKO | daily | 1 station (HKO HQ) | 1884-03 .. 2026-08 | 0.8 MB | main |
| [S9](#s9-smart-lamppost-detector-readings-rawspeedvol_slp-allxml) | Smart-lamppost detector readings | TD | 30 s periods | lane × detector (17 reporting) | 2024-01 .. 2025-12, monthly bundles | 0.9 GB | optional |
| [S10](#s10-smart-lamppost-detector-locations-traffic_speed_volume_occ_info-slpcsv) | Smart-lamppost detector locations | TD | versions | detector | 2023-12, 2024-01 | 8 kB | optional |
| [S11](#s11-segment-speeds-irnavgspeed-allxml) | Segment speeds (TD processed) | TD | ~1 min snapshots | road segment (~4,400) | 2024-01 .. 2025-12, monthly bundles | 13 GB | optional |
| [N1](#n1-road-network-segments-speed_segments_infocsv) | Segment → route number | TD | versions | road segment | 2021-08 .. 2023-09, 6 versions | 0.2 MB | optional |
| [S12](#s12-road-network-2nd-generation-rdnet_irnpgdbzip) | Road network geometry (FGDB) | TD | versions (34 in 2024–25) | road centreline (35,837) | 2024-01 .. 2025-12, monthly bundles | 0.6 GB | optional |
| [S13](#s13-special-traffic-news-trafficnewsxml) | Special traffic news (incidents, closures) | TD | per message update | location text; some with district / lat-lon | 2024-01 .. 2025-12, monthly bundles | 61 MB | optional |
| [S7](#s7-gridded-rainfall-nowcast) | Gridded rainfall nowcast (radar **forecast**) | HKO | every 15 min, +30 .. +120 min | ~2 km grid, 121 × 121 | 2024-01 .. 2025-12, monthly bundles | 12 GB | optional |

Not obtainable for the past: [N2 station hourly rainfall](#n2-automatic-weather-station-hourly-rainfall-hourlyrainfallphp)
and HKO's JSON Current Weather Report (`weather.php?dataType=rhrread`); neither is in the Historical Archive.

### Where the files are, and how they were downloaded

Two downloaders, by where the data comes from:

**`hkdata.download` (DATA.GOV.HK Historical Archive)** — S1, S2 (3 versions), S3, S7, S9–S13, N1 (1 version).
Driven by the plans in `hkdata/plans/`; layout `data/raw/<url host>/<url path>/`:

| Plan | Contents | Size |
|------|----------|------|
| `2024_2025_main.json` | S1, S3, S13, S2 (2022-03, 2024-02, 2025-10), N1 (2023-09) | 25.2 GB |
| `2024_2025_optional.json` | S11, S9, S7, S10 | 28.1 GB |
| `road_network_2024_2025.json` | S12 | 0.6 GB |

```bash
python -m hkdata.download run hkdata/plans/2024_2025_main.json --out data/raw
```

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
| `warnings` | `hko/rstorm.dat`, `hko/tc.dat` (+ parsed `rainstorm_warnings.csv`, `tc_signals.csv`) | S4, S5 (not on DATA.GOV.HK) |
| `static` | `hko/daily_HKO_RF_ALL.csv`, `td/traffic_speed_volume_occ_info.csv` | S8; S2 live copy (= its 2026-04 version) |
| `static-history` | `td/traffic_speed_volume_occ_info/<YYYYMMDD>.csv`, `td/speed_segments_info/<YYYYMMDD>.csv` | S2 2021-08 .. 2021-12 and 2026-04; N1 2021-08 .. 2022-10 |
| `holidays` | `calendar/public_holidays.csv` | S6 (all archived versions merged) |

Versions in both places were checked byte for byte and the `src.download` copies deleted.
Their data dictionaries were saved by hand into `hko/data-dictionary/`,
`calendar/data-dictionary/` and `td/data-dictionary/` (see [Data dictionaries](#data-dictionaries)).

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
`<url-encoded live URL>/<YYYYMMDD-HHMM>-rawSpeedVol-all.xml`. `hkdata.download` keeps whole
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
| S1, S2, S11, N1 | `dataspec-traffic-data-strategic-major-roads.pdf` in each resource folder and `td/data-dictionary/` (20210812, 20211118, 20240418) | 20211118 → 20240418 (last update 30 Nov 2022): only wording (`valid`, occupancy definition); structure unchanged |
| S9, S10 | `dataspec-traffic-data-slp.pdf` (20231228, 20240418) | one: same XML structure as S1 |
| S3 | `HKO_Open_Data_API_Documentation.pdf` (11 versions) | three; it documents the JSON API, **not the RSS file** we use |
| S4, S5 | `hko/data-dictionary/hko-webpage-warndb3.shtml.html`, `…warndb1.shtml.html` | **no official dictionary**: the HKO database web pages, saved 2026-09-29 (notes on provisional records, signal-number history) |
| S6 | `calendar/data-dictionary/…-1823_cal_dictionary.pdf` (4 versions) | – |
| S7 | `HKO_gridded_rainfall_nowcast_documentation.pdf` (6 versions) | one |
| S8 | `hko/data-dictionary/20250227-data_dictionary_daily_total_rainfall.pdf` | – |
| S12 | `rdnet_dataspec.zip` (5 versions): one PDF each for FGDB, GML, KML | – |
| S13 | `Data_Specification_for_STN_Eng_v4.0.pdf` (2 versions) + `schema/20210608/20210608-trafficnews.xsd` | one |

Found while reading them:

| Finding | Detail |
|---------|--------|
| `valid` = detector online / offline | S1/S9: the 2022 dictionary defines `Y` as "Detector Online" and `N` as "Detector Offline" (2021: "valid / non-valid") |
| Dictionary column names ≠ files | S2 is documented as `Device_ID`, the file has `AID_ID_Number`; N1 as `segment_id`, `road name`, the file has `irn_id`, `ucase(route)`. The files are what we use |
| S3 format undocumented | The RSS bulletin is free text; our parser fails loudly on anything unexpected (see S3) |
| Truncated dictionary files in the archive | 6 versions lack the PDF end marker `%%EOF` (HKO API documentation 20240921, 20241022, 20241116, 20250311; gridded nowcast 20240921, 20241010); the next day's version is complete |
| Broken archive links | Dictionary versions 20221214 (TD strategic roads) and 20240229 (HKO API) redirect to files the storage host does not have (404), so they are not on disk; N1 has 20211118 and 20240418 instead |

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
| detector | `direction` | string | – | Direction of AID | e.g. `South East`; same as S2 `Direction` |
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
| Missing periods | 1,730 of 2,880 periods per day present on 5 Aug 2025 (~40 % missing) | Missing data = **absent rows**, not NA |
| Overlap | Adjacent files repeat readings; ~9 % of rows are duplicates | Deduplicate on (time, detector, lane) |
| Midnight date | The 00:00 period carries the **previous day's** `<date>` | Re-date using the archive time |
| Duplicate files | Monthly bundles occasionally store the same file twice | Drop identical copies |
| Truncated files | A few files end mid-document (1 of 919 on 29 Jul 2025) | Keep complete readings before the cut |
| Schema change | `<s.d.>` appears from ~18 Nov 2021 (data dictionary `20211118`) | `sd` missing earlier |
| Placeholder speed | With `volume = 0`, `speed` is 70 / 80 / 100 / 50 / 110 (the speed limit) and `s.d.` = 0 in 99.9 % of cases | Not a measurement |
| Contradictions | `speed = 0` with `volume > 0`: 5,991 readings; `occupancy = -1`: 60 | Cleaning rule needed |
| Out of range | `speed > 130`: 15,711 readings (0.4 %), mostly 131–136 in the fast lane; max 300 | Cleaning rule needed |
| Stuck sensor or standstill? | `occupancy = 100`: 1,533 readings, 1,415 with speed = volume = 0. TDSLTR20004 reads 100 % from 06:34 to 15:26 on 5 Aug 2025, during the Black Rainstorm | Needs judgement: sensor fault or flooded road |
| Partial reporting | AID01133 reports only after 20:45 on 5 Aug 2025 (219 periods) | Per-detector coverage matters |

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
| `Direction` | string | Traffic direction | 8 values: `West` 127, `North West` 117, `South East` 114, `East` 108, `North East` 105, `South` 85, `South West` 79, `North` 72 |
| `Rotation` | integer | Bearing in degrees for map arrows | 0–355 |

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

---

## S5. Tropical cyclone warning signals (`tc.dat`)

| | |
|---|---|
| Web page | [Tropical Cyclone Warning Signals database](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml) |
| Data file | `https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat` |
| Format | Tab-separated, UTF-8 with BOM, **no header**, 2,512 lines since 1946 (1,262 cyclone signals + 1,250 other rows) |

Example line: `202603	SuperT	SAUDEL	1	X	1810	31	8	2026	X	010	4	9	2026	X	7800`.

| Column | Description | Observed |
|--------|-------------|----------|
| 1 | Cyclone code (year + number) | 483 cyclones |
| 2 | Intensity: `TD` tropical depression, `TS` tropical storm, `STS` severe tropical storm, `T` typhoon, `ST` severe typhoon, `SuperT` super typhoon; combined codes such as `TST`, `TSupT`, `TD/TD` also occur (not documented). **`MSN` rows are not cyclone signals** (1,250 rows; skipped) | `T` 394, `STS` 231, `TSupT` 178, `TS` 177, `TST` 113, `SuperT` 71, `TD` 56, `ST` 41 |
| 3 | Name; `NIL` = unnamed | 109 unnamed |
| 4 | Signal: 1, 3, 8, 9, 10 | 1: 538, 3: 428, 8: 242, 9: 35, 10: 19 |
| 5 | Direction of No. 8 signal (`NE`/`NW`/`SE`/`SW`); `X` otherwise; `*` in some old records | – |
| 6 | Start time `HHMM` (leading zeros dropped: `10` = 00:10; `2400` = midnight) | – |
| 7–9 | Start day, month, year | – |
| 10 | Flag `X` / `S` (undocumented; `S` only in old records) | – |
| 11 | End time `HHMM` | – |
| 12–14 | End day, month, year | – |
| 15 | Flag, as column 10 | – |
| 16 | Duration `HHHMM` (`7800` = 78 h 00 min) | – |

---

## S6. Public holidays (`en.json`)

| | |
|---|---|
| Dataset | [Hong Kong Public Holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) |
| Live URL | `https://www.1823.gov.hk/common/ical/en.json` (also `tc.json`, `sc.json`) |
| Format | iCalendar-style JSON, UTF-8 with BOM |
| Coverage | **Each file covers three years** (the live file: 2025–2027). The 10 archived versions since 2019 together cover 2018–2027 |

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

---

## Optional sources

Downloaded for 2024–2025 (see [Inventory](#inventory-on-disk-2026-09-29)); not yet parsed.
"Observed" figures here come from one monthly bundle (2025-08) unless stated otherwise.

### S9. Smart-lamppost detector readings (`rawSpeedVol_SLP-all.xml`)

| | |
|---|---|
| Dataset | [Traffic Data collected by Traffic Detectors Installed at Smart Lampposts](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts) |
| Live URL | `https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol_SLP-all.xml` |
| Format | **Same as S1**: same root element and same schema (`SpeedVolOcc-BR.xsd`), same fields and codes (data dictionary 20231228) |
| Observed | 28,465 snapshots in 2025-08 (up to 948 a day), 0.34 GB uncompressed per month; 17 detectors reporting (`AID20011` .. `AID20060`, in 57 sampled snapshots), of the 20 listed in S10 |

### S10. Smart-lamppost detector locations (`traffic_speed_volume_occ_info-slp.csv`)

| | |
|---|---|
| URL | `https://static.data.gov.hk/td/traffic-data-slp/info/traffic_speed_volume_occ_info-slp.csv` |
| Columns | Same 11 as S2 (`AID_ID_Number`, `District`, `Road_EN`, …, `Rotation`) |
| Versions | Only two archived. **Their encodings differ**: 2023-12 (13 rows) is **UTF-16 with BOM, tab-separated**; 2024-01 (20 rows) is UTF-8 with BOM, comma-separated. Read by BOM, not with a fixed encoding |
| Observed | Districts Kwun Tong, Wan Chai, Yau Tsim Mong. `Road_EN` ends with the ID in brackets. AID20051 has `Direction` = `East` while its `Road_EN` says "Westbound" (`Rotation` 270) |

### S11. Segment speeds (`irnAvgSpeed-all.xml`)

| | |
|---|---|
| Dataset | [Traffic Data of Strategic / Major Roads](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads), resource "Traffic Speeds of Road Network Segments (Processed Data)" |
| Live URL | `https://resource.data.one.gov.hk/td/traffic-detectors/irnAvgSpeed-all.xml` |
| Structure | `<segment_speed_list>`: `date`, `time`, `irn_version`, then `<segments>` with one `<segment>` each: `segment_id`, `speed` (float, km/h, "current average speed"), `valid` (`Y` online / `N` offline) |
| Observed | 21,414 snapshots in 2025-08 (~1–2 min apart), 7.9 GB uncompressed per month; 4,405 segments per file, `valid = N` on 41 of them in one sample. File archived 17:02 held `time` 16:55. `irn_version` was `20221210` |
| Link | `segment_id` is `ROUTE_ID` of the S12 road centreline: 4,395 of 4,405 ids of a 2025-08 snapshot are in the 2025-08 CENTERLINE layer (the other 10 not yet checked against older versions) |

### N1. Road network segments (`speed_segments_info.csv`)

`https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv`,
4,255 rows × 2 columns (2023-09): `irn_id` (segment ID) and `ucase(route)` (the **route number** the
segment belongs to; 174 values, e.g. `9` has 423 segments). No coordinates: the geometry is S12.
6 versions on disk (2021-08 .. 2023-09).

### S12. Road network, 2nd generation (`RdNet_IRNP.gdb.zip`)

| | |
|---|---|
| Dataset | [Road Network (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2) |
| URL | `https://static.data.gov.hk/td/road-network-v2/RdNet_IRNP.gdb.zip` — the only resource of the dataset in the Historical Archive (its per-layer GML / KMZ files are not) |
| Format | Esri File Geodatabase in a ZIP, inside the bundle as `<YYYYMMDD-HHMM>-RdNet_IRNP.gdb.zip`; ~17 MB per version, 34 versions in 2024–2025 |
| Layers | 17: `CENTERLINE`, `INTERSECTION`, `SPEED_LIMIT`, `BUS_ONLY_LANE`, `TURN`, `ROUNDABOUT`, `TRAFFIC_FEATURES`, `PEDESTRIAN_ZONE`, `NSR`, `PERMIT`, `PROHIBITION`, `VEHICLE_RESTRICTION`, `RUN_IN_OUT`, `ONSTREETPARK`, `GISP_ON_STREET_PARKING`, `TUN_BRIDGE_TOLL`, `TUN_BRIDGE_TV_TOLL` |
| CENTERLINE | 35,837 lines (2025-08); columns `STREET_ENAME`, `STREET_CNAME`, `ELEVATION`, `ST_CODE`, `EXIT_NUM`, `ROUTE_NUM`, `REMARKS`, `ROUTE_ID`, `TRAVEL_DIRECTION`, `CRE_DATE`, `LAST_UPD_DATE_V`, `ALIAS_ENAME`, `ALIAS_CNAME`, `SHAPE_Length`; CRS EPSG:2326 (HK1980 Grid, as S2 `Easting` / `Northing`) |
| Reading | `geopandas` / `pyogrio` (installed in conda base). Geometries carry an M value, which pyogrio drops with a warning |

### S13. Special traffic news (`trafficnews.xml`)

| | |
|---|---|
| Dataset | [Special Traffic News (2nd Generation)](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2) |
| Live URL | `https://www.td.gov.hk/en/special_news/trafficnews.xml` |
| Structure | `<list>` of `<message>`, fields as in the XSD: `INCIDENT_NUMBER`, `INCIDENT_HEADING_EN/CN`, `INCIDENT_DETAIL_EN/CN`, `LOCATION_EN/CN`\*, `DISTRICT_EN/CN`\*, `DIRECTION_EN/CN`\*, `ANNOUNCEMENT_DATE` (`YYYY-MM-DDTHH:MM:SS`), `INCIDENT_STATUS_EN/CN` (`NEW` / `UPDATED` / `CLOSED`), `NEAR_LANDMARK_EN/CN`\*, `BETWEEN_LANDMARK_EN/CN`\*, `ID`, `CONTENT_EN/CN`, `LATITUDE`\*, `LONGITUDE`\* (\* optional) |
| Observed | 3,390 snapshots in 2025-08 (up to 166 a day). Each snapshot is the list of messages current at that moment (one sample held 1 message), so the same message repeats across snapshots. Optional fields are often absent (that sample had no district and no coordinates) |

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
