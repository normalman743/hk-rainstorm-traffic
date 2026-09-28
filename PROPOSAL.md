# Project Proposal: Rainstorm-Sensitive Roads in Hong Kong

**Working title:** Which Hong Kong roads are most sensitive to rainstorms? A data preprocessing and integration study using HKO and Transport Department open data.

## 1. Motivation

Heavy rain is a recurring disruption in Hong Kong. The Observatory's Black
Rainstorm warning text itself warns that "persistent rainstorm will cause serious road
flooding and traffic congestion". In 2025 Hong Kong had four Black Rainstorm
episodes, the first time this happened in one year under the current warning system.

Commuters and traffic managers are not asking *whether* rain slows traffic.
That is well established. They want to know **where** the impact is worst and
**whether it can be anticipated**. Both questions depend on joining two
messy, independently collected data sources: minute-level road detectors and
hourly regional rainfall. How that join and the cleaning around it are done
is the core subject of this project.

## 2. Related work

- **Rain vs. travel speed (single road).** A 2021 review in *ISPRS IJGI*
  ([doi:10.3390/ijgi10080557](https://doi.org/10.3390/ijgi10080557)) reports that
  on one Hong Kong urban road, light, moderate and heavy rain reduced speed by
  roughly 4.21%, 6.28% and 7.31%.
- **Rain vs. city-level congestion.** A 2026 study in *Frontiers in Sustainable
  Cities* ([link](https://www.frontiersin.org/journals/sustainable-cities/articles/10.3389/frsc.2026.1871487/full))
  models the nonlinear relation between daily rainfall, a city-wide congestion
  index and metro ridership in Guangzhou and Shenzhen.
- **2025 Black Rainstorms.** [arXiv:2508.07600](https://arxiv.org/pdf/2508.07600)
  analyses the meteorology of the four 2025 Black Rainstorm episodes.

**Gap we address:** prior work uses either a single road or a daily,
city-aggregated index. We work at **detector level (~800 locations, whole
territory)**, at **sub-hourly resolution**, conditioned on **official warning
levels**. We also make the preprocessing pipeline itself the object of study.
Novelty in the rain-slows-traffic finding is *not* claimed.

## 3. Research questions

- **RQ1 – Sensitivity ranking.** For each detector, how much do speed and
  occupancy deviate from their own normal level (same weekday type and time of day) during
  Amber / Red / Black periods? Which roads or districts are most sensitive?
- **RQ2 – Prediction.** Given road attributes (district, road type, direction,
  lanes, baseline speed) and rainfall features (current / lagged district
  rainfall, warning level, time since warning issued), can we predict
  15-minute congestion during rainstorms better than a time-only baseline?
- **RQ3 – Preprocessing impact (primary course focus).** How sensitive are
  RQ1 rankings and RQ2 accuracy to each preprocessing choice listed in §5?

## 4. Data

| Source | Content | Resolution | Coverage used |
|--------|---------|-----------|---------------|
| TD *Traffic Data of Strategic / Major Roads*: `rawSpeedVol-all.xml` | Per-lane speed, volume, occupancy, `valid` flag, s.d. | 30 s, ~800 detectors | Rainy seasons (Apr–Sep) 2022–2025, plus dry-month controls |
| TD detector location CSV | Detector ID, road, district, lat/lon, direction | Static | All |
| HKO *Current Weather Report*: `CurrentWeather.xml` | Past-hour rainfall **range (min–max mm) per district** | Hourly | Same period |
| HKO Rainstorm Warning Signals Database | Amber / Red / Black issue and cancel times | Event | 2021–2025 |
| HKO daily rainfall (`daily_HKO_RF_ALL.csv`) | Daily rainfall totals | Daily | Sanity checks / day labelling |

All sources and download commands are listed in [`README.md`](README.md#data-sources).

**Feasibility check (done):** the DATA.GOV.HK Historical Archive API serves
both the raw detector file and the HKO current-weather RSS back to at least
June 2021. Snapshots for the 5 Aug 2025 Black Rainstorm were retrieved
successfully. We do **not** depend on live collection this season.

**Known limitations**
- District rainfall is given as a *range* over several gauges, not a point value.
- Station-level hourly AWS rainfall (`hourlyRainfall.php`) is not archived, so it is used only as an optional live supplement.
- Detectors cover strategic / major roads only. Local streets are out of scope.
- The raw archive is about 1 GB zipped per month, so we must parse data by streaming it, not by loading it all into memory.

## 5. Preprocessing pipeline and controlled experiments

Each step has a **default** and one or more **alternatives**. RQ3 varies one
step at a time while the other steps stay at their defaults, then records
the change in RQ1 (Spearman correlation of sensitivity rankings and top-20
overlap) and RQ2 (MAE / F1 of the congestion class).

| Step | Default | Alternatives compared |
|------|---------|-----------------------|
| **P1. Validity filtering** | Drop lanes with `valid = N` | Keep all; drop whole detector-period if any lane invalid |
| **P2. Outlier handling** | Physical bounds (speed 0–130 km/h, occupancy 0–100%) + per-detector robust z-score | Bounds only; IQR; none |
| **P3. Zero-volume / stuck sensors** | Flag runs of identical readings > 30 min as missing | Treat as genuine; drop detector-day |
| **P4. Lane → detector aggregation** | Volume-weighted mean speed, summed volume, mean occupancy | Simple mean speed; slowest lane |
| **P5. Temporal aggregation** | 15 min | 5 min; 60 min (to match rainfall) |
| **P6. Missing values** | Short gaps (≤ 2 intervals) linearly interpolated, longer left missing | Forward-fill; drop; detector-level seasonal mean |
| **P7. Rainfall-to-road matching** | Detector's own district, midpoint of range | Upper bound of range; nearest neighbouring district by centroid; territory-wide max |
| **P8. Rainfall temporal alignment** | Hourly value assigned to the preceding hour's 15-min slots | Forward-fill; linear interpolation; lagged features (t−1 h, t−2 h) |
| **P9. Warning encoding** | Ordinal level (0 none, 1 Amber, 2 Red, 3 Black) + minutes since issue | One-hot; binary "any warning"; ignore warnings (rain only) |
| **P10. Baseline / normalisation** | Speed ratio vs. detector's median at same weekday-type × 15-min slot on dry days | Raw speed; z-score; ratio vs. previous-week same slot |
| **P11. Confounders** | Exclude public holidays and typhoon-signal ≥ 8 periods | Keep them; add as features |

## 6. Methods

- **RQ1:** Per-detector sensitivity = median speed ratio under each warning level
  minus 1. We check robustness with a mixed-effects model
  (`speed_ratio ~ rain + warning + (1 | detector)`) and map the results by district.
- **RQ2:** Target = 15-min speed ratio (regression) and congested/not (speed
  ratio < 0.7, classification). Models: time-of-day baseline, linear/logistic
  regression, gradient boosting (LightGBM). **Split by rainstorm event** (the
  test events are unseen) to avoid temporal leakage. We report MAE, F1 and
  feature importance.
- **RQ3:** Run the one-at-a-time ablation grid from §5 and report sensitivity
  tables plus a short discussion of which steps matter most.

## 7. Timeline (8 weeks)

| Week | Deliverable |
|------|-------------|
| 1 | Archive downloader; warning-event table from HKO DB; select event windows |
| 2 | Streaming XML parser → Parquet; detector metadata join |
| 3 | Cleaning steps P1–P4, P6, with data-quality report |
| 4 | Rainfall parser (district ranges), integration P7–P9 |
| 5 | EDA; RQ1 sensitivity ranking and maps |
| 6 | RQ2 models and event-based evaluation |
| 7 | RQ3 ablation grid |
| 8 | Report, figures, presentation |

## 8. Risks and mitigation

| Risk | Mitigation |
|------|------------|
| Data volume (~1 GB/month zipped) | Download only months that contain warnings plus a few matched dry control weeks; stream-parse to 5-min Parquet |
| Few Black events (small sample) | Pool Red + Black as "severe"; report per-event results; use Amber events for training volume |
| Coarse rainfall (district range, hourly) | Treat as an explicit RQ3 variable (P7, P8); note it as a limitation |
| Detector ID or schema changes across years | Use archived data dictionaries (`data-dictionary-dates` field); keep only detectors present across the period |
| Congestion caused by incidents, not rain | Robust medians; optional filter using TD special traffic news (future work) |

## 9. Expected outputs

1. A reproducible pipeline (download → clean → integrate → features).
2. A ranked list and map of rainstorm-sensitive roads.
3. A rainstorm-period congestion model with an event-held-out evaluation.
4. An ablation report quantifying how each preprocessing decision changes the conclusions.
