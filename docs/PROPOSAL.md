# Project Proposal: Rainstorm-Sensitive Roads in Hong Kong

**Title:** Which Hong Kong roads are most sensitive to rainstorms? A preprocessing and
integration study of Transport Department detector data, HKO rainfall and warning signals.

Rewritten on 2026-10-01 from the first full run of the pipeline (three months, all main
sources). The previous version is in git history; numbers below come from
`report/results/*.json` and `docs/cleaning.md`.

## 1. Problem and why it matters

Heavy rain is a recurring disruption in Hong Kong; 2025 had four Black Rainstorm episodes, the
first time under the current warning system. That rain slows traffic is known. What a traffic
manager or a commuter needs is **where** the effect is worst and **whether it can be
anticipated**. Both answers depend on joining data that were never designed to be joined:
30-second lane readings from ~790 road detectors, an hourly rainfall *range* per district
published inside a weather bulletin, and warning signals issued for the whole territory. How
that join and the cleaning around it are done is the subject of the project, as the course
asks: we measure how each preprocessing choice changes the answers.

## 2. Data (three months: 2024-05, 2025-07, 2025-08)

| ID | Source | Resolution | Used for |
|----|--------|-----------|----------|
| S1 | TD raw detector readings (speed, volume, occupancy, s.d., valid) | 30 s × lane, 784 detectors, 332.9 M readings | traffic |
| S2 | TD detector locations | per detector | district, lat/lon |
| S3 | HKO Current Weather Report: past-hour rainfall range per district | hourly × 18 districts | local rain |
| S4 | HKO rainstorm warning signals | per signal | Amber / Red / Black |
| S5 | HKO tropical cyclone signals | per signal | confounder (signal ≥ 8 left out) |
| S6 | Public holidays | per date | day type |
| S8 | HKO daily rainfall | per day | checks |

The three months hold 41 Amber (76 h), 18 Red (28 h) and 5 Black (21 h) signals, including all
four 2025 Black episodes, and Typhoon Wipha (signal 10). Optional sources (radar nowcast,
segment speeds, traffic news, road network) are downloaded but set aside for now.

**What the raw data are like** (details in `docs/raw_data.md`): the archive stored a copy of
the live file each time it fetched it, so 27–47 % of the 30-s periods are absent, identical
copies are stored several times, midnight periods carry yesterday's date and three files are
truncated. With volume 0 the reported speed is the speed limit, not a measurement (20 % of
readings). `valid = N` readings (2.9 %) look normal. Speed 0 with volume > 0 is physically
impossible (0.17 %). District rainfall is a range, and a district without rain is not listed.

## 3. Research questions

- **RQ1 – Sensitivity.** Which detectors and districts lose most speed, relative to their own
  dry-weather normal, under rainstorms, and is this a stable property of the road or an effect
  of how much rain fell there?
- **RQ2 – Prediction.** Can rain, warning and road features predict the 15-min speed ratio in
  unseen storms better than a time-only baseline? Which information helps: local rain or the
  warning level?
- **RQ3 – Preprocessing impact (course focus).** How much does each preprocessing choice change
  the RQ1 ranking and the RQ2 accuracy?

## 4. Pipeline and method

Three layers, all Parquet, processed with DuckDB (`src/clean`, `src/l3.py`, `src/analysis`):

- **L1** parses every file as written (strings, nothing dropped), with structure checks.
- **L2** cleans each source by explicit rules D1–D22, each with evidence, decider and counts
  (`docs/cleaning.md`). Principles agreed with the course teacher: fail loudly on anything no
  rule covers; leave no NA — estimate a few missing values with good neighbours (interpolation,
  ratio), average a value given twice, drop rare bad data in a large source after checking
  that the drop does not cluster in rain periods; flag everything estimated.
- **L3** is one row per detector × 15-min slot (6.43 M rows): volume-weighted speed, flow,
  occupancy; the district's rain (midpoint of the range), the rain of the hour before and the
  territory maximum; warning level and minutes since the warning episode began; cyclone signal;
  day type. The target is the **speed ratio** to the detector's median speed in dry slots of
  the same season, day type and time of day. Each step (P1–P11) has a default and alternatives.

| Step | Default | Alternatives (RQ3) |
|------|---------|--------------------|
| P1 validity | drop `valid = N` readings | keep; drop the whole detector period |
| P2 outliers | drop speed 0 or > 130 with volume > 0 | none; + robust z per lane |
| P3 stuck sensors | drop identical lane slots ≥ 30 min | keep |
| P4 lane → detector | volume-weighted speed | mean of all readings; slowest lane |
| P5 time slot | 15 min | 5 min; 60 min |
| P6 gaps | interpolate 1–2 missing slots | none |
| P7 rain → road | own district, midpoint | upper bound; territory maximum |
| P8 rain alignment | the hour the slot is in | the hour before |
| P9 warning encoding | level 0–3 + minutes since issue | any / none; no warning features |
| P10 baseline | dry median per season × day type × slot | per month; all months |
| P11 confounders | leave out cyclone signal ≥ 8 | keep |

**RQ1:** per detector, median speed ratio under Red/Black − 1 (`s_warn`), under district rain
≥ 10 mm/h (`s_rain`), an exposure-adjusted `s_warn`, and a mixed-model rain slope; stability
by split-half over rain events. **RQ2:** 42 event days (22 events), five folds grouped by
event; baseline ratio = 1; ridge / logistic regression and LightGBM with four feature sets;
MAE and F1 of congestion (ratio < 0.7). **RQ3:** one alternative at a time; Spearman of the
ranking with the default, top-20 overlap, headline ratios, and LightGBM skill (1 − MAE / MAE of
the baseline, because the target changes with the variant).

## 5. Preliminary results (first full run, 2026-10-01)

- **Speed follows the local rain; the warning level mostly changes demand.** Median speed ratio
  falls from 0.976 (0–5 mm/h) to 0.888 (> 40 mm/h) without a warning. By level: Amber 0.940,
  Red 0.918, **Black 0.937**. Under Black the flow is 0.62 of normal in every rain bin, even
  where the district had no rain (speed there 1.007): a "Black paradox" of fewer, faster cars.
- **5 August 2025:** speed ratio 0.77 ten minutes after the Black signal, flow down to 0.38 by
  09:00, speed back to 1.0 by 16:00 while Black was still in force.
- **RQ1:** the ranking is stable across storms (split-half Spearman 0.84 / 0.90) but
  correlates −0.51 with the rain the district received under Red/Black. After adjusting for
  that exposure, the Kowloon urban corridors (Tseung Kwan O Road, Kwun Tong Bypass, Lung
  Cheung Road, West Kowloon Corridor, Lion Rock Tunnel Road) remain the most sensitive; North
  District moves up, the Islands move down.
- **RQ2:** LightGBM cuts the wet-slot MAE from 0.079 to 0.057 (−28 %; Red/Black −36 %). Rain
  features alone reach 0.057, warning features alone 0.067. Congestion (1–4 % of slots) stays
  hard: F1 0.14–0.17.
- **RQ3 (18 alternatives, one at a time; noise floor about 0.005 in skill):**
  - *Speed aggregation (P4) matters most for the ranking:* mean of all readings or slowest
    lane keeps only 11 of the top 20 (Spearman 0.91). The mean lets empty-lane readings (speed
    = the posted limit) dilute every ratio (Black 0.961 instead of 0.937).
  - *The time slot (P5) changes what can be predicted:* skill 0.215 at 5 min, 0.278 at 15 min,
    0.378 at 60 min (rain is hourly).
  - *Rain assignment (P7, P8) matters for prediction:* the territory maximum instead of the own
    district lowers skill 0.278 → 0.212; the hour before, → 0.233. Removing warning features:
    0.272.
  - *A robust outlier rule (P2 + z) removes real congestion:* its 1.73 M extra exclusions are
    72 % slow readings (median 20 km/h on lanes with median 72) and 1.7 times over-represented
    under Red/Black; congestion under Red/Black falls 3.9 % → 3.0 %, F1 0.168 → 0.138.
  - *Validity flag, stuck sensors, gap filling, cyclone filter hardly matter* (Spearman ≥ 0.998,
    skill within noise). Baseline choice (P10) is in between (16–18 of the top 20).

## 6. Plan to the final report (30 Nov)

| Weeks | Work |
|-------|------|
| to 21 Oct | Proposal presentation from this document; review the decisions marked "pending review" in `docs/cleaning.md` |
| 3–4 | Verify the hypotheses (H1–H10 in the report): per-episode analysis of the Black paradox; speed difference in km/h vs ratio; traffic news (S13) for congested slots and stuck sensors |
| 5 | Add the optional sources where they answer a hypothesis: radar nowcast (S7) for short bursts, road network (S12/S14) for road class |
| 6 | Extend to more months if the archive allows (more Black / Red episodes) |
| 7–8 | Final report (IEEE, ≤ 10 pages), presentation (25 Nov) |

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Four Black episodes only | Pool Red + Black; report per episode; add months |
| Rain is an hourly district range | Treat it as an RQ3 variable (P7, P8); radar nowcast as a check |
| 27–47 % of 30-s periods unfetched | Coverage is recorded per slot; missing periods are absent rows, not filled |
| Congestion from incidents, not rain | Traffic news join (H6); robust medians |
| Demand change confounds speed | Report flow ratio next to speed ratio throughout |
