# hk-rainstorm-traffic

Which Hong Kong roads are most sensitive to rainstorms? Integrating HKO rainfall and warning data with Transport Department traffic detectors to study how preprocessing and feature engineering affect congestion prediction.

> Course project. The focus is **data preprocessing and integration**: every
> major cleaning / aggregation / matching decision is treated as an experimental
> variable, and we measure how it changes the downstream results.
>
> **Report draft (IEEE, PDF): [`report/main.pdf`](report/main.pdf).**
> **Research data** (the whole `data/` folder, ~13 GB, as of 2026-10-01): [Google Drive](https://drive.google.com/drive/folders/1PbwMZtaP58idOqs0kwuPo_p8RRdwfTlG?usp=sharing);
> what each folder holds and where to put it: [`docs/findings_and_next.md`](docs/findings_and_next.md) §5.
> Research plan: [`docs/PROPOSAL.md`](docs/PROPOSAL.md). Findings so far and next steps
> (Chinese): [`docs/findings_and_next.md`](docs/findings_and_next.md). Cleaning rules:
> [`docs/cleaning.md`](docs/cleaning.md). Also
> [`docs/raw_data.md`](docs/raw_data.md) (every raw source and field),
> [`docs/processing.md`](docs/processing.md) (what each pipeline step does) and
> [`docs/database_description.md`](docs/database_description.md) (processed tables).
> Chinese versions: [`README.zh.md`](README.zh.md), [`docs/raw_data.zh.md`](docs/raw_data.zh.md),
> [`docs/processing.zh.md`](docs/processing.zh.md), [`docs/database_description.zh.md`](docs/database_description.zh.md).

## Status (2026-10-01)

- **Data: complete.** Every source the analysis needs, plus optional extensions, is downloaded
  for 2024-01 .. 2025-12 (~53 GB of raw monthly bundles), each with its official data dictionary.
  Inventory: [`docs/raw_data.md`](docs/raw_data.md#inventory-on-disk-2026-09-29).
- **Pipeline: end to end for three months** (2024-05, 2025-07, 2025-08; main sources S1–S6, S8):
  L1 → L2 (cleaned per source) → L3 (detector × 15 min analysis table) → EDA, RQ1, RQ2, RQ3.
  The report draft ([`report/main.pdf`](report/main.pdf), 6 pages) is built from the results.
- **Next:** review the decisions marked "pending review" in [`docs/cleaning.md`](docs/cleaning.md),
  and verify the hypotheses (traffic news S13, per-episode Black Rainstorm analysis); see
  [`docs/findings_and_next.md`](docs/findings_and_next.md).

## Research questions

1. **Sensitivity:** Which road segments show the largest speed drop / occupancy rise during rainstorms, after controlling for time of day and day of week?
2. **Prediction:** Can road attributes plus rainfall features predict congestion during rainstorm periods better than a time-only baseline?
3. **Preprocessing impact:** How much do choices such as outlier handling, aggregation window, rainfall-to-road matching and warning encoding change the answers to Q1 and Q2?

## Data sources

All data is free Hong Kong government open data. Nothing large is committed: `data/` is
git-ignored and re-created by the download commands below, or taken from the
[research data on Google Drive](https://drive.google.com/drive/folders/1PbwMZtaP58idOqs0kwuPo_p8RRdwfTlG?usp=sharing) (raw files of the three months, L1, L2, L3). Full inventory, file locations,
fields and quirks: [`docs/raw_data.md`](docs/raw_data.md).

| ID | Data | Provider | Resolution | On disk | Tier |
|----|------|----------|------------|---------|------|
| S1 | [Traffic detector readings](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads) (speed, volume, occupancy) | TD | 30 s × lane × detector (~790) | 2024-01 .. 2025-12 | main |
| S2 | Traffic detector locations | TD | per detector, 8 versions | 2021-08 .. 2026-04 | main |
| S3 | [Current Weather Report](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report): past-hour rainfall per district | HKO | hourly × 18 districts | 2024-01 .. 2025-12 | main |
| S4, S5 | [Rainstorm](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) / [tropical cyclone](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml) warning signals | HKO | per signal | since 1998 / 1946 | main |
| S6 | [Public holidays](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) | 1823 | per day | 2018 .. 2027 | main |
| S8 | [Daily total rainfall](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) at HKO HQ | HKO | daily | since 1884 | main |
| S9, S10 | [Smart-lamppost detectors](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts): readings, locations | TD | 30 s × lane × detector (17) | 2024-01 .. 2025-12 | optional |
| S11, S14 | Segment speeds (TD processed), segment → route | TD | ~1 min × segment (~4,400) | 2024-01 .. 2025-12 | optional |
| S12 | [Road network (2nd gen.)](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2) geometry | TD | per version (34) | 2024-01 .. 2025-12 | optional |
| S13 | [Special traffic news](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2) (incidents, closures) | TD | per message update | 2024-01 .. 2025-12 | optional |
| S7 | [Gridded rainfall nowcast](https://data.gov.hk/en-data/dataset/hk-hko-rss-gridded-rainfall-nowcast-in-hong-kong) (radar **forecast**) | HKO | 15 min × ~2 km grid | 2024-01 .. 2025-12 | optional |

Station-level hourly rainfall (`hourlyRainfall.php`) is **not** in the historical
archive, so rainfall is matched to roads by district.

### Downloading the data

```bash
pip install -r requirements.txt

# Optional: install the independent archive tool when downloading again.
python -m pip install "git+https://github.com/normalman743/hkgovdata.git"

# DATA.GOV.HK Historical Archive, driven by plans (skips files already there; shows sizes and asks first)
python -m hkgovdata.download run plans/2024_2025_main.json --out data/raw          # 25.2 GB
python -m hkgovdata.download run plans/2024_2025_optional.json --out data/raw      # 28.1 GB
python -m hkgovdata.download run plans/road_network_2024_2025.json --out data/raw  #  0.6 GB

# Sources not in the archive, or versions the plans leave out (seconds)
python -m src.download warnings         # S4, S5
python -m src.download static           # S8, S2 live copy
python -m src.download static-history   # S2, S14 older versions
python -m src.download holidays         # S6
```

[`hkgovdata`](https://github.com/normalman743/hkgovdata) is an independent DATA.GOV.HK
tool: `python -m hkgovdata.discover` finds datasets and checks archive coverage;
`python -m hkgovdata.download` downloads a plan. This course repository keeps its own
plans in `plans/`. Cleaning and analysis read `data/raw/` directly and do not require
the tool to be installed. A local `hkgovdata/` checkout is ignored by this repository;
install it with `python -m pip install -e ./hkgovdata` when developing the tool locally.

### How the archive is accessed

Historical versions of DATA.GOV.HK resources come from the
[Historical Archive API](https://data.gov.hk/en/help/api-spec):

```bash
# List versions of a file for a date range: returns "timestamps" and "data-files" (monthly ZIP bundles)
curl -G "https://app.data.gov.hk/v1/historical-archive/list-file-versions" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "start=20250805&end=20250805"

# One snapshot (time = YYYYMMDD-HHMM) or a whole bundle (time = the bundle's YYYYMMDD timestamp)
curl -L -G "https://app.data.gov.hk/v1/historical-archive/get-file" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "time=20250805-0801" -o rawSpeedVol-20250805-0801.xml
```

A monthly traffic bundle is ~1 GB, and one day's XML unzipped is ~670 MB. The
plans keep whole monthly bundles under `data/raw/<url host>/<url path>/bundle/`, next to each
resource's data dictionaries (`data-dictionary/`). `hkgovdata.download` can also take single
days out of a bundle with HTTP range requests.

## Processing

Layers: **L1** is the raw files as written, in Parquet. Every value is kept as a string, an
absent element is null and an empty one is `""`. **L2** (cleaning; decisions and open
questions in [`docs/cleaning.md`](docs/cleaning.md)) types and cleans each main source; every
rule is logged with its counts. **L3** is the analysis table, one row per detector and 15-min
slot, with district rain, warning level and the dry-weather baseline; each preprocessing step
(P1–P11 in [`docs/PROPOSAL.md`](docs/PROPOSAL.md)) has a default and alternatives for RQ3. The
earlier day-by-day pipeline was removed on 2026-09-29; it is in the git history before that date.

L1 from the monthly bundles in `data/raw/` (any months; the parsers read the months listed in
the manifest):

```bash
export PYTHONPATH=.
# All of steps 1 and 2 in one command (stops at the first step that fails):
python -m src.clean.l1 202405 202507 202508

# 1. Manifest: every file in the bundles of these months; byte-identical copies are parsed once.
#    List ALL months you want, old and new: the manifest and checks/*.csv are rewritten.
python -m src.clean.manifest 202405 202507 202508

# 2. Parsers -> data/interim/l1/<source>/<YYYYMM or version>.parquet
python -m src.clean.s1_periods --source s1 && python -m src.clean.s1_parse --source s1  # S1 detector readings
python -m src.clean.s1_periods --source s9 && python -m src.clean.s1_parse --source s9  # S9 lamppost readings
python -m src.clean.s3_parse          # S3 weather bulletins
python -m src.clean.s13_parse         # S13 traffic news
python -m src.clean.s11_parse         # S11 segment speeds
python -m src.clean.s7_parse          # S7 gridded rainfall nowcast
python -m src.clean.s12_parse         # S12 road network, every layer (geometry with Z / M)
python -m src.clean.versions_parse    # S2 / S10 / S14, every version
python -m src.clean.s6_parse          # S6 public holidays, every version
python -m src.clean.signals_parse     # S4 rainstorm / S5 tropical cyclone signals
python -m src.clean.s8_parse          # S8 daily rainfall

# 3. Checks (optional, not needed for L1) -> data/interim/checks/
python -m src.clean.s1_rows --source s1 && python -m src.clean.s1_rows --source s9
python -m src.clean.s3_checks && python -m src.clean.s13_checks && python -m src.clean.s11_checks
python -m src.clean.s7_checks && python -m src.clean.versions_checks
python -m src.clean.structure         # S4 S5 S6 S8 S12: presumed forms against the data, with every exception
```

L2, L3, analysis and report (after L1; packages in `requirements.txt`, LaTeX with `latexmk` for
the report):

```bash
# 4. L2 -> data/interim/l2/, counts in data/interim/checks/
python -m src.clean.l2_s1 202405 202507 202508   # S1 readings, one Parquet per month
python -m src.clean.l2_s3                          # S3 rain per hour and district
python -m src.clean.l2_ref                         # S2 detectors, S4 / S5 signals, S6 holidays, S8 daily rain

# 5. L3 -> data/interim/l3/<name>.parquet
python -m src.l3                                   # the default table
python -m src.l3 speed_agg=mean                    # a variant: any option=value (RQ3)

# 6. Analysis -> report/figures/*.pdf, report/results/*.json|csv
python -m src.analysis.eda
python -m src.analysis.rq1
python -m src.analysis.rq2
python -m src.analysis.rq3                         # builds the L3 variants it lacks; ~40 min

# 7. Report -> report/main.pdf
cd report && latexmk -pdf main.tex
```

A parser raises on anything it does not know (a new element, header or file form) instead of
skipping it; look at the case, then decide. What each parser keeps and skips is in its
docstring; the findings are in
[`docs/raw_data.md`](docs/raw_data.md).

What `src.download` itself derives (warning signals, rainstorm episodes, holidays, and the
optional day selection `select-days`) is described in [`docs/processing.md`](docs/processing.md).

## Data quirks found so far

These are material for the preprocessing experiments. The full list is in
[`docs/database_description.md`](docs/database_description.md#5-known-data-issues).

- **Detector network grew:** 42 detectors (Jul 2021), 554 (Dec 2021), ~680 (2023), 770 (2025).
  807 are listed in the location table.
- **`s.d.` only from ~18 Nov 2021.**
- **Snapshot time ≠ measurement time:** a file archived at 08:01 holds 07:53:00–07:54:00;
  the measurement time is `<period_from>`.
- **Midnight date quirk:** the 00:00 period carries the previous day's `<date>`; the file's
  archive time tells the real day.
- **Gaps:** snapshots per day vary by month (≈ 530–1,430). On 5 Aug 2025 only 1,730 of
  2,880 30-second periods are present.
- **Truncated files:** a few archived XML files are cut off (1 of 919 on 29 Jul 2025).
- **Overlap:** adjacent snapshots repeat readings (~9 % of rows), and bundles sometimes store
  a file twice.
- **Placeholder speeds:** when `volume = 0` (~28 % of readings), `speed` is the posted limit
  (70/80/100/50/110, s.d. = 0), not a measurement.
- **Out-of-range values:** speeds up to 300 km/h, occupancy = −1, speed 0 with volume > 0;
  `valid = N` on ~0.5 % of readings.
- **Names:** the detector table has both `Central & Western` and `Central and Western`, and
  most road names have trailing spaces. HKO writes `Southern District` where TD writes `Southern`.
- **Rainfall is a min–max range per district.** A district missing from a bulletin had no rain.
  A bulletin without the rainfall sentence means no rain anywhere. The rainfall hour is the one
  stated in the sentence (e.g. 06:45–07:45), not the bulletin's "At 8 a.m." time.
- **Warning DB:** `24:00` end times; rows after `UUUU` are provisional.
- **All times are HKT (UTC+8)** and are stored without a time zone.

### Key periods

2025 had four Black Rainstorm episodes, the first time this has happened in one
year under the current system ([arXiv:2508.07600](https://arxiv.org/pdf/2508.07600)).
Other notable events: the [7–8 Sep 2023 record rainstorm](https://en.wikipedia.org/wiki/2023_Hong_Kong_rainstorm_and_floods)
and the Black Rainstorm of 4–5 Aug 2025.

## Repository layout

```
.
├── README.md, README.zh.md      # this file (English / Chinese)
├── requirements.txt             # Python packages (download, L1, L2, L3, analysis, tests)
├── docs/
│   ├── PROPOSAL.md              # research plan, rewritten from the first results (2026-10-01)
│   ├── findings_and_next.md     # findings so far, what must / could be done next (Chinese)
│   ├── cleaning.md              # every L2 rule (D1–D22) with evidence, decider and counts; open questions; L3 options
│   ├── raw_data(.zh).md         # every raw source as published: access, fields, values, problems found
│   ├── processing(.zh).md       # how raw sources become tables: L1, L2, L3, analysis, src.download
│   ├── database_description(.zh).md  # sources, tables and how they link; known data issues
│   ├── data_sources_notes.md    # sources in use vs. reference only
│   └── course_project.md        # the course's project requirements (copied from Canvas)
├── plans/                       # archive download plans for hkgovdata (main, optional, road network)
├── src/
│   ├── config.py                # paths and source URLs
│   ├── download/                # sources not in the plans
│   │   ├── __main__.py          # CLI: warnings, static, static-history, holidays, select-days
│   │   ├── archive.py           # DATA.GOV.HK Historical Archive client
│   │   ├── warnings.py          # HKO rainstorm / tropical cyclone databases -> CSV (S4, S5)
│   │   ├── static.py            # detector locations, daily rainfall (S2, S8)
│   │   ├── holidays.py          # public holidays, all archived versions merged (S6)
│   │   └── select_days.py       # event + control day selection (optional)
│   ├── clean/                   # L1 (raw as written) and L2 (cleaned)
│   │   ├── l1.py                # L1 in one command: manifest, then every parser
│   │   ├── manifest.py          # every file in the monthly bundles; byte-identical copies grouped
│   │   ├── files.py             # read snapshot files out of a bundle
│   │   ├── s1_periods.py        # which 30-s periods each S1 / S9 file holds; missing and repeated periods
│   │   ├── s1_parse.py          # S1 / S9 L1: every lane reading
│   │   ├── s1_rows.py           # S1 / S9 row checks (repeated keys, nulls, formats)
│   │   ├── s3_parse.py, s3_checks.py        # S3 weather bulletins and district rainfall: L1, checks
│   │   ├── signals_parse.py     # S4 / S5 warning signals L1
│   │   ├── s6_parse.py          # S6 holidays L1, every version
│   │   ├── s8_parse.py          # S8 daily rainfall L1
│   │   ├── versions_parse.py, versions_checks.py  # S2 / S10 / S14, every version: L1, checks
│   │   ├── s7_parse.py, s7_checks.py        # S7 rainfall nowcast (optional): L1, checks
│   │   ├── s11_parse.py, s11_checks.py      # S11 segment speeds (optional): L1, checks
│   │   ├── s12_parse.py         # S12 road network (optional) L1, every layer
│   │   ├── s13_parse.py, s13_checks.py      # S13 traffic news (optional): L1, checks
│   │   ├── structure.py         # L1 values against the presumed forms (S4 S5 S6 S8 S12)
│   │   ├── l2_s1.py             # S1 L2: types, D3–D6, D12–D14, D16, D21; one Parquet per month
│   │   ├── l2_s3.py             # S3 L2: rain per hour and district, no gaps (D8–D10)
│   │   └── l2_ref.py            # S2 / S4 / S5 / S6 / S8 L2 (D2, D3, D11, D17–D20, D22)
│   ├── l3.py                    # L3 analysis table (detector × slot) and its P1–P11 options
│   └── analysis/
│       ├── common.py            # output folders, L3 connection, labels, plot style
│       ├── eda.py               # coverage, events, speed / flow vs rain and warning, 2025-08-05
│       ├── rq1.py               # RQ1 sensitivity per detector and district, exposure, stability, map
│       ├── rq2.py               # RQ2 event-held-out prediction (baseline, linear, LightGBM)
│       └── rq3.py               # RQ3 ablation: one preprocessing alternative at a time
├── tests/
│   ├── test_download.py         # src.download
│   └── test_clean.py            # L1 / L2 / L3 rules
├── report/
│   ├── main.tex, refs.bib       # report source (IEEEtran)
│   ├── main.pdf                 # the built report
│   ├── figures/                 # figures written by src.analysis (eda_*, rq1_*, rq2_*, rq3_*)
│   └── results/                 # numbers written by src.analysis (eda / rq1 / rq2 / rq3 .json, .csv)
├── data/                        # git-ignored: raw/ (downloads), interim/ (l1, l2, l3, manifest, checks)
└── hkgovdata/                   # optional independent local checkout; git-ignored
```

## Licence & attribution

Code: MIT (TBD). Data: © Transport Department and Hong Kong Observatory,
HKSAR Government, used under the [DATA.GOV.HK Terms and Conditions](https://data.gov.hk/en/terms-and-conditions).
HKO notes that AWS rainfall is provisional and differs from the official
climatological record. We report which source each figure uses.
