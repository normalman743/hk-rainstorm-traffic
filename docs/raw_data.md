# Raw Data Dictionary

This document describes every **raw** data source as it is published: where it comes
from, how it is accessed, its format and structure, what every field means, which
values actually occur, and the quirks found when we inspected real data. Processed
tables are described in [`processing.md`](processing.md) and
[`database_description.md`](database_description.md).

Figures quoted as "observed" come from a read-only audit of real data in September 2026
(traffic: 5 Aug 2025, a Black Rainstorm day, unless stated otherwise).

All times are **Hong Kong Time (HKT, UTC+8)** unless stated otherwise.

| ID | Source | Provider | Format | Used for | Downloaded by |
|----|--------|----------|--------|----------|---------------|
| [S1](#s1-traffic-detector-readings-rawspeedvol-allxml) | Traffic detector readings | Transport Department | XML, 1 file / min | Target variables | `src.pipeline` (step 3) |
| [S2](#s2-traffic-detector-locations-traffic_speed_volume_occ_infocsv) | Traffic detector locations | Transport Department | CSV | Detector attributes, district join | `src.download static` |
| [S3](#s3-current-weather-report-currentweatherxml) | Current Weather Report | Hong Kong Observatory | RSS/XML, hourly | District rainfall | `src.pipeline` (step 3) |
| [S4](#s4-rainstorm-warning-signals-rstormdat) | Rainstorm warning signals | Hong Kong Observatory | Tab-separated text | Warning state, event selection | `src.download warnings` |
| [S5](#s5-tropical-cyclone-warning-signals-tcdat) | Tropical cyclone signals | Hong Kong Observatory | Tab-separated text | Exclude typhoon periods | `src.download warnings` |
| [S6](#s6-public-holidays-enjson) | Public holidays | 1823 (HKSAR Government) | JSON | Day type | `src.download holidays` |
| [S8](#s8-daily-total-rainfall-daily_hko_rf_allcsv) | Daily total rainfall | Hong Kong Observatory | CSV | Day-level sanity checks | `src.download static` |

Considered but not used: [N1 road network segments](#n1-road-network-segments-speed_segments_infocsv),
[N2 station hourly rainfall](#n2-automatic-weather-station-hourly-rainfall-hourlyrainfallphp),
[S7 gridded rainfall nowcast](#s7-gridded-rainfall-nowcast-optional) (optional).

---

## How historical files are obtained

The live URLs of S1 and S3 always return the *latest* file. Past versions come from the
[DATA.GOV.HK Historical Archive API](https://data.gov.hk/en/help/api-spec):

| Endpoint | Parameters | Returns |
|----------|------------|---------|
| `https://app.data.gov.hk/v1/historical-archive/list-file-versions` | `url` (live URL), `start`, `end` (`YYYYMMDD`) | JSON: `timestamps` (one per archived version, `YYYYMMDD-HHMM`), `data-files` (ZIP bundles, usually one per month), `data-dictionary-dates` |
| `https://app.data.gov.hk/v1/historical-archive/get-file` | `url`, `time` | HTTP 302 redirect to the file. `time=YYYYMMDD-HHMM` gives one snapshot; `time=YYYYMMDD` (a bundle's timestamp) gives the whole bundle ZIP |

A traffic bundle is ~1 GB per month. Its members are named
`<url-encoded live URL>/<YYYYMMDD-HHMM>-rawSpeedVol-all.xml`, plus the data dictionary PDF.
Our downloader reads the bundle's ZIP index with HTTP range requests and fetches only the
members of the requested day (~31 MB compressed instead of 1 GB).

**Archive time ≠ measurement time.** A version's timestamp is when the archive captured the
file, not when it was measured (see S1 and S3).

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
| lane | `valid` | `Y`/`N` | – | – | TD's validity flag; `N` on 0.5 % of readings. `N` rows have normal-looking values, so only the flag identifies them |

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
| Format | CSV, UTF-8 with BOM, 807 rows × 11 columns, one row per detector |
| History | Latest version only (detectors added later appear, removed ones do not) |

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
| URL | `https://data.weather.gov.hk/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv` |
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

## Not used (S7 is an optional extension)

### N1. Road network segments (`speed_segments_info.csv`)

`https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv`,
4,255 rows × 2 columns: `irn_id` (segment ID) and `ucase(route)` (the **route number** the
segment belongs to; 174 values, e.g. `9` has 423 segments). It has no coordinates and no link
to detectors; it belongs to the processed segment-speed feed `irnAvgSpeed-all.xml`. Our unit
of analysis is the detector, so it is not used.

### N2. Automatic weather station hourly rainfall (`hourlyRainfall.php`)

`https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en`: JSON with
`obsTime` and, for each of 36 stations, `automaticWeatherStation`, `automaticWeatherStationID`,
`value`, `unit`. **It is not in the Historical Archive** (the API returns `Not Found` for every
date range), so it can only be collected live. This is why rainfall is matched to roads by district (S3).

### S7. Gridded rainfall nowcast (optional)

`https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv`, archived
from ~July 2022, ~96 files per day. Each file is a 121 × 121 grid (≈ 2 km) × 4 lead times (+30 to
+120 min), with columns `Updated Date and Time`, `Ending Date and Time`, `Latitude`,
`Longitude`, `Half-hourly Nowcast Accumulated Rainfall (mm)`. It is a radar-based
**forecast**, not a gauge measurement, so at most it could serve as a finer-grained sensitivity check.
