# Cleaning record

L1 (`data/interim/l1/`) keeps every raw file as written. L2 is where the data gets cleaned; it
is not started yet. This file records what has been decided for L2 and what is still open.
Each entry gives the fields, the evidence, and who decided it and when. The findings behind
the entries are in [`raw_data.md`](raw_data.md). Months: 2024-05, 2025-07, 2025-08.

Principles:
- Nothing is removed from L1.
- When two sources disagree, both values are kept.
- A rule that changes values gets its counts (values and rows touched) here once L2 runs.

## Decided

| # | Sources | Decision | Evidence | Decided |
|---|---------|----------|----------|---------|
| D1 | S1, S2 | Keep both directions. S1 and S2 are joined on `detector_id` = `AID_ID_Number`. Every field is named `<source>_<field>`, with the field name as written: `s1_direction`, `s2_Direction`, `s2_Rotation`, … No choice between the two at this step. The join is a view, not a new file | S1 `direction` ≠ S2 `Direction` for 139 / 142 / 142 detectors. S1 does not change over the three months. S2 changed for 22 detectors across its versions, none after 2024-02 | user, 2026-09-30 |
| D2 | S2 | Join S2 version 2025-10 for all three months | 2024-02 → 2025-10 only adds 4 detectors (AID09115, AID09116, AID90008, AID90009) and changes no field of any other detector, so the version date makes no difference | user, 2026-09-30 |
| D3 | S1, S2 | Trim leading and trailing spaces; L1 keeps them | S1 `North ` / `South ` (6 detectors); S2 `Road_EN` and `South ` (2021-11 .. 2022-03) | user, 2026-09-30 |

## Open

"Proposal" marks a suggestion that has not been decided.

**S1 / S9 detector readings**

| # | Question | Evidence |
|---|----------|----------|
| O1 | TDS90026 lists two lanes as `Middle Lane` in 2025-07/08 (about 98k keys, readings differ). How to tell them apart? | 3 lanes in 2024-05 (Fast, Middle, Slow), 4 in 2025. The data dictionary codes 4 lanes as Fast, Middle Lane 2, Middle Lane 1, Slow. The lane's position in the file may tell them apart (the L1 row order within a file follows the XML; not verified yet) |
| O2 | A lane listed twice inside one detector block | S1: AID02215, 2024-05-30 08:25, 2 keys, readings differ. S9: 622 keys in 49 files (615 identical, 7 differ). Each period is in one file only, so there is no other copy to compare with. Proposal: keep identical duplicates once (lossless, count recorded); differing ones still open |
| O3 | 4 detectors without `direction` until 2025-07-25 10:34:30 (AID09115, AID09116, AID90008, AID90009; 268,072 readings) | Proposal, following D1: `s1_direction` stays null; `s2_Direction` gives E / E / W / W |
| O4 | Trim spaces (D3) in S9 and the other text sources too? | S5 lines 1695–1702 have values with a trailing space (`915 `, `3 `, …) |

**S13 traffic news**

| # | Question | Evidence |
|---|----------|----------|
| O5 | Bare `&` (5 files in 2024-05) is escaped before parsing; the value stays as written. OK? | Files listed in `checks/s13_bare_ampersands.csv` |
| O6 | Every file holds one message, so the archive cannot give "all incidents in force at time t". Enough for the project? | – |
| O7 | IDs 118305 / 118306 reused on 2025-07-12/13 ("DR Testing"): key by (ID, INCIDENT_NUMBER)? Drop the test message? ID 96671 was fetched before its ANNOUNCEMENT_DATE: leave it? | – |

**S11 segment speeds**

| # | Question | Evidence |
|---|----------|----------|
| O8 | `valid = N`: treat the speed as missing? | The speed is then always 50 / 70 / 80 / 100 / 110, one value per segment (maybe the speed limit; not checked against S12 `SPEED_LIMIT`). 16 / 11 / 12 segments have such integer speeds with `valid = Y` |
| O9 | 121.0: a cap? | 2,843 times, far more than each of 120.1 .. 120.9 (94–220) |

**S7 rainfall nowcast**

| # | Question | Evidence |
|---|----------|----------|
| O10 | 58 malformed files are not in L1: salvage the rows before the fault, or keep them out? | 44 have only leftover text after the last row, but 20250715-1030 shows that such a file can differ from another file with the same `updated` (515 values, ≤ 0.05 mm). Listed in `checks/s7_files.csv` |
| O11 | 3 parsed files have corrupted rows: drop the file, drop the rows, or keep them with a flag? | Found by format and grid-cell-set checks |
| O12 | Rainfall ≥ 1,000 mm per half hour in 2025 (max 5,407; 2024-05 max 583): radar artefacts? Cap? | – |

**S14 / S12 road network**

| # | Question | Evidence |
|---|----------|----------|
| O13 | S14 has three headers (`Road Name,Segment ID`, `route,irn_id`, `irn_id,ucase(route)`): rename to one pair? 135–161 S11 segments have no S14 route: take S12 CENTERLINE `ROUTE_NUM`? | `ROUTE_NUM` not checked |
| O14 | Which S12 version gives the geometry for a month? | 10 S11 segments of 2025-08 are only in older S12 versions; S12 L1 holds only the 4 versions of the three months. 4 layers changed field types from 2024-05 to 2025 |

**S4 / S5 / S8 (found 2026-09-30)**

| # | Question | Evidence |
|---|----------|----------|
| O15 | S5 `MSN` rows are not tropical cyclone signals: leave them out of the signal table? | 1,250 rows with `cyclone` and `signal` `0` and a compass direction (`E`, `N`, …) |
| O16 | S8 `Trace` (< 0.05 mm): as 0, or kept apart? `***` on 1900-02-29, a date that does not exist: drop the row? | `Trace` on 6,926 days (238 in 2022–2025); `***` once |
| O17 | S4 end time `24:00` (2 cases): read it as 00:00 of the next day? | – |
