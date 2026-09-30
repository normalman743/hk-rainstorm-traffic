# Cleaning record

L1 (`data/interim/l1/`) keeps every raw file as written. L2 (`data/interim/l2/`) is where the
data gets cleaned: `src.clean.l2_s1`, `l2_s3` and `l2_ref`; counts in "Applied" below. This file records what has been decided for L2 and what is still open.
Each entry gives the fields, the evidence, and who decided it and when. The findings behind
the entries are in [`raw_data.md`](raw_data.md). Months: 2024-05, 2025-07, 2025-08.

Scope (user, 2026-10-01): the main sources (S1–S6, S8) first; the optional sources (S7, S9,
S11–S14) are set aside, and their open questions (O5–O14 and the S9 parts of O2, O4, O18)
wait.

Principles:
- Nothing is removed from L1.
- When two sources disagree, both values are kept.
- L2 leaves no NA behind: each problem is either estimated or dropped, with the method chosen
  by the kind of problem (user, after talking with the course teacher, 2026-10-01):
  - a few values missing, with trustworthy data around them: estimate (interpolation, or a
    ratio to the other lanes of the same block);
  - the same value given twice: the mean;
  - bad or mostly missing data, few of it in a large source: drop.
  Estimated and averaged values are flagged. Before dropping, check that the rows do not
  cluster in rain periods. S1 periods the archive did not fetch are absent rows, not NA, and
  are not filled.
- A rule that changes or drops values gets its counts (values and rows touched) here once L2 runs.

## Decided

| # | Sources | Decision | Evidence | Decided |
|---|---------|----------|----------|---------|
| D1 | S1, S2 | Keep both directions. S1 and S2 are joined on `detector_id` = `AID_ID_Number`. Every field is named `<source>_<field>`, with the field name as written: `s1_direction`, `s2_Direction`, `s2_Rotation`, … The join is a view, not a new file. **The analysis uses `s1_direction`** (user, 2026-10-01); `s2_Direction` and `s2_Rotation` stay in the view for reference only | S1 `direction` ≠ S2 `Direction` for 139 / 142 / 142 detectors. S1 is consistent: one direction per detector in each month, and the same in all three months. S2 changed for 22 detectors across its versions, none after 2024-02 | user, 2026-09-30; S1 chosen 2026-10-01 |
| D2 | S2 | Join S2 version 2025-10 for all three months | 2024-02 → 2025-10 only adds 4 detectors (AID09115, AID09116, AID90008, AID90009) and changes no field of any other detector, so the version date makes no difference | user, 2026-09-30 |
| D3 | S1, S2 | Trim leading and trailing spaces; L1 keeps them | S1 `North ` / `South ` (6 detectors); S2 `Road_EN` and `South ` (2021-11 .. 2022-03) | user, 2026-09-30 |
| D4 (was O1) | S1 | Rename in L2: in a detector block where `Middle Lane` occurs more than once, the `Middle Lane`s are numbered in file order, `Middle Lane 1` first (next to Fast). A block that repeats any other lane name, or mixes a repeated `Middle Lane` with numbered ones, raises (the one known case is dropped first, D5). Widest roads for reference: 6 lanes one way (AID04212 Island Eastern Corridor, AID07114 Kwun Tong Road: Fast, Middle Lane 1–4, Slow). L1 keeps `Middle Lane` and gains `lane_position` (the lane's place in the file) so the two can be told apart | Only TDS90026 writes two `Middle Lane`, in 2025-07/08 (3 lanes in 2024-05). Every other detector with more than one middle lane writes them as `Fast Lane, Middle Lane 1, Middle Lane 2, …, Slow Lane` in the file (every 200th file, all three months, no other order), so `Middle Lane 1` is next to Fast. TDS90026's order is always Fast, Middle, Middle, Slow (every 50th file: 926 + 1,037 blocks); the two middle lanes cannot be told apart by their values (median speed 67 / 68). TDS90026 also has a few 3-lane blocks in 2025 (`Fast, Middle, Slow`; 36 in the sample, speed ≈ 70 and volume ≈ 0); they are dropped (D12) | user, 2026-09-30 |
| D5 (was O2, S1 part) | S1 | AID02215, 2024-05-30 08:25:00: the two `Fast Lane` rows become one, and the two `Slow Lane` rows one, each field the mean of the two (speed, volume, occupancy, sd); flagged as averaged. `valid` is `Y` in all four | The only S1 block with a lane listed twice. Fast: speed 97 / 92, volume 5 / 4, occupancy 2 / 2; Slow: speed 105 / 86, volume 1 / 7, occupancy 0 / 4; sd 0. Not the block written twice (the order is Fast, Fast, Slow, Slow); the detector has 2 lanes in every other period, and 08:24:30 / 08:25:30 read Fast 79 / 90, Slow 81 / 83. Not a neighbouring period merged in: 08:24:30 and 08:25:30 are both present in their own files with other values, and no detector is missing at 08:25:00 that is present at 08:24:30 and 08:25:30 (646 detectors in all three). Periods the archive did not fetch (e.g. 08:23:00, 08:23:30) cannot be compared. 1 of 122,617,560 detector blocks | user, 2026-10-01 (first: drop; changed to mean the same day) |
| D6 | S1 | Re-date the 00:00:00 and 00:00:30 periods: their `date` is the previous day's, so L2 adds one day. No row is dropped | All 83 files holding 00:00 in the three months carry the day before (fetched 00:06–00:10) | user, 2026-10-01 |
| D7 | S1 | The 3 truncated files stay out (they do not parse); nothing to do in L2 | Fetched 2025-07-17 14:18, 2025-07-29 10:28, 2025-08-11 02:00; each is cut at 384 / 192 KiB and is a byte-for-byte prefix of a complete file fetched 1–3 min away, so no reading is lost | user, 2026-10-01 |
| D8 | S3 | The 3 rain periods with no bulletin are interpolated: per district, `low` and `high` each the mean of the hour before and the hour after; flagged as interpolated. Applied after D9 (a district not listed = 0 mm) | Periods 2025-07-18 16:45–17:45 (before: 1 district, 1 mm; after: no rain), 2025-08-18 21:45–22:45 (before: 18 districts, up to 33 mm; after: 16, up to 3 mm), 2025-08-23 10:45–11:45 (no rain before or after). No rainstorm signal (S4) in force in any of them. 3 of 2,232 hours. Interpolated rather than dropped so that the hourly rain series has no gaps for the analysis; S1 has many missing periods and is not interpolated | user, 2026-10-01 |
| D9 | S3 | A district not listed in a bulletin has 0 mm (`low` = `high` = 0) for that period, flagged as not listed. This includes the bulletins with no rainfall sentence (all 18 districts) | Of 2,231 bulletins, 1,419 have no rainfall sentence; of the 812 with one, 117 list 1 district and 129 all 18. No listed district is ever 0 mm: single values are ≥ 1 and ranges have `high` ≥ 1, so HKO lists a district only when at least one of its stations rounds to ≥ 1 mm. Against S8 (HKO HQ, in Yau Tsim Mong), 93 days: Yau Tsim Mong never listed all day → S8 0 or Trace on 38 days, 0.1–0.9 mm on 4, ≥ 1 mm on 2; listed at least once → 0.1–0.9 on 5, ≥ 1 on 44. The two exceptions: 2025-07-09 (15.2 mm) fell 22:45–00:45, in bulletins dated the next day (Yau Tsim Mong 5–8 and 20–25 mm); 2024-05-02 (1.1 mm) was spread over hours each below 1 mm. Cost: rain below about 0.5 mm an hour counts as 0 | user, 2026-10-01 |
| D10 | S3 | The rain table keeps one row per (rain period, district). Where two files give the same period, their values must be equal and one is kept; unequal values raise | Two cases, both equal in all 18 districts: the 22:02 bulletin of 2025-08-18 (period 20:45–21:45) is in two files that differ only in the weather icon (`pic63.png` → `pic64.png`); the 17:00 bulletin of 2025-07-18 repeats the 16:02 bulletin's period 14:45–15:45 (the 17:11 bulletin then gives 15:45–16:45) | user, 2026-10-01 |
| D11 | S2, S3 | A detector's rain district is its S2 `District`, through a fixed name map to the S3 names: `Eastern` → `Eastern District`, `Southern` → `Southern District`, `Islands` → `Islands District`, `North` → `North District`, `Central & Western` and `Central and Western` → `Central & Western District`; the other 13 names are the same. A name not in the map raises. The district is not re-derived from coordinates. `low` and `high` are both kept; which one the analysis uses is an analysis choice | Every S1 detector of the three months is in S2 2025-10. S2 covers all 18 S3 districts (9 to 131 detectors each). `Central and Western` is written for one detector only (TDSIEC10001, Harcourt Road near Tim Mei Avenue - Eastbound); `Central & Western` for 13. No district boundary data is on disk | user, 2026-10-01 |
| D12 (was O18, part) | S1 | TDS90026: drop the 3-lane blocks of 2025 (1,846 blocks: 1,143 in 2025-07, 703 in 2025-08). Its 4-lane blocks are kept (D4). Its 3-lane blocks of 2024-05 are normal and kept | Tuen Mun Road near Sham Tseng - Westbound (2). In the 2025 3-lane blocks, Middle Lane volume is 0 in 97–98 % of rows (mean 0.06 / 0.11) and median speed is 70 in every lane of 2025-07, while `valid` is `Y` in 99.7–99.9 %. Its 4-lane blocks in the same months read Middle mean volume 5.8, median speeds 77 / 67 / 42; its 3-lane blocks of 2024-05 read median speeds 76 / 69 / 62, mean volumes 8.0 / 7.1 / 3.7. Neighbours TDS90025 and TDS90027 are on the same road | user, 2026-10-01 |
| D13 (was O18, part) | S1 | TDS90036: in the 2,022 blocks without `Slow Lane`, the Slow Lane is estimated from the other three lanes of the same block and the detector's own ratios by hour of day, taken from its complete blocks of the same month: volume and occupancy = the other lanes' total × (Slow total / other total); speed = the other lanes' mean speed × the median of (Slow speed / other lanes' mean speed). Flagged as estimated. `sd` = the other lanes' mean sd × the median of (Slow sd / other lanes' mean sd); `valid` = true only if all three other lanes are valid; a block whose other lanes have volume 0 gets Slow volume 0 (the ratio is by hour over the month, so it exists; an hour without one raises) (Claude, 2026-10-01, pending review) | Tuen Mun Road near Tuen Mun Road Bus-Bus Interchange - Westbound (1); lanes Fast, Middle Lane 1, Middle Lane 2, Slow. 2,022 blocks without Slow (170 in 2024-05, 1,852 in 2025-07, on 21 days, spread over the hours of the day), 162,503 complete. In the complete blocks (all three months together) Slow carries 1.2–5.9 % of the volume by hour (about 3 % by day); its speed is 0.59–0.85 of the other lanes' mean by hour (median), with a wide spread (10th–90th percentile 0.42–0.97). Estimated rather than dropped because the other three lanes are real readings and Slow carries little of the volume | user, 2026-10-01 |
| D14 (was O18, part) | S1 | Drop the 40 blocks (38 detectors) in which lanes are missing for a single block | 36 of the 38 detectors on 2024-05-01/02, AID07104 on 05-11, AID04218 on 05-17; AID02120 and AID07203 twice. Many keep 1 lane of 3–4 (e.g. AID02120: Fast only of 4), and in most the detector is also absent at ±30 s (both neighbours present only for AID02215, D5), so there is nothing to interpolate from | user, 2026-10-01 |
| D15 (was O18, part) | S1 | The 24 detectors whose lanes change once (between 2024-05 and 2025-07) are kept as they are | More lanes (e.g. TDS91016 3 → 4, TDS90070 4 → 5), fewer (TDSTCKR10001 Middle+Slow → Slow) or other names for the same count (AID02116 `Fast, Middle` → `Fast, Slow`); read as a change on the road or in the equipment, not an error | user, 2026-10-01 |
| D16 (was O3) | S1 | AID09115, AID09116, AID90008, AID90009: before 2025-07-25 10:36:00, `direction` is taken from their own later S1 readings (`East`, `East`, `West`, `West`); flagged as filled | 268,072 readings without `direction`. Each S1 detector has one direction in every month and the same in all three months (D1); S2 2025-10 gives the same four | user, 2026-10-01 |
| D17 (was O4, S5 part) | S5 | Trim leading and trailing spaces from the fields after they are split, before typing | 10 values in 6 lines (1695, 1696, 1698, 1700, 1702, 1775): `915 `, `3 `, … | user, 2026-10-01 |
| D18 (was O15) | S5 | `MSN` rows are left out of the signal table; count recorded | 1,250 rows with `cyclone` and `signal` `0` and a compass direction; not tropical cyclone signals; HKO's own warning database leaves them out [ext] | user, 2026-10-01 |
| D19 (was O16) | S8 | `Trace` = 0 mm, flagged as trace (as D9: under 1 mm an hour is 0 in S3). The 1900-02-29 row (`***`) is left out | `Trace` on 6,926 days (238 in 2022–2025); 1900-02-29 does not exist and is outside the study period | user, 2026-10-01 |
| D20 (was O17) | S4 | End time `24:00` = 00:00 of the next day; any other `24:xx` raises | Line 56: 2000-04-02 22:15 → 24:00, 105 min; line 596: 2019-05-20 22:05 → 24:00, 115 min; both equal end − start with that reading [ext, checked]. Both outside the study period | user, 2026-10-01 |
| D21 | S1 | `occupancy = -1` becomes 0, flagged; `-1` with a volume other than 0, or any other negative occupancy, raises | 7,687 rows in L1 (three months), every one with `volume = 0`, so read as "no vehicle, occupancy not computed" | Claude, 2026-10-01, pending review |
| D22 | S5 | A time flagged `S` (columns 10 and 15) is Hong Kong summer time (HKT + 1 h) and is moved back 1 h to HKT | With `S` = summer time, `duration` = end − start in all 1,262 signal rows; read as written, the 3 rows that start in `S` and end in `X` (e.g. line 86, BETTY 1953-10-31 → 11-01: 35 h 15 min apart, `duration` 3615) are 1 h short. `S` occurs 1946–1979 only; Hong Kong stopped summer time after 1979. 451 signals touched, none in the study period | Claude, 2026-10-01, pending review |

## Applied (L2, 2026-10-01)

Counts from `data/interim/checks/l2_s1_counts.csv`, `l2_s3_counts.csv`, `l2_ref_counts.csv`;
the dropped S1 blocks are listed in `l2_s1_dropped.csv`.

| Rule | What | 2024-05 | 2025-07 | 2025-08 |
|------|------|--------:|--------:|--------:|
| – | S1 L1 rows in | 123,072,815 | 99,901,116 | 109,903,740 |
| D3 | S1 rows whose `direction` lost a space | 1,048,442 | 857,783 | 948,206 |
| D4 | S1 blocks with `Middle Lane` numbered | 0 | 46,384 | 51,709 |
| D5 | S1 rows averaged (4 in → 2 out) | 4 → 2 | 0 | 0 |
| D6 | S1 rows re-dated | 98,142 | 109,729 | 121,594 |
| D12 | S1 blocks (rows) dropped | 0 | 1,143 (3,429) | 703 (2,109) |
| D13 | S1 blocks with Slow Lane estimated (1 row each) | 170 | 1,852 | 0 |
| D14 | S1 blocks (rows) dropped | 40 (48) | 0 | 0 |
| D16 | S1 rows with `direction` filled | 0 | 268,072 | 0 |
| D21 | S1 rows with occupancy −1 set to 0 | 3,085 | 2,322 | 2,280 |
| – | S1 L2 rows out | 123,072,935 | 99,899,539 | 109,901,631 |

S1 rows out = in − D5 (2) − D12 − D14 + D13. S3 (all months on disk): 2,231 bulletins; 1,419
without a rainfall sentence (period by the lag rule; the one bulletin with a sentence that
differs from the rule is the 2025-07-18 17:00 repeat, D10); D10 2 periods; D9 33,340 rows; D8
3 periods; 40,176 rows out (2,232 periods × 18 districts). S2: 790 detectors, 128 renamed by
D11. S4: 974 signals, D20 2. S5: 1,262 signals, D18 1,250 rows out, D17 10 values, `2400` 2,
D22 451 signals. S6: 170 holiday dates (2018–2027). S8: 49,491 days, D19 6,926 Trace, 1 row out.

**Drop check against rain** (principle above). D12 blocks in a rainstorm warning: 10 of 1,143
(0.9 %) in 2025-07, when warnings cover 4.3 % of the month; 66 of 703 (9.4 %) in 2025-08
(8.9 %). In an hour with rain in the detector's district (S3 `high` > 0): 19.9 % (the district,
Tuen Mun, has rain in 18.4 % of the hours) and 14.5 % (20.9 %). Not clustered in rain. D14:
5 of 40 blocks in a warning (the month: 3.8 %), 12 of 40 in rain (14.2 % of district-hours);
36 of the 40 are on 2024-05-01/02; 48 rows in all, so the drop cannot move a result.

## Open

"Proposal" marks a suggestion that has not been decided. "[ext]" marks evidence from the external review of O1–O17 (GPT, 2026-09-30); "[ext, checked]" means Claude re-ran it on L1 the same day with the same result (script kept outside the repo).

**S1 / S9 detector readings**

| # | Question | Evidence |
|---|----------|----------|
| O2 | A lane listed twice inside one detector block. S1 part decided (D5); the S9 part waits with the optional sources | S1: only AID02215, 2024-05-30 08:25:00 (20240501.zip:31022, `20240530-0832-rawSpeedVol-all.xml`). Order in the file: Fast 97 / Fast 92 / Slow 105 / Slow 86 (speed; all `valid = Y`), so not the block written twice (that would be Fast, Slow, Fast, Slow). The detector has 2 lanes in every other period of the ten files around it; 08:24:30 (Fast 79, Slow 81) does not match the extra readings. Looks like a system fault: the period reported twice. S9: 622 keys in 49 files (615 identical, 7 differ, all 7 in 2024-05); lane order not yet looked at. Each period is in one file only, so there is no other copy to compare with. Proposal: keep both, told apart by `lane_position`, flagged; identical S9 duplicates kept once (count recorded). Next check: every detector's lane lists per month (all changes of lanes, not only repeats) |
| O18 | A detector's lanes change over time. What does a lane mean across months? S1 part decided (D12–D15); the S9 part waits with the optional sources | Blocks in time order, consecutive blocks with the same lane list = one run (`checks/lanes_runs.csv`, `lanes_classes.csv`, 2026-09-30). **S1, 784 detectors:** 719 always the same. 24 change once, all between 2024-05 and 2025-07 (the date is not in the data): more lanes (e.g. TDS91016 3 → 4, TDS90070 4 → 5), fewer (TDSTCKR10001 Middle+Slow → Slow) or other names for the same count (AID02116 `Fast, Middle` → `Fast, Slow`; TDS91005 `Fast, ML1, ML2` → `Fast, Middle, Slow`). 38 have one block (30 s) with lanes missing, 36 of them on 2024-05-01/02 (the other two: AID07104 05-11, AID04218 05-17) (4 at 2024-05-02 07:44:00, just before a gap to 09:10); AID02215 is the one block with lanes added (O2). TDS90026 flips between 4 and 3 lanes through 2025 (1,846 runs; the 3-lane blocks read speed ≈ 70, volume ≈ 0). TDS90036 loses its Slow Lane for about 20–30 min at a time (143 runs). **S9, 20 detectors:** the lane order in the file is not fixed (e.g. `Slow, Fast` in 12 % of blocks), so `lane_position` is not a place on the road in S9 and D4 is S1 only. 4 detectors (AID20022, AID20023, AID20032, AID20059) have two lane sets, about 58k blocks each, likely 2024-05 vs 2025 (not checked). Blocks with a name twice: a few hundred, see O2 |
| O4 | Trim spaces (D3) in S9 and the other text sources too? S5 part decided (D17); S9 and S13 wait with the optional sources | S5: 10 values in 6 lines have a trailing space: lines 1695, 1696, 1698, 1700, 1702 and 1775 (`915 `, `3 `, …) [ext, checked]. S13 `CONTENT_EN` has leading / trailing white space in 5,907 of 5,908 rows [ext, checked]; S3 `description` also [ext]. Proposal: trim identifiers, codes, dates, times and numbers before typing and joining, after the fields are split; free text (S13 content, S3 description) stays as written |

**S13 traffic news**

| # | Question | Evidence |
|---|----------|----------|
| O5 | Bare `&` (5 files in 2024-05) is escaped before parsing; the value stays as written. OK? | Files listed in `checks/s13_bare_ampersands.csv`; all five in `Kowloonbay International Trade & Exhibition Centre` [ext]. Proposal: accept; any other XML error still raises |
| O6 | Every file holds one message, so the archive cannot give "all incidents in force at time t". Enough for the project? | Longest gap between fetches within a day 536 / 460 / 514 min; latitude / longitude always empty [ext]. 194 (ID, INCIDENT_NUMBER) keys are fetched as NEW / UPDATED after their first CLOSED [ext, checked]. ID 119648: U 08:43, C 08:48, U 08:49, C 08:50, U 08:51, C 08:52 (2025-08-02) — two versions served in turn, so not a road closed again; the first CLOSED is not a safe end time. Proposal: S13 explains events it saw; "no message" means "not seen", not "no incident"; keep every fetch in order |
| O7 | IDs 118305 / 118306 reused on 2025-07-12/13 ("DR Testing"): key by (ID, INCIDENT_NUMBER)? Drop the test message? ID 96671 was fetched before its ANNOUNCEMENT_DATE: leave it? | 5,908 rows, 4,761 (ID, INCIDENT_NUMBER) keys, 4,759 IDs [ext, checked]. `DR Testing` in two rows: ID 118306 IN-25-04137 NEW, and ID 116872 IN-25-03541 CLOSED (text added to an older message) [ext, checked]. ID 96671: announced 2024-05-11 23:19, first fetched 12:14 (12:17 is the copy kept in L1); ID 120705: announced 22:00, first fetched 21:56 [ext, checked]. Proposal: keep (bundle, index) as the identity of a message version; leave out the two test rows from incident analysis; keep both times and flag, change neither |

**S11 segment speeds**

| # | Question | Evidence |
|---|----------|----------|
| O8 | `valid = N`: treat the speed as missing? | The speed is then always 50 / 70 / 80 / 100 / 110, one value per segment. 16 / 11 / 12 segments have such integer speeds with `valid = Y`. N rows 4,239,192 / 914,518 / 770,817; segments with N 947 / 723 / 788, of which 297 / 144 / 193 have a same-month S12 `SPEED_LIMIT` (joined on `ROAD_ROUTE_ID`), and the N speed is one of their limits for 296 / 144 / 192 [ext, checked]. The data specification defines N as offline [ext]. Proposal: speed for analysis = missing when N (no filling with the limit); integer speeds with Y kept, flagged |
| O9 | 121.0: a cap? | 2,843 times (798 / 1,115 / 930), all `valid = Y`, the maximum in every month; far more than each of 120.1 .. 120.9 (94–220) [ext]. Proposal: keep, flag as a likely cap |

**S7 rainfall nowcast**

| # | Question | Evidence |
|---|----------|----------|
| O10 | 58 malformed files are not in L1: salvage the rows before the fault, or keep them out? | 44 have only leftover text after the last row, but 20250715-1030 shows that such a file can differ from another file with the same `updated` (515 values, ≤ 0.05 mm). Listed in `checks/s7_files.csv`. The external review found 44 files whose full grid can be recovered (one, 20240523-0915, only after removing a stray `202`) and partial rows in 14 more [ext]. Proposal (Claude): the 58 are 0.65 % of 8,910 files and overlap with the files around them; if anything, take in only files whose full grid parses as written with only trailing leftover (an L1 change, to be done with the other L1 changes); no file is edited to parse |
| O11 | 3 parsed files have corrupted rows: drop the file, drop the rows, or keep them with a flag? | Found by format and grid-cell-set checks. 9 rows (6, 2, 1); one is latitude `21.60`, the grid value 21.600 written short [ext]. Proposal: keep the rest of the three files; the 8 rows that are not a grid cell are left out of analysis, flagged |
| O12 | Rainfall ≥ 1,000 mm per half hour in 2025 (max 5,407; 2024-05 max 583): radar artefacts? Cap? | 649 rows in 58 files (2025-07), 1,493 in 77 (2025-08); none inside lat 22.15–22.57, lon 113.83–114.45 (a rough box, not the border); maximum inside the box 206.19 / 148.53 / 252.81 [ext, checked]. Proposal: keep, flag ≥ 1,000 as suspect, no cap; check whether any falls on a studied road once cells are matched to roads |

**S14 / S12 road network**

| # | Question | Evidence |
|---|----------|----------|
| O13 | S14 has three headers (`Road Name,Segment ID`, `route,irn_id`, `irn_id,ucase(route)`): rename to one pair? 135–161 S11 segments have no S14 route: take S12 CENTERLINE `ROUTE_NUM`? | `ROUTE_NUM` is a route number, not a road name; it has a value for only 2 / 4 / 4 of the missing segments, `STREET_ENAME` for 130 / 149 / 143 (some `-99`) [ext]. Proposal: map the headers by name (the column order changes), not position; keep S14 route, S12 `STREET_ENAME` and `ROUTE_NUM` as separate fields |
| O14 | Which S12 version gives the geometry for a month? | 10 S11 segments of 2025-08 are only in older S12 versions; S12 L1 holds only the 4 versions of the three months. 4 layers changed field types from 2024-05 to 2025. Geometry of shared S11 segments changed for 65 / 79 (2025-07 versions) and 92 (2025-08) against 2024-05 [ext]. Proposal (Claude): the month's own version; the 10 missing segments from the latest older version that has them (needs versions not in L1 yet) |
