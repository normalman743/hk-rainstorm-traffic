# 数据处理过程

> 本文是 [`processing.md`](processing.md) 的中文版，两者内容一致。命令、字段名和文件名保留英文原文。

本文说明原始数据（[`raw_data.zh.md`](raw_data.zh.md)）怎样变成处理后的表格
（[`database_description.md`](database_description.md)）：每一步由哪个代码文件负责、改了什么、
故意不改什么，以及结果怎样检查。

## 原则

1. **流水线不做清洗。** 第 1–4 步只整理结构：解析、类型转换、去掉完全重复的记录、修正时间戳。
   所有数值都按发布时的原样保留，包括车速填充值、`valid = N` 的读数和超出范围的读数。
   怎样清洗是本项目要做的对照实验（[`PROPOSAL.md`](../PROPOSAL.md) 中的 P1–P11），
   之后再单独做，才能衡量每种清洗方式的影响。
2. **大文件不落盘。** 原始 XML 直接从下载的 ZIP 里读取，转成 Parquet 后就删除 ZIP。
3. **每个输出文件都记录生成它的代码版本。** 过期的文件会重新生成，不会被悄悄沿用。
4. **每次运行都检查。** 每次跑完流水线后，`src.validate` 都会检查数据规则，并对每张表做体检。

## 总览

```
                    第 1 步  参考数据（几秒）
S4 rstorm.dat ─┐
S5 tc.dat ─────┴─ src.download warnings ──▶ data/raw/hko/rainstorm_warnings.csv、tc_signals.csv
                                            data/interim/rainstorm_episodes.csv
S2、S8、N1 ────── src.download static ────▶ data/raw/td/*.csv、data/raw/hko/daily_HKO_RF_ALL.csv
S6 ────────────── src.download holidays ──▶ data/raw/calendar/public_holidays.csv

                    第 2 步  选日期
暴雨事件 + 台风 ── src.download select-days ─▶ data/interim/day_manifest.csv

                    第 3 步  逐天：下载 → 解析 → Parquet → 删 ZIP（约 24 秒/天）
S1（存档）─────┐                            ┌▶ data/processed/traffic_lane/<YYYY>/<YYYYMMDD>.parquet
S3（存档）─────┴─ src.pipeline ─────────────┼▶ data/processed/rainfall_district/<YYYY>/<YYYYMMDD>.parquet
                                            ├▶ data/processed/coverage.csv
                                            └▶ src.validate ─▶ data/processed/validation_report.md

                    第 4 步  每探测器每 15 分钟（约 10 秒/天）
traffic_lane ──── src.aggregate ──────────▶ data/processed/traffic_15min/<YYYY>/<YYYYMMDD>.parquet

                    随时可运行
                  src.validate ──────────▶ validation_report.md、validation_checks.csv
```

```bash
python -m src.download warnings && python -m src.download static && python -m src.download holidays
python -m src.download select-days --min-level R
python -m src.pipeline --manifest          # 结束时会自动运行 src.validate
python -m src.aggregate --manifest
python -m src.validate --manifest          # 完整检查，包括 traffic_15min
```

每一步都会跳过已经完成、而且是当前版本生成的工作，所以中断或改了代码之后都可以直接重跑。

---

## 第 1 步：参考数据

### `python -m src.download warnings`（`src/download/warnings.py`）

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

### `python -m src.download static`（`src/download/static.py`）

S2、N1 和 S8 **原样保存**。如果天文台服务器断开连接（在某些云主机上会发生），
就改从历史存档下载最新的一份。

### `python -m src.download holidays`（`src/download/holidays.py`）

解析 S6 自 2019 年以来的所有存档版本，加上当前的实时文件。日期取自 `dtstart[0]`，名称取自 `summary`。
同一日期出现在多个版本时，以较新的版本为准。
输出：`data/raw/calendar/public_holidays.csv`（`date`、`name`），覆盖 2018–2027 年。

---

## 第 2 步：选日期 `python -m src.download select-days`（`src/download/select_days.py`）

全部下载的话，每个月约 1 GB，所以只选有用的日子：

- **事件日：** 所有与最高级别 ≥ `--min-level` 的暴雨事件有交集的日子，事件前后各延长
  `--pad-hours`（默认 3 小时）。只统计开始时间在 `--years`（默认 2022–2025）和
  `--months`（默认 4–10 月）内的事件。
- **对照日：** 每个事件日之前 1 至 `--controls`（默认 2）周的同一个星期几，而且这一天必须
  **没有任何级别的暴雨警告、也没有热带气旋信号**，本身也不是事件日。
- 2021 年 6 月 1 日（交通数据存档开始）之前的日子一律去掉。

输出：`data/interim/day_manifest.csv`，包含 `date`、`role`（`event` 事件日 / `control` 对照日）、
`episode_ids`（空格分隔；对照日为空）、`max_level`（对照日为 0）、`max_level_name`。
用 `--min-level R` 会选出 59 天（28 个事件日 + 31 个对照日）。

---

## 第 3 步：下载和解析 `python -m src.pipeline`（`src/pipeline.py`）

对每个数据源（`weather` 天气、`traffic` 交通）的每一天：

### 3a. 下载（`src/download/archive.py`）

1. 对这一天调用 `list-file-versions`，拿到当天所有快照的时间戳，以及包含它们的打包文件（月度 ZIP）。
2. 用 HTTP 分段请求读取打包文件的 ZIP 目录。当天的文件（文件名形如 `<YYYYMMDD>-*-<文件名>`）
   用 16 个线程并行下载，每个文件一次分段请求，然后解压并做 CRC 校验。
3. **重复文件：** 文件名和 CRC 都相同的只下载一次。如果文件名相同但 CRC 不同，会以带后缀的新名字保留。
4. 如果还没有打包文件（当前月份），就改为逐份下载快照。
5. 当天的数据写入 `data/raw/<source>/<YYYY>/<YYYYMMDD>.zip`（用快速压缩，级别 1）。交通数据约 31 MB。

### 3b. 解析交通数据 → `traffic_lane`（`src/parse/traffic.py`，版本 3）

| 操作 | 说明 |
|-----------|--------|
| 扫描 | 对每个 XML 文件用正则表达式扫一遍，记录当前的 `<date>`、`<period_from>` 和 `<detector_id>`，每遇到一个 `<lane>` 输出一行。已在一整天的数据（3,611,987 行）上验证，与 ElementTree 解析的结果完全相同 |
| `time` | `date` + `period_from`，即测量时间，从不使用文件的存档时间 |
| **午夜修正** | 如果某个时段比文件的存档时间（取自文件名）早 12 小时以上，就把它往后移一天。这修正的是 00:00 那个带着前一天 `<date>` 的时段。修正次数记为 `n_periods_redated` |
| **截断文件** | 不以 `</raw_speed_volume_list>` 结尾的文件会被计数（`n_truncated_files`）。截断前完整的读数保留；最后一条不完整的车道读数匹配不上正则，自然被丢弃 |
| `sd` | `<s.d.>` 是可选的：约 2021 年 11 月 18 日之前的文件没有，结果为 NaN |
| 类型 | `speed`、`occupancy`、`volume` → `Int16`；`sd` → `float32`；`detector_id`、`lane`、`valid` → 分类类型。非数字的文字会变成 NA（实测没有出现） |
| 丢弃的字段 | `direction`（S2 里有）和 `period_to`（= `time` + 30 秒） |
| **去重** | 相邻文件重叠造成的（`time`，`detector_id`，`lane`）完全重复只保留第一条。约占 9% 的行 |
| 排序 | 按 `detector_id`、`lane`、`time` |
| **不做的事** | 不会因为数值而删除或修改任何一行：车流为 0 时的车速填充值、`valid = N`、`speed > 130`、`occupancy = -1` 等都保留 |

### 3c. 解析天气报告 → `rainfall_district`（`src/parse/weather.py`，版本 1）

| 操作 | 说明 |
|-----------|--------|
| 文字 | 解码 HTML 实体，去掉标签，合并空白 |
| `bulletin_time` | 取自标题 `Bulletin updated at HH:MM HKT DD/MM/YYYY`（公告发布时间，不是存档时间） |
| **统计时段** | 取自 `Between H:MM [a.m./p.m.] and H:MM a.m./p.m.`：把结束时间转成 24 小时制，并取**不晚于** `bulletin_time` 的最近一个该时刻（这样能正确处理跨午夜、跨中午和迟发的公告）；`period_start` = 结束时间 − 1 小时 |
| 各区数值 | `rainfall recorded in various regions were:` 后面的内容按 `;` 拆开。每一项必须符合 `<区名> <最小值> [to <最大值>] mm`，**否则直接报错**，这样格式一旦改变就不会被悄悄忽略 |
| 区名 | 统一写法：去掉 ` District` 后缀，` and ` 改为 ` & `。遇到不认识的区名直接报错 |
| **补 0** | 每份公告都输出 **18 行**（每区一行）。没列出的区雨量记为 0，`listed = False` |
| **没有雨量句** | 18 个区全部记为 0，`section_present = False`。统计时段推断为公告发布前至少 15 分钟的最近一个 HH:45 |
| 去重 | 同一份公告被存档两次时只保留一份（按 `bulletin_time`、`district`） |

### 3d. 写文件、清理、记录

- 用 `src/storage.py` 写出结果：先写 `.part` 临时文件再改名（原子写入），并把解析器版本和解析统计存进 Parquet 元数据。
- 删除 ZIP（加 `--keep-raw` 则保留）。
- `data/processed/coverage.csv` 每个（数据源，日期）一行：`status`（`ok` / `no_data` / `failed`）、`version`、
  `n_snapshots`、`n_rows_raw`、`n_rows`、`n_periods`、`n_detectors`、`has_sd`、`n_periods_redated`、
  `n_truncated_files`（交通），以及 `n_bulletins`、`n_with_rain_section`、`max_rain_mm`（天气），`error`。
  不适用于该数据源的列留空。

### 并行调度

主进程负责下载；解析在 `--jobs` 个子进程中进行（默认 3 个，解析一天交通数据每个进程约需 1.6 GB 内存）。
下载最多只比解析超前 `--jobs` 天，所以硬盘上同时只有几个 ZIP。
某一天失败时，会记进 `coverage.csv`，然后继续处理下一天。进度条显示已完成的天数和文件下载进度。

### 过期检测

只有当某天的文件存在，**而且**文件里记录的解析器版本等于当前版本（`traffic.VERSION`、`weather.VERSION`）时，
才会跳过这一天；否则重新生成，并打印 `[stale]` 提示。加入版本记录之前生成的文件没有版本号，一律重新生成。

---

## 读取处理后的数据（`src/data.py`）

每天的文件里是**当天存档**的内容。因为存档比测量时间晚，第 *d* 天最后约 10 分钟的数据在第 *d + 1* 天的文件里。
所以 `load_traffic_lane(days)` / `load_rainfall_district(days)` 会：

1. 读取所需每一天的文件，**以及后一天的文件**；
2. 只保留 `time` / `period_end` 落在所需日期内的行；
3. 合并（保持分类类型不变），去掉重复的主键；
4. 按主键排序。

如果后一天还没处理，那最后几分钟的数据就会缺失（验证时会给出 WARN）。

---

## 第 4 步：每探测器每 15 分钟 `python -m src.aggregate`（`src/aggregate.py`，版本 1）

输入：`load_traffic_lane([day])`。按 `detector_id` 和 `t_bin`（`time` 向下取整到 15 分钟）分组。

| 列 | 定义 |
|--------|------------|
| `n_readings` | 这 15 分钟内的车道读数条数 |
| `n_periods` | 不同的 30 秒时段个数（最多 30；因为存档有缺口，通常约 18） |
| `n_invalid` | `valid = N` 的读数条数 |
| `n_zero_volume` | `volume = 0` 的读数条数（这些读数的车速是填充值） |
| `n_speed_over_130` | `speed > 130` 的读数条数 |
| `speed_naive` | **所有**读数的 `speed` 平均值（不做任何清洗） |
| `speed_clean` | 只用 `valid = Y` 且 `volume > 0` 的读数，按车流量加权平均：Σ(车速 × 车流) / Σ 车流；没有这样的读数时为 **NA**（约占 1% 的格子） |
| `volume_sum` | `valid = Y` 的读数的车流量总和 |
| `occupancy_mean` | `valid = Y` 的读数的占用率平均；全部读数都无效时为 NA |

`speed_clean` 只去掉了填充值和被标为无效的读数，**不会**过滤超出范围的车速（实测最大 186）。
输出文件的元数据记录了汇总代码的版本，以及所用两个 `traffic_lane` 文件的版本。
其中任何一个改变，或者后一天的文件后来才生成，这一天都会重新计算。

---

## 验证（`src/validate.py`）

`python -m src.validate --manifest|--days|--range`（每次运行 `src.pipeline` 后也会自动运行）。

| 等级 | 含义 | 例子 |
|-------|---------|----------|
| FAIL | 数据肯定有错 | 文件缺失或由旧版本代码生成；必填列有 NA；主键重复；午夜日期错误的读数；日期不属于当天的行；未知的 `valid` / 车道 / 区名；某小时不是正好 18 个区；`rain_min_mm > rain_max_mm`；没列出的区却有雨量；`n_periods > 30` |
| WARN | 可疑 | 30 秒时段不到 50%；有截断的原始文件；探测器不在 S2 里；后一天还没处理；雨量不足 24 小时；`occupancy > 100`；`speed < 0` |
| INFO | 清洗前需要知道的情况 | `volume = 0` 的比例及此时最常见的车速；`speed = 0` 但 `volume > 0`；`speed > 130`；`occupancy < 0` 和 `= 100`；`valid = N` 的比例；`speed_clean` 为 NA 的比例；S8 里的非数字值 |

参考表也会检查：S2 的探测器编号是否重复、区名写法、名字末尾空格、多个探测器共用同一名字；
警告的结束时间是否早于开始时间、信号是否重叠；假期日期是否重复；S8 里的 `Trace` / `***`。

输出：
- `data/processed/validation_report.md`，包括：汇总、问题列表、逐日检查结果、参考表检查，
  以及**每张表的体检**（逐列列出：类型、NA 数量和比例、唯一值个数、最小值和最大值、出现最多的值）。
- `data/processed/validation_checks.csv`：每项检查一行。
- 有任何 FAIL 时，程序以退出码 1 结束。

---

## 版本号规则

只要改动会改变某个模块的**输出**，就把该模块的 `VERSION` 加一，并在它上方的注释里说明改了什么：

| 模块 | 常量 | 当前版本 | 历史 |
|--------|----------|---------|---------|
| `src/parse/traffic.py` | `VERSION` | 3 | 1 初版 · 2 午夜日期修正 · 3 统计截断文件 |
| `src/parse/weather.py` | `VERSION` | 1 | 1 初版 |
| `src/aggregate.py` | `VERSION` | 1 | 1 初版 |

下次运行 `src.pipeline` / `src.aggregate` 时会重新生成受影响的日子；
如果还有旧版本生成的文件，`src.validate` 会报 FAIL。

---

## 尚未完成

以下是后续阶段和本项目的对照实验，不属于这条流水线：

- **清洗：** 车速填充值、`valid = N`、超出范围的值、卡住的探测器、缺失时段（P1–P6）。
- **关联：** 探测器 ↔ 分区雨量（统一运输署和天文台的区名写法）、把逐小时雨量对齐到 15 分钟、
  每个时间格的警告状态、假期和日期类型、排除台风时段（P7–P11）。
- **S8**（逐日雨量）目前只是原样保存，没有解析。使用时必须把 `Trace` 转成约等于 0，把 `***` 转成 NA。
