# Data sources: in use vs. reference

Found via the `list-files` API (`provider=hk-td` / keyword `search`), see
[`docs/raw_data.md`](raw_data.md) for full field-level docs on the sources
already in the pipeline.

## Main — downloaded (IDs as in `raw_data.md`)

1. S1 Traffic Speed, Volume and Road Occupancy (Raw Data) — `rawSpeedVol-all.xml`
2. S2 Traffic detector locations — `traffic_speed_volume_occ_info.csv`
3. S3 Current Weather Report (English RSS) — `CurrentWeather.xml`
4. S4, S5 Rainstorm + tropical cyclone warning databases — `rstorm.dat`, `tc.dat`
5. S6 Public holidays
6. S8 Daily total rainfall (HKO HQ) — `daily_HKO_RF_ALL.csv`

## Optional — downloaded for 2024–2025, not yet parsed

- **S11 Traffic Speeds of Road Network Segments (Processed Data)** — `irnAvgSpeed-all.xml`.
  TD's own segment aggregation; useful for cross-validation against our per-lane data.
  With **S14** `speed_segments_info.csv` (segment → route number) and **S12** Road Network
  (2nd Generation) `RdNet_IRNP.gdb.zip` (segment geometry: `segment_id` = CENTERLINE `ROUTE_ID`).
- **S13 Special Traffic News (2nd gen)** — `trafficnews.xml`. Lets us flag accident / closure
  periods as confounders, separate from rainfall.
- **S9, S10 Smart-lamppost traffic detectors** — `rawSpeedVol_SLP-all.xml` (same format as S1)
  and their locations; 17 detectors in Kwun Tong, Wan Chai, Yau Tsim Mong.
- **S7 Gridded rainfall nowcast** — radar forecast on a ~2 km grid; sensitivity check only.

## Reference — not verified in depth, may be worth a look later

- **Weather Warning Bulletin / Summary** —
  `https://rss.weather.gov.hk/rss/WeatherWarningBulletin.xml`,
  `https://rss.weather.gov.hk/rss/WeatherWarningSummaryv2.xml`.
  Covers thunderstorm, landslip, flooding-in-northern-NT, hot/cold warnings etc.,
  not just rainstorm/typhoon. **Checked 2026-09:** archived, but only about one snapshot
  a day (~10:20; 30 in 2025-08), so it cannot give start / end times of warnings the way
  `rstorm.dat` / `tc.dat` do.
- **Daily number of hours of reduced visibility** (per station) —
  `https://data.weather.gov.hk/weatherAPI/cis/csvfile/HKA/ALL/daily_HKA_RVIS_ALL.csv`
  (HKA = Hong Kong International Airport; swap the station code for others).
  Daily granularity only, limited value.
- **Daily mean wind speed** (per station) —
  `https://data.weather.gov.hk/cis/csvfile/<STATION>/ALL/daily_<STATION>_WSPD_ALL.csv`.
  Daily granularity only.
- **Journey Time Indicators (2nd Gen)** (`Journeytimev2.xml`) — road-level travel
  time, likely redundant with our detector speeds.
- **Car Journey Time data**, **Monthly Traffic and Transport Digest** (tunnel/bridge
  flow) — yearly/monthly aggregates, too coarse.
- **DSD Drainage Records** (culvert/tunnel geometry) — static GIS layers, could
  proxy flood-prone locations but needs spatial join work; high effort for
  indirect signal.
