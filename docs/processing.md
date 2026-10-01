# Data Processing

> 中文版：[`processing.zh.md`](processing.zh.md)

How raw sources ([`raw_data.md`](raw_data.md)) become tables. The commands are in the
README ("Processing"); every cleaning rule, with its evidence and counts, is in
[`cleaning.md`](cleaning.md); the columns of each table are in
[`database_description.md`](database_description.md) §3. Study months: 2024-05, 2025-07,
2025-08.

```
data/raw/                     as downloaded (src.download, hkgovdata plans)
  └─ L1  src.clean.*_parse    data/interim/l1/<source>/       every file as written, strings
      └─ L2  src.clean.l2_*   data/interim/l2/<source>/       typed and cleaned, main sources only
          └─ L3  src.l3       data/interim/l3/<name>.parquet  detector × 15-min analysis table
              └─ src.analysis.*   report/figures/*.pdf, report/results/*.json|csv
```

Every step raises on a case no rule covers, with the offending rows, instead of skipping it.
Counts of every step go to `data/interim/checks/`.

---

## L1: raw as written (`src.clean`)

- `src.clean.manifest` lists every file in the monthly bundles of the given months and groups
  byte-identical copies (the archive often stores the same file several times); each parser
  reads one file per group.
- One parser per source (`s1_parse`, `s3_parse`, `signals_parse`, `s6_parse`, `s8_parse`,
  `versions_parse` for S2 / S10 / S14; the optional `s7_parse`, `s11_parse`, `s12_parse`,
  `s13_parse`). Every value is kept as a string, an absent element is null and an empty one
  `""`; each row keeps the file it comes from (`bundle`, `index`).
- Checks (`s1_periods`, `s1_rows`, `*_checks`, `structure`) only describe the data; their
  findings are in [`raw_data.md`](raw_data.md).

## L2: cleaned per source (`src.clean.l2_s1`, `l2_s3`, `l2_ref`)

| Script | Output | Rules |
|--------|--------|-------|
| `l2_s1` | `s1/<YYYYMM>.parquet`: one row per lane and 30-s period (123.1 M / 99.9 M / 109.9 M rows) | D3 trim, D4 number repeated `Middle Lane`s, D5 average the one doubled block, D6 re-date the 00:00 periods, D12 drop TDS90026's 3-lane blocks of 2025, D13 estimate TDS90036's missing Slow Lane, D14 drop single blocks with lanes missing, D16 fill a missing `direction`, D21 `occupancy = -1` → 0 |
| `l2_s3` | `s3/rain.parquet`: one row per hour (HH:45 → HH:45) and district, 40,176 rows | D9 a district not listed has 0 mm, D10 one row per hour and district, D8 a single missing hour is the mean of its neighbours |
| `l2_ref` | `s2/detectors.parquet` (790), `s4/rainstorm.parquet` (974), `s5/tc.parquet` (1,262), `s6/holidays.parquet` (170), `s8/daily.parquet` (49,491) | D2 S2 version 2025-10, D3, D11 S2 district → S3 district name; D20 `24:00`; D17, D18, D22 for S5; latest version per holiday date; D19 for S8 |

Rows changed or made by a rule carry it in `l2_rule`. Missing 30-s periods are not filled in
L2: they are absent rows. The optional sources (S7, S9–S14) have no L2 yet.

## L3: the analysis table (`src.l3`)

One row per detector and slot (default 15 min). Each step has a default and alternatives
(P1–P11 in [`PROPOSAL.md`](PROPOSAL.md); `python -m src.l3 option=value` builds a variant).
The steps, with the counts of the default table:

1. **Readings** (L2 S1, 332.9 M): P1 leaves out `valid = N` (9.8 M); P2 leaves out speed 0 or
   > 130 km/h with volume > 0 (2.4 M); 12.2 M together.
2. **Lane slots** (17.8 M): P3 leaves out a lane slot whose readings are all identical with
   occupancy or volume above 0, two slots or more in a row (1,122).
3. **Detector slots** (6.56 M): P4 speed = volume-weighted mean of the lane readings (an empty
   lane's speed is the speed limit, not a measurement); flow = vehicles per hour over all
   lanes; occupancy = mean. A slot in which no lane has a vehicle has no speed and is left out
   (34,691). `periods` / `coverage` record how many 30-s periods the slot had.
4. **Gaps**: P6 a run of 1–2 missing slots between two present ones is interpolated and flagged
   (25,787).
5. **Context**: slots outside the three months are left out (1,469); S2 (district, position,
   road); the district's rain of the hour (P7 midpoint of the range; P8 the hour the slot is
   in) and of the hour before, and the territory maximum; slots without a rain hour are left
   out (7,273: after 22:45 on a month's last day, that bulletin is in the next month's
   files); warning level and minutes since the warning episode began (signals that follow on
   without a break are one episode); TC signal; day type (weekday / Saturday / Sunday or
   holiday). A slot is **dry** with no rain in the district this hour and the hour before, no
   rainstorm warning and TC signal below 8.
6. **Baseline** (P10): per detector, season (2024-05; 2025-07 + 08), day type and slot of day,
   the median speed, flow and occupancy of the dry slots; a slot with fewer than 3 dry slots
   behind its baseline is left out (109,646). `ratio` = speed / base speed, `flow_ratio` =
   flow / base flow.

Result: 6,430,886 rows (`data/interim/l3/default.parquet`). P9 (warning encoding) and P11
(cyclone signal ≥ 8 left out) are applied by the analysis, not here.

## Analysis (`src.analysis`)

| Script | What | Output |
|--------|------|--------|
| `eda` | coverage, rain events, speed / flow by rain and warning level, onset, 2025-08-05 | `report/figures/eda_*.pdf`, `report/results/eda.json` |
| `rq1` | per-detector sensitivity (`s_warn`, `s_rain`, exposure-adjusted, mixed-model slope), stability, districts, map | `rq1_*.pdf`, `rq1.json`, `rq1_detectors.csv` |
| `rq2` | event-held-out prediction of the speed ratio and of congestion (baseline, ridge / logistic, LightGBM, four feature sets) | `rq2_models.pdf`, `rq2.json` |
| `rq3` | one preprocessing alternative at a time: ranking, headline ratios, prediction skill | `rq3_ablation.pdf`, `rq3.json`, `rq3.csv` |

---

## Reference data (`python -m src.download ...`)

Besides saving the raw files, `warnings` and `holidays` derive small tables
(`rainstorm_warnings.csv`, `rainstorm_episodes.csv`, `tc_signals.csv`, `public_holidays.csv`).
L2 and L3 do not read them: they work from the L1 of the raw files (`rstorm.dat`, `tc.dat`,
the S6 versions) by their own rules. The tables are kept for reference.

```bash
python -m src.download warnings         # S4, S5 -> data/raw/hko/, data/interim/rainstorm_episodes.csv
python -m src.download static           # S8, S2 live copy -> data/raw/hko/, data/raw/td/
python -m src.download static-history   # S2, S14 archived versions -> data/raw/td/<name>/<YYYYMMDD>.csv
python -m src.download holidays         # S6 -> data/raw/calendar/public_holidays.csv
```

### `warnings` (`src/download/warnings.py`)

**Input:** S4 `rstorm.dat`, S5 `tc.dat`. Both raw files are also saved to `data/raw/hko/`.

Rainstorm signals → `data/raw/hko/rainstorm_warnings.csv` (one row per signal):
- Columns 2–11 become `start` and `end`. **`24:00` is rolled over to 00:00 the next day**
  (`_dt` adds hours and minutes to the date instead of constructing the time directly).
- `level` becomes 1 / 2 / 3 for A / R / B, plus `level_name`, and `duration_min` = end − start.
  The file's own duration columns are not used.
- `provisional` is True for rows after a `UUUU` line.

Episodes → `data/interim/rainstorm_episodes.csv`:
- Signals sorted by start are merged while the next signal starts **no later than** the
  current episode ends (HKO records upgrades with identical end/start minutes).
- Each episode keeps `start`, `end`, `max_level`, `n_signals`, `duration_min`, `provisional`.

Tropical cyclone signals → `data/raw/hko/tc_signals.csv`:
- Rows with intensity `MSN` are dropped (they are not cyclone signals).
- `HHMM` times are left-padded (`10` → 00:10), and `2400` rolls over as above.
- `NIL` names become empty (they show as NA when read with pandas).

### `static` (`src/download/static.py`)

S2, S14 and S8 are saved **unchanged**. If the HKO server resets the connection (this
happens from some cloud hosts), the latest copy is fetched from the Historical Archive instead.

### `static-history` (`src/download/static.py`)

Every archived version of S2 and S14: for each monthly bundle, its CSV member is saved
unchanged as `data/raw/td/<name>/<bundle YYYYMMDD>.csv`; versions already on disk are skipped.

### `holidays` (`src/download/holidays.py`)

All archived versions of S6 since 2019, plus the live file, are parsed. The date comes from
`dtstart[0]` and the name from `summary`. Later versions overwrite earlier ones for the same
date. Output: `data/raw/calendar/public_holidays.csv` (`date`, `name`), 2018–2027.
The individual versions are not saved.

---

## Choosing days: `python -m src.download select-days` (`src/download/select_days.py`)

Kept for later analysis; the current pipeline does not depend on it.

- **Event days:** every calendar day touched by an episode with `max_level ≥ --min-level`,
  extended by `--pad-hours` (default 3) before and after. Only episodes starting in
  `--years` (default 2022–2025) and `--months` (default 4–10) count.
- **Control days:** for each event day, the same weekday 1 … `--controls` (default 2) weeks
  earlier, provided that day has **no rainstorm signal of any level and no tropical cyclone
  signal**, and is not itself an event day.
- Days before 2021-06-01 (start of the traffic archive) are dropped.

Output: `data/interim/day_manifest.csv` with `date`, `role` (`event` / `control`), `episode_ids`
(space-separated; empty for controls), `max_level` (0 for controls), `max_level_name`.
The current file has 362 days (155 event, 207 control), 2021-06 .. 2025-09.
