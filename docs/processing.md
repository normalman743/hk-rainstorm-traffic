# Data Processing

> 中文版：[`processing.zh.md`](processing.zh.md)

How raw sources ([`raw_data.md`](raw_data.md)) become tables.

> **The processing pipeline is being rewritten.** The earlier one (`src/pipeline.py`,
> `src/parse/`, `src/aggregate.py`, `src/validate.py`, `src/data.py`, `src/storage.py`) downloaded
> selected days itself, parsed them into `traffic_lane` / `rainfall_district` / `traffic_15min`
> and deleted the ZIPs. It was removed on 2026-09-29, together with its output in
> `data/processed/`; it is in the git history before that date. The new pipeline will read the
> monthly bundles already in `data/raw/` and will be documented here.

What remains are the download commands of `src.download`. Besides saving the raw files, two of
them derive small tables, described below.

---

## Reference data (`python -m src.download ...`)

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

Kept for later analysis; the new pipeline does not depend on it.

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
