# Data Processing

How raw sources ([`raw_data.md`](raw_data.md)) become the processed tables
([`database_description.md`](database_description.md)): every step, the code that does
it, what it changes, what it deliberately leaves alone, and how the result is checked.

## Principles

1. **No cleaning in the pipeline.** Steps 1–4 only restructure data: parsing, type
   conversion, deduplication of exact repeats, fixing timestamps. Every value is kept as
   published, including placeholder speeds, `valid = N` and out-of-range readings.
   Cleaning choices are the experiments of the project (P1–P11 in [`PROPOSAL.md`](../PROPOSAL.md))
   and are applied later, so their effect can be measured.
2. **Nothing large touches the disk.** Raw XML is read straight from the downloaded ZIP,
   converted to Parquet, and the ZIP is deleted.
3. **Every output records the code version that made it.** Outdated files are rebuilt,
   never silently reused.
4. **Every run is checked.** `src.validate` checks invariants and profiles every table
   after each pipeline run.

## Overview

```
                    STEP 1  reference data (seconds)
S4 rstorm.dat ─┐
S5 tc.dat ─────┴─ src.download warnings ──▶ data/raw/hko/rainstorm_warnings.csv, tc_signals.csv
                                            data/interim/rainstorm_episodes.csv
S2, S8, N1 ────── src.download static ────▶ data/raw/td/*.csv, data/raw/hko/daily_HKO_RF_ALL.csv
S6 ────────────── src.download holidays ──▶ data/raw/calendar/public_holidays.csv

                    STEP 2  choose days
episodes + TC ─── src.download select-days ─▶ data/interim/day_manifest.csv

                    STEP 3  per day: download -> parse -> Parquet -> delete ZIP (~24 s/day)
S1 (archive) ──┐                            ┌▶ data/processed/traffic_lane/<YYYY>/<YYYYMMDD>.parquet
S3 (archive) ──┴─ src.pipeline ─────────────┼▶ data/processed/rainfall_district/<YYYY>/<YYYYMMDD>.parquet
                                            ├▶ data/processed/coverage.csv
                                            └▶ src.validate ─▶ data/processed/validation_report.md

                    STEP 4  detector x 15 min (~10 s/day)
traffic_lane ──── src.aggregate ──────────▶ data/processed/traffic_15min/<YYYY>/<YYYYMMDD>.parquet

                    ANY TIME
                  src.validate ──────────▶ validation_report.md, validation_checks.csv
```

```bash
python -m src.download warnings && python -m src.download static && python -m src.download holidays
python -m src.download select-days --min-level R
python -m src.pipeline --manifest          # runs src.validate at the end
python -m src.aggregate --manifest
python -m src.validate --manifest          # full check incl. traffic_15min
```

Every step skips work that is already done and current, so it can be re-run after an
interruption or a code change.

---

## Step 1 — Reference data

### `python -m src.download warnings` (`src/download/warnings.py`)

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

### `python -m src.download static` (`src/download/static.py`)

S2, N1 and S8 are saved **unchanged**. If the HKO server resets the connection (this
happens from some cloud hosts), the latest copy is fetched from the Historical Archive instead.

### `python -m src.download holidays` (`src/download/holidays.py`)

All archived versions of S6 since 2019, plus the live file, are parsed. The date comes from
`dtstart[0]` and the name from `summary`. Later versions overwrite earlier ones for the same
date. Output: `data/raw/calendar/public_holidays.csv` (`date`, `name`), 2018–2027.

---

## Step 2 — Choose days: `python -m src.download select-days` (`src/download/select_days.py`)

Downloading every day is ~1 GB per month, so only relevant days are taken:

- **Event days:** every calendar day touched by an episode with `max_level ≥ --min-level`,
  extended by `--pad-hours` (default 3) before and after. Only episodes starting in
  `--years` (default 2022–2025) and `--months` (default 4–10) count.
- **Control days:** for each event day, the same weekday 1 … `--controls` (default 2) weeks
  earlier, provided that day has **no rainstorm signal of any level and no tropical cyclone
  signal**, and is not itself an event day.
- Days before 2021-06-01 (start of the traffic archive) are dropped.

Output: `data/interim/day_manifest.csv` with `date`, `role` (`event` / `control`), `episode_ids`
(space-separated; empty for controls), `max_level` (0 for controls), `max_level_name`.
With `--min-level R` this gives 59 days (28 event + 31 control).

---

## Step 3 — Download and parse: `python -m src.pipeline` (`src/pipeline.py`)

For each source (`weather`, `traffic`) and day:

### 3a. Download (`src/download/archive.py`)

1. `list-file-versions` for the day returns the day's snapshot timestamps and the bundle
   (monthly ZIP) that contains them.
2. The bundle's ZIP index is read with HTTP range requests. Members named `<YYYYMMDD>-*-<file>`
   for the day are fetched in parallel (16 threads), each with one range request, decompressed,
   and CRC-checked.
3. **Duplicates:** members with the same name and the same CRC are fetched once. A same-name
   member with a different CRC would be kept under a suffixed name.
4. If no bundle exists yet (the current month), each snapshot is fetched individually instead.
5. The day is written to `data/raw/<source>/<YYYY>/<YYYYMMDD>.zip` (fast compression, level 1),
   ~31 MB for traffic.

### 3b. Parse traffic → `traffic_lane` (`src/parse/traffic.py`, version 3)

| Operation | Detail |
|-----------|--------|
| Scan | One regex pass per XML file tracks the current `<date>`, `<period_from>` and `<detector_id>`, and emits one row per `<lane>`. Tested equal to an ElementTree parse on a full day (3,611,987 rows) |
| `time` | `date` + `period_from` (the measurement time, never the file's archive time) |
| **Midnight fix** | If a period is > 12 h older than the file's archive time (taken from the member name), it is moved forward one day. This fixes the 00:00 period, which carries the previous day's `<date>`. Counted as `n_periods_redated` |
| **Truncated files** | Files not ending in `</raw_speed_volume_list>` are counted (`n_truncated_files`). Their complete lane readings before the cut are kept; an incomplete last lane is dropped by the regex |
| `sd` | `<s.d.>` is optional: missing (NaN) in files before ~18 Nov 2021 |
| Types | `speed`, `occupancy`, `volume` → `Int16`; `sd` → `float32`; `detector_id`, `lane`, `valid` → category. Non-numeric text would become NA (none observed) |
| Dropped | `direction` (in S2) and `period_to` (= `time` + 30 s) |
| **Deduplication** | Exact repeats of (`time`, `detector_id`, `lane`) from overlapping files are dropped, keeping the first. ~9 % of rows |
| Sort | by `detector_id`, `lane`, `time` |
| **Not done** | No row is removed or changed for its values: `volume = 0` placeholder speeds, `valid = N`, `speed > 130`, `occupancy = -1` and so on all stay |

### 3c. Parse weather → `rainfall_district` (`src/parse/weather.py`, version 1)

| Operation | Detail |
|-----------|--------|
| Text | HTML entities decoded, tags removed, whitespace collapsed |
| `bulletin_time` | From the title `Bulletin updated at HH:MM HKT DD/MM/YYYY` (not the archive time) |
| **Period** | From `Between H:MM [a.m./p.m.] and H:MM a.m./p.m.`: the end is converted to 24 h and anchored as the latest such time **not after** `bulletin_time` (handles midnight, noon and late bulletins); `period_start` = end − 1 h |
| Entries | The sentence after `rainfall recorded in various regions were:` is split on `;`. Each entry must match `<District> <min> [to <max>] mm`, **otherwise the parse fails loudly** (so a format change cannot pass silently) |
| Districts | Normalised: ` District` suffix removed, ` and ` → ` & `. Unknown names fail loudly |
| **Zeros** | Every bulletin yields **18 rows**. Districts not listed get 0 mm and `listed = False` |
| **No sentence** | → all 18 districts 0 mm, `section_present = False`. The period is inferred as the last HH:45 at least 15 min before the bulletin |
| Deduplication | The same bulletin archived twice → one copy (by `bulletin_time`, `district`) |

### 3d. Write, clean up, record

- Output is written with `src/storage.py`: atomically (via a `.part` file), with the
  parser version and the parse statistics stored in the Parquet metadata.
- The ZIP is deleted (`--keep-raw` keeps it).
- `data/processed/coverage.csv` gets one row per (source, date): `status` (`ok` / `no_data` /
  `failed`), `version`, `n_snapshots`, `n_rows_raw`, `n_rows`, `n_periods`, `n_detectors`,
  `has_sd`, `n_periods_redated`, `n_truncated_files` (traffic), `n_bulletins`,
  `n_with_rain_section`, `max_rain_mm` (weather), `error`.
  Columns that do not apply to a source are empty.

### Scheduling

Downloads run in the main process; parsing runs in `--jobs` worker processes (default 3,
~1.6 GB RAM each for a traffic day). Downloads stay at most `--jobs` days ahead of parsing,
so only a few ZIPs are on disk at once. A failing day is logged in `coverage.csv` and the
run continues. Progress bars show days completed and files downloaded.

### Staleness

A day is skipped only if its file exists **and** its stored parser version equals the
current one (`traffic.VERSION`, `weather.VERSION`). Otherwise it is rebuilt, with a
`[stale]` message. Files written before versioning have no version and are always rebuilt.

---

## Reading processed days (`src/data.py`)

Each day file holds what was *archived* that day. Because files lag measurement time,
the last ~10 minutes of day *d* are in the file of day *d + 1*. So
`load_traffic_lane(days)` / `load_rainfall_district(days)`:

1. read the files of each requested day **and the following day**;
2. keep rows whose `time` / `period_end` falls on a requested day;
3. concatenate (keeping categorical columns categorical) and drop duplicate keys;
4. sort by the key.

If the next day was not processed, those last minutes are missing (validation warns).

---

## Step 4 — Detector × 15 min: `python -m src.aggregate` (`src/aggregate.py`, version 1)

Input: `load_traffic_lane([day])`. Rows are grouped by `detector_id` and
`t_bin` = `time` floored to 15 min.

| Column | Definition |
|--------|------------|
| `n_readings` | lane readings in the bin |
| `n_periods` | distinct 30-s periods (≤ 30; ~18 typical because of archive gaps) |
| `n_invalid` | readings with `valid = N` |
| `n_zero_volume` | readings with `volume = 0` (their speed is a placeholder) |
| `n_speed_over_130` | readings with `speed > 130` |
| `speed_naive` | mean of `speed` over **all** readings (no cleaning) |
| `speed_clean` | Σ(speed × volume) / Σ volume over readings with `valid = Y` and `volume > 0`; **NA** if there are none (~1 % of bins) |
| `volume_sum` | Σ volume over `valid = Y` readings |
| `occupancy_mean` | mean occupancy over `valid = Y` readings; NA if all readings are invalid |

`speed_clean` removes only placeholders and flagged readings. It does **not** filter out-of-range
speeds (max 186 observed). Output metadata stores the aggregate version and the versions
of the two `traffic_lane` files used. The day is rebuilt if either changes, including when
the next day's file appears later.

---

## Validation (`src/validate.py`)

`python -m src.validate --manifest|--days|--range` (also run automatically after `src.pipeline`).

| Level | Meaning | Examples |
|-------|---------|----------|
| FAIL | the data is wrong | file missing or made by an outdated version; NA in a required column; duplicate keys; misdated midnight rows; rows outside the day; unknown `valid` / lane / district values; not exactly 18 districts per hour; `rain_min_mm > rain_max_mm`; unlisted district with rain; `n_periods > 30` |
| WARN | suspicious | < 50 % of 30-s periods present; truncated source files; detectors missing from S2; next day not processed; < 24 rainfall hours; `occupancy > 100`; `speed < 0` |
| INFO | facts before cleaning | share of `volume = 0`, with its top speeds; `speed = 0` with `volume > 0`; `speed > 130`; `occupancy < 0` and `= 100`; share of `valid = N`; share of NA `speed_clean`; non-numeric values in S8 |

Reference tables are checked too: duplicate detector IDs, district spellings, trailing
spaces and shared names in S2; `end <= start` and overlaps in warnings; duplicate holiday
dates; `Trace` / `***` in S8.

Outputs:
- `data/processed/validation_report.md`, with these sections: summary, problems, checks per
  day, reference tables, and a **profile of every table** (per column: dtype, NA count and
  share, number of unique values, min/max, most frequent values).
- `data/processed/validation_checks.csv`: every check as a row.
- The exit code is 1 if anything FAILs.

---

## Versioning rules

Bump `VERSION` in the module whenever a change alters its **output**, and describe the
change in the comment above it:

| Module | Constant | Current | History |
|--------|----------|---------|---------|
| `src/parse/traffic.py` | `VERSION` | 3 | 1 initial · 2 midnight fix · 3 truncated files counted |
| `src/parse/weather.py` | `VERSION` | 1 | 1 initial |
| `src/aggregate.py` | `VERSION` | 1 | 1 initial |

The next `src.pipeline` / `src.aggregate` run rebuilds affected days, and `src.validate`
FAILs on any file still made by an older version.

---

## Not done yet

These are the next stages and the project's experiments, not part of the pipeline:

- **Cleaning:** placeholder speeds, `valid = N`, out-of-range values, stuck sensors, gaps (P1–P6).
- **Integration:** detector ↔ district rainfall (TD and HKO district names normalised),
  time alignment of hourly rain to 15-min bins, warning state per bin, holiday/day type,
  typhoon exclusion (P7–P11).
- **S8** (daily rainfall) is stored raw and not parsed. Anyone using it must map
  `Trace` → ~0 and `***` → NA.
