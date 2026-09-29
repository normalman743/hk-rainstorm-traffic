# 数据处理过程

> 本文是 [`processing.md`](processing.md) 的中文版，两者内容一致。命令、字段名和文件名保留英文原文。

本文说明原始数据（[`raw_data.zh.md`](raw_data.zh.md)）怎样变成表格。

> **数据处理流程正在重写。** 之前的流程（`src/pipeline.py`、`src/parse/`、`src/aggregate.py`、
> `src/validate.py`、`src/data.py`、`src/storage.py`）自己下载选定的日子，解析成
> `traffic_lane` / `rainfall_district` / `traffic_15min`，然后删除 ZIP。它和它在 `data/processed/`
> 里的输出已于 2026-09-29 删除；该日期之前的 git 历史里还能找到。新流程将直接读取 `data/raw/`
> 里已有的月度打包文件，写好后在这里说明。

现在剩下的是 `src.download` 的下载命令。除了保存原始文件，其中两个命令还会生成小表，说明如下。

---

## 参考数据（`python -m src.download ...`）

```bash
python -m src.download warnings         # S4、S5 -> data/raw/hko/、data/interim/rainstorm_episodes.csv
python -m src.download static           # S8、S2 实时副本 -> data/raw/hko/、data/raw/td/
python -m src.download static-history   # S2、N1 的存档版本 -> data/raw/td/<名称>/<YYYYMMDD>.csv
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

S2、N1 和 S8 **原样保存**。如果天文台服务器断开连接（在某些云主机上会发生），
就改从历史存档下载最新的一份。

### `static-history`（`src/download/static.py`）

S2 和 N1 的每个存档版本：每个月度打包文件里的 CSV 原样保存为 `data/raw/td/<名称>/<打包文件 YYYYMMDD>.csv`；
硬盘上已有的版本会跳过。

### `holidays`（`src/download/holidays.py`）

解析 S6 自 2019 年以来的所有存档版本，加上当前的实时文件。日期取自 `dtstart[0]`，名称取自 `summary`。
同一日期出现在多个版本时，以较新的版本为准。
输出：`data/raw/calendar/public_holidays.csv`（`date`、`name`），覆盖 2018–2027 年。各个版本本身不保存。

---

## 选日期：`python -m src.download select-days`（`src/download/select_days.py`）

保留给之后的分析用；新流程不依赖它。

- **事件日：** 所有与最高级别 ≥ `--min-level` 的暴雨事件有交集的日子，事件前后各延长
  `--pad-hours`（默认 3 小时）。只统计开始时间在 `--years`（默认 2022–2025）和
  `--months`（默认 4–10 月）内的事件。
- **对照日：** 每个事件日之前 1 至 `--controls`（默认 2）周的同一个星期几，而且这一天必须
  **没有任何级别的暴雨警告、也没有热带气旋信号**，本身也不是事件日。
- 2021 年 6 月 1 日（交通数据存档开始）之前的日子一律去掉。

输出：`data/interim/day_manifest.csv`，包含 `date`、`role`（`event` 事件日 / `control` 对照日）、
`episode_ids`（空格分隔；对照日为空）、`max_level`（对照日为 0）、`max_level_name`。
现有文件有 362 天（155 个事件日、207 个对照日），2021-06 至 2025-09。
