# 数据处理过程

> 本文是 [`processing.md`](processing.md) 的中文版，两者内容一致。命令、字段名和文件名保留英文原文。

本文说明原始数据（[`raw_data.zh.md`](raw_data.zh.md)）怎样变成表格。命令见 README 的“数据处理”一节；
每条清洗规则及其证据和处理数量见 [`cleaning.md`](cleaning.md)；每张表的列见
[`database_description.zh.md`](database_description.zh.md) 第 3 节。研究月份：2024-05、2025-07、2025-08。

```
data/raw/                     下载的原始文件（src.download、hkgovdata 的 plan）
  └─ L1  src.clean.*_parse    data/interim/l1/<来源>/          每个文件原样保存，全部是字符串
      └─ L2  src.clean.l2_*   data/interim/l2/<来源>/          定类型并清洗，只做主要来源
          └─ L3  src.l3       data/interim/l3/<名称>.parquet   探测器 × 15 分钟的分析表
              └─ src.analysis.*   report/figures/*.pdf、report/results/*.json|csv
```

每一步遇到没有规则覆盖的情况都会报错并列出相关的行，不会跳过。每一步的处理数量写到
`data/interim/checks/`。

---

## L1：原样保存（`src.clean`）

- `src.clean.manifest` 列出指定月份打包文件中的每个文件，并把字节完全相同的副本归为一组
  （存档经常把同一个文件存好几次）；解析程序每组只读一个文件。
- 每个来源一个解析程序（`s1_parse`、`s3_parse`、`signals_parse`、`s6_parse`、`s8_parse`，
  S2 / S10 / S14 用 `versions_parse`；可选来源用 `s7_parse`、`s11_parse`、`s12_parse`、
  `s13_parse`）。所有值都保存为字符串，元素不存在记为 null，元素为空记为 `""`；每行都记录它来自哪个文件
  （`bundle`、`index`）。
- 检查程序（`s1_periods`、`s1_rows`、`*_checks`、`structure`）只描述数据，不改数据；发现的问题见
  [`raw_data.zh.md`](raw_data.zh.md)。

## L2：按来源清洗（`src.clean.l2_s1`、`l2_s3`、`l2_ref`）

| 程序 | 输出 | 规则 |
|------|------|------|
| `l2_s1` | `s1/<YYYYMM>.parquet`：每条车道每个 30 秒时段一行（1.231 亿 / 9,990 万 / 1.099 亿行） | D3 去空格，D4 给重复的 `Middle Lane` 编号，D5 对唯一一个重复的数据块取平均，D6 给 00:00 时段改日期，D12 删除 TDS90026 在 2025 年的三车道数据块，D13 估算 TDS90036 缺失的 Slow Lane，D14 删除个别缺车道的数据块，D16 补上缺失的 `direction`，D21 `occupancy = -1` → 0 |
| `l2_s3` | `s3/rain.parquet`：每小时（HH:45 → HH:45）每区一行，40,176 行 | D9 公告里没列出的区记为 0 mm，D10 每小时每区一行，D8 单独缺失的一小时取前后两小时的平均 |
| `l2_ref` | `s2/detectors.parquet`（790）、`s4/rainstorm.parquet`（974）、`s5/tc.parquet`（1,262）、`s6/holidays.parquet`（170）、`s8/daily.parquet`（49,491） | D2 用 S2 的 2025-10 版本，D3，D11 S2 区名 → S3 区名；D20 `24:00`；S5 用 D17、D18、D22；假期每个日期取最新版本；S8 用 D19 |

被规则修改或生成的行，在 `l2_rule` 里记下规则编号。缺失的 30 秒时段在 L2 不补：它们就是不存在的行。
可选来源（S7、S9–S14）还没有 L2。

## L3：分析表（`src.l3`）

每个探测器每个时段一行（默认 15 分钟）。每一步都有默认做法和备选做法
（[`PROPOSAL.md`](PROPOSAL.md) 中的 P1–P11；`python -m src.l3 选项=值` 生成变体）。
各步骤及默认表的处理数量：

1. **读数**（L2 S1，3.329 亿条）：P1 去掉 `valid = N`（980 万）；P2 去掉车流 > 0 但车速为 0 或
   > 130 km/h 的读数（240 万）；两者合计 1,220 万。
2. **车道时段**（1,780 万）：P3 去掉卡死的车道时段：时段内读数全部相同、占用率或车流大于 0，
   而且连续两个时段以上（1,122 个）。
3. **探测器时段**（656 万）：P4 车速 = 各车道读数按车流加权的平均（空车道的车速是道路限速，不是测量值）；
   车流 = 所有车道每小时的车辆数；占用率 = 平均值。没有任何车道有车的时段没有车速，去掉（34,691 个）。
   `periods` / `coverage` 记录这个时段有多少个 30 秒时段。
4. **缺口**：P6 两个有数据的时段之间连续缺 1–2 个时段时，用线性插值补上并标记（25,787 个）。
5. **背景信息**：去掉三个月以外的时段（1,469 个）；接上 S2（区、位置、道路）；本区这一小时的雨量
   （P7 取范围中点；P8 取时段所在的那一小时）、前一小时的雨量和全港最大雨量；没有雨量小时的时段去掉
   （7,273 个：每月最后一天 22:45 之后，那份公告在下个月的文件里）；警告等级和警告事件开始后的分钟数
   （首尾相接的信号算一次事件）；热带气旋信号；日子类型（工作日 / 星期六 / 星期日或假期）。
   本区这一小时和前一小时都没有雨、没有暴雨警告、热带气旋信号低于 8 号的时段，记为**干燥**时段。
6. **基线**（P10）：每个探测器按季节（2024-05；2025-07 + 08）、日子类型和一天中的时段，
   取干燥时段车速、车流和占用率的中位数；基线背后不足 3 个干燥时段的去掉（109,646 个）。
   `ratio` = 车速 / 基线车速，`flow_ratio` = 车流 / 基线车流。

结果：6,430,886 行（`data/interim/l3/default.parquet`）。P9（警告编码）和 P11（去掉 8 号及以上
热带气旋信号）在分析时处理，不在这里。

## 分析（`src.analysis`）

| 程序 | 内容 | 输出 |
|------|------|------|
| `eda` | 覆盖率、降雨事件、车速 / 车流与雨量和警告等级的关系、警告开始、2025-08-05 | `report/figures/eda_*.pdf`、`report/results/eda.json` |
| `rq1` | 每个探测器的敏感度（`s_warn`、`s_rain`、按暴露量调整、混合模型斜率）、稳定性、各区、地图 | `rq1_*.pdf`、`rq1.json`、`rq1_detectors.csv` |
| `rq2` | 按事件留出，预测速度比和拥堵（基线、Ridge / Logistic、LightGBM、四组特征） | `rq2_models.pdf`、`rq2.json` |
| `rq3` | 每次只换一个预处理备选：排名、主要比值、预测 skill | `rq3_ablation.pdf`、`rq3.json`、`rq3.csv` |

---

## 参考数据（`python -m src.download ...`）

除了保存原始文件，`warnings` 和 `holidays` 还会生成几张小表（`rainstorm_warnings.csv`、
`rainstorm_episodes.csv`、`tc_signals.csv`、`public_holidays.csv`）。L2 和 L3 不读这些表：
它们按自己的规则，从原始文件（`rstorm.dat`、`tc.dat`、S6 的各个版本）的 L1 开始处理。这些表留作参考。

```bash
python -m src.download warnings         # S4、S5 -> data/raw/hko/、data/interim/rainstorm_episodes.csv
python -m src.download static           # S8、S2 实时副本 -> data/raw/hko/、data/raw/td/
python -m src.download static-history   # S2、S14 的存档版本 -> data/raw/td/<名称>/<YYYYMMDD>.csv
python -m src.download holidays         # S6 -> data/raw/calendar/public_holidays.csv
```

### `warnings`（`src/download/warnings.py`）

**输入：** S4 `rstorm.dat` 和 S5 `tc.dat`。这两个原始文件也会原样保存到 `data/raw/hko/`。

暴雨警告信号 → `data/raw/hko/rainstorm_warnings.csv`（一行一个信号）：
- 第 2–11 列转成 `start`（开始）和 `end`（结束）。**`24:00` 会转成第二天 00:00**
  （`_dt` 是在日期上加小时和分钟，而不是直接构造时间，所以 24 点也能处理）。
- 颜色 A / R / B 转成 `level` 1 / 2 / 3，另加 `level_name`；`duration_min` = 结束 − 开始。
  不使用文件自带的持续时间列。
- `UUUU` 行之后的记录，`provisional`（临时数据）设为 True。

暴雨事件 → `data/interim/rainstorm_episodes.csv`：
- 信号按开始时间排序；只要下一个信号的开始时间**不晚于**当前事件的结束时间，就并入同一次事件
  （天文台记录警告升级时，前一个信号的结束和下一个的开始是同一分钟）。
- 每次事件保留 `start`、`end`、`max_level`（最高级别）、`n_signals`（合并了几个信号）、`duration_min`、`provisional`。

热带气旋信号 → `data/raw/hko/tc_signals.csv`：
- 强度为 `MSN` 的行删掉（它们不是热带气旋信号）。
- `HHMM` 时间在前面补 0（`10` → 00:10），`2400` 同样转成第二天 00:00。
- 名字为 `NIL` 的改成空值（用 pandas 读取时显示为 NA）。

### `static`（`src/download/static.py`）

S2、S14 和 S8 **原样保存**。如果天文台服务器断开连接（在某些云主机上会发生），
就改从历史存档下载最新的一份。

### `static-history`（`src/download/static.py`）

S2 和 S14 的每个存档版本：每个月度打包文件里的 CSV 原样保存为 `data/raw/td/<名称>/<打包文件 YYYYMMDD>.csv`；
硬盘上已有的版本会跳过。

### `holidays`（`src/download/holidays.py`）

解析 S6 自 2019 年以来的所有存档版本，加上当前的实时文件。日期取自 `dtstart[0]`，名称取自 `summary`。
同一日期出现在多个版本时，以较新的版本为准。
输出：`data/raw/calendar/public_holidays.csv`（`date`、`name`），覆盖 2018–2027 年。各个版本本身不保存。

---

## 选日期：`python -m src.download select-days`（`src/download/select_days.py`）

保留给之后的分析用；现在的流程不依赖它。

- **事件日：** 所有与最高级别 ≥ `--min-level` 的暴雨事件有交集的日子，事件前后各延长
  `--pad-hours`（默认 3 小时）。只统计开始时间在 `--years`（默认 2022–2025）和
  `--months`（默认 4–10 月）内的事件。
- **对照日：** 每个事件日之前 1 至 `--controls`（默认 2）周的同一个星期几，而且这一天必须
  **没有任何级别的暴雨警告、也没有热带气旋信号**，本身也不是事件日。
- 2021 年 6 月 1 日（交通数据存档开始）之前的日子一律去掉。

输出：`data/interim/day_manifest.csv`，包含 `date`、`role`（`event` 事件日 / `control` 对照日）、
`episode_ids`（空格分隔；对照日为空）、`max_level`（对照日为 0）、`max_level_name`。
现有文件有 362 天（155 个事件日、207 个对照日），2021-06 至 2025-09。
