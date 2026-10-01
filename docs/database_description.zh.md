# 数据库说明

> 本文是 [`database_description.md`](database_description.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

本文档说明项目用到的每个数据来源，以及我们用它们建立的表：每个来源从哪里来、原始字段是什么意思、
预处理后怎样存储，以及各表之间怎样关联。

所有来源都在 2026 年 9 月对照实时服务和 DATA.GOV.HK 历史存档核对过。除特别说明外，所有时间都是
**香港时间（HKT，UTC+8）**，存储时不带时区。

---

## 1. 数据来源清单

"已下载"指下载到 `data/raw/` 的数据（清单、位置和数据字典见
[`raw_data.zh.md`](raw_data.zh.md) 的"数据清单"一节）；自 2026-09-30 起，S1、S7、S9、S11 的打包文件只在硬盘上保留三个研究月份
（2024-05、2025-07、2025-08）。"状态"写的是已经生成的层（L1 原样保存，L2 清洗后；见第 3 节和
[`processing.zh.md`](processing.zh.md)）；L3 由主要来源的 L2 生成。

| 编号 | 来源（提供者） | 获取方式 | 频率 | 已下载 | 用途 | 状态 |
|----|----------------|----------|------|--------|------|------|
| S1 | [交通车速、车流及道路占用率（原始数据）](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)，`rawSpeedVol-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 30 秒时段，每分钟发布 | 2024-01 至 2025-12（存档自 2021 年 6 月起；2021 年 11 月前只有 42 个探测器） | 目标变量 | **必需**；L1、L2 |
| S2 | [交通探测器位置](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv)，CSV（运输署） | 历史存档（`hkgovdata.download`、`src.download static-history`） | 按版本 | 8 个版本，2021-08 至 2026-04 | 探测器属性、空间关联 | **必需**；L1、L2 |
| S3 | [现时天气报告](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report)，`CurrentWeather.xml`（天文台） | 历史存档（`hkgovdata.download`） | 每小时 | 2024-01 至 2025-12（存档自 2021 年 6 月起） | **分区**过去一小时雨量 | **必需**；L1、L2 |
| S4 | [暴雨警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml)，`rstorm.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1998 年 3 月至今 | 每个时刻的警告状态 | **必需**；L1、L2 |
| S5 | [热带气旋警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml)，`tc.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1946 年至今 | 排除台风时段 | **必需**；L1、L2 |
| S6 | [香港公众假期](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal)，`en.json`（1823） | 直接下载 + 历史存档（`src.download holidays`） | 每年 | 各存档版本合起来覆盖 2018–2027 | 工作日 / 周末 / 假期 | **必需**；L1、L2 |
| S8 | [逐日总雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall)，`daily_HKO_RF_ALL.csv`（天文台） | 直接下载（`src.download static`） | 每天 | 1884 年至今 | 按日核对 | 辅助；L1、L2 |
| S9 | [智能灯柱交通探测器](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts)，`rawSpeedVol_SLP-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 30 秒时段 | 2024-01 至 2025-12 | 额外的探测器（格式与 S1 相同） | 可选；L1 |
| S10 | 智能灯柱探测器位置，CSV（运输署） | 历史存档（`hkgovdata.download`） | 按版本 | 2023-12、2024-01 | S9 探测器的属性 | 可选；L1 |
| S11 | 路网路段车速（处理后数据），`irnAvgSpeed-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 约 1 分钟 | 2024-01 至 2025-12 | 运输署自己算的路段车速，用于交叉核对 | 可选；L1 |
| S14 | [路网路段](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv)，`speed_segments_info.csv`（运输署） | 历史存档（`hkgovdata.download`、`src.download static-history`） | 按版本 | 6 个版本，2021-08 至 2023-09 | S11 的路段 → 路线编号 | 可选；L1 |
| S12 | [第二代道路网络](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2)，`RdNet_IRNP.gdb.zip`（运输署） | 历史存档（`hkgovdata.download`） | 按版本 | 2024-01 至 2025-12（34 个版本） | S11 路段的几何（`ROUTE_ID`） | 可选；L1 |
| S13 | [特别交通消息（第二代）](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2)，`trafficnews.xml`（运输署） | 历史存档（`hkgovdata.download`） | 每条消息的每次更新 | 2024-01 至 2025-12 | 把事故 / 封路标记为干扰因素 | 可选；L1 |
| S7 | [格点雨量临近预报](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv)，CSV（天文台） | 历史存档（`hkgovdata.download`） | 约每 15 分钟 | 2024-01 至 2025-12（存档自约 2022 年 7 月起） | 局部（约 2 公里）雨量的代理变量 | 可选；L1 |

### 考虑过但不使用的来源

| 来源 | 原因 |
|------|------|
| [自动气象站过去一小时雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-rainfall-in-the-past-hour)（`hourlyRainfall.php`，36 个站） | **没有存档。** 对任何日期范围，历史存档 API 都返回 `Not Found`，所以只能从现在开始实时采集。这就是我们用**分区**雨量（S3）代替气象站级别匹配的原因。可选地，格点临近预报（S7）能提供比区更细的信息。 |
| [天文台气象站位置](https://www.hko.gov.hk/en/cis/stn.htm) | 只有做气象站级别的雨量匹配才需要。既然没有历史的气象站数据，就不需要它。只有在加入各站逐日雨量（`daily_<STN>_RF_ALL.csv`）时才会用到。 |
| 天文台 JSON 版现时天气报告（`weather.php?dataType=rhrread`） | 有结构化的分区雨量，但**没有存档**（`Not Found`），所以改为解析 S3 的 RSS 文字。 |
| [天气警告摘要 / 天气警告资料](https://data.gov.hk/en-data/dataset/hk-hko-rss-weather-warning-summary)（RSS） | 有存档，但每天只有约**一份快照**（约 10:20），两份快照之间发出又取消的警告会漏掉；S4 / S5 提供准确的开始和结束时间。 |

---

## 2. 原始数据字典

每个原始来源（格式、获取方式、结构、每个字段的官方说明、实测取值和数据问题）都记录在
**[`raw_data.zh.md`](raw_data.zh.md)**，使用相同的编号 S1–S14，并注明每个来源的数据字典放在哪里。
每个来源怎样变成下面的表，见 **[`processing.zh.md`](processing.zh.md)**。

---

## 3. 表

全部在 `data/interim/` 下，Parquet 格式，由 [`processing.zh.md`](processing.zh.md) 里的程序生成。
PK = 主键（已核查：键重复时程序会报错）。时间都是香港时间，不带时区。

**L1**（`l1/<来源>/`）：每个原始文件原样保存，所有值都是字符串，每个元素或字段一列；每行记录它来自哪个文件
（`bundle`、`index`）。各来源的列见对应解析程序（`src/clean/*_parse.py`）的 docstring 和
[`raw_data.zh.md`](raw_data.zh.md)。

### L2（`l2/`）

| 表 | 行数 | PK | 列 |
|----|------|----|----|
| `s1/<YYYYMM>.parquet` | 1.231 亿 / 9,990 万 / 1.099 亿 | `detector_id`、`time`、`lane_id` | `time`（30 秒时段的开始）、`detector_id`、`direction`、`lane_id`、`speed`（km/h）、`volume`（30 秒内的车辆数）、`occupancy`（%）、`sd`、`valid`（布尔）、`l2_rule`（修改或生成这一行的规则）、`bundle`、`index`（L1 文件） |
| `s2/detectors.parquet` | 790 | `AID_ID_Number` | S2 的 2025-10 版本，字段名保留原文：`AID_ID_Number`、`District`、`Road_EN`、`Road_TC`、`Road_SC`、`Easting`、`Northing`、`Latitude`、`Longitude`、`Direction`、`Rotation`；另加 `rain_district`（`District` 对应的 S3 区名，D11） |
| `s3/rain.parquet` | 40,176 | `period_end`、`district` | `period_start`、`period_end`（HH:45 → HH:45 的一小时）、`district`（天文台区名）、`low`、`high`（mm）、`l2_rule`（D8 插值，D9 未列出 = 0 mm） |
| `s4/rainstorm.parquet` | 974 | `line` | `line`、`colour`、`level`（1 黄、2 红、3 黑）、`start`、`end`、`provisional` |
| `s5/tc.parquet` | 1,262 | `line` | `line`、`cyclone`、`intensity`、`name`、`signal`（整数）、`direction`、`start`、`end` |
| `s6/holidays.parquet` | 170 | `date` | `date`、`name`、`version`（列出这个日期的最新版本） |
| `s8/daily.parquet` | 49,491 | `date` | `date`、`rain_mm`、`trace`（`Trace` = 0 mm）、`completeness` |

### L3（`l3/<名称>.parquet`）

`default.parquet`：6,430,886 行；变体按改动的选项命名（例如 `speed_agg=mean.parquet`）。
PK `detector_id`、`slot`。

| 类别 | 列 |
|------|----|
| 时间 | `slot`（开始时间）、`month`（YYYYMM）、`date`、`slot_of_day`（00:00 起的分钟数）、`day_type`（weekday / saturday / sunday_holiday）、`holiday`、`season` |
| 探测器 | `detector_id`、`direction`（S1）、`district`（S2）、`rain_district`、`latitude`、`longitude`、`road`、`n_lanes` |
| 交通 | `periods`（有数据的 30 秒时段数）、`coverage`（periods / 应有数）、`speed`（km/h）、`flow`（所有车道每小时车辆数）、`occupancy`（%）、`interpolated`（P6） |
| 雨量 | `rain`（P7 / P8 选出的值）、`rain_mid`、`rain_high`、`rain_max`（18 区中最大的 `high`）、`rain_lag1`（前一小时）、`rain_rule`（S3 的 `l2_rule`） |
| 警告 | `warn_level`（0–3）、`warn_minutes`（警告事件开始后的分钟数）、`tc_signal`（0 或生效中的最高信号） |
| 基线 | `dry`、`base_speed`、`base_flow`、`base_occupancy`、`base_n`（基线背后的干燥时段数）、`ratio`（车速 / 基线车速）、`flow_ratio` |

### `src.download` 生成的表（参考用；L2 / L3 不读）

下载时生成（见 [`processing.zh.md`](processing.zh.md) 的"参考数据"一节）。

### `rainstorm_warnings`：事件表（来自 S4）

`data/raw/hko/rainstorm_warnings.csv`

| 列 | 类型 | 说明 |
|----|------|------|
| `level` | 整数 | 1 黄、2 红、3 黑 |
| `level_name` | 字符串 | |
| `start`、`end` | 时间戳 | `24:00` 改为第二天 00:00 |
| `duration_min` | 整数 | |
| `provisional` | 布尔 | `UUUU` 之后的行 |

### `rainstorm_episodes`：事件表（由 S4 推出）

`data/interim/rainstorm_episodes.csv`。首尾相接的信号（结束 = 下一个开始）合并在一起，例如黄 → 红 → 黑 → 黄。

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `episode_id` | 整数 | ✓ | |
| `start`、`end` | 时间戳 | | |
| `max_level`、`max_level_name` | 整数、字符串 | | 达到的最高级别 |
| `n_signals` | 整数 | | 合并的信号数 |
| `duration_min` | 整数 | | |
| `provisional` | 布尔 | | |

### `tc_signals`：事件表（来自 S5）

`data/raw/hko/tc_signals.csv`：`tc_code`、`name`、`intensity`、`signal`、`direction`、`start`、`end`、`provisional`。

### `public_holidays`：维度表（来自 S6）

`data/raw/calendar/public_holidays.csv`，2018–2027（每年 17 个），由 10 个存档版本加实时文件合并而成。

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `date` | 日期 | ✓ | |
| `name` | 字符串 | | |

### `day_manifest`：选出的日子（来自 `select-days`）

`data/interim/day_manifest.csv`：`date`、`role`（`event` / `control`）、`episode_ids`、`max_level`、`max_level_name`。
现在的流程不使用；保留给之后的分析。

---

## 4. 表之间的关系

L3 怎样关联各张 L2 表（`src/l3.py`）：

```
l2/s1  (detector_id, time, lane_id)
   │  车道读数 → 探测器 × 时段（P1–P6）
   ▼
l3 slot ──detector_id = AID_ID_Number──▶ l2/s2 detectors   （每个 S1 探测器都必须在 S2 里）
   │                                        │ rain_district = district
   │  slot ∈ [period_start, period_end)     ▼
   ├────────────────────────────────▶ l2/s3 rain  （以及前一小时：rain_lag1）
   ├── slot ∈ [start, end) ─────────▶ l2/s4 rainstorm  （信号 → 事件：warn_level、warn_minutes）
   ├── slot ∈ [start, end) ─────────▶ l2/s5 tc  （tc_signal）
   └── date ────────────────────────▶ l2/s6 holidays  （day_type）
```

`l2/s8`（天文台总部每日雨量）不参与关联，只用于按日核对。基线把每个时段关联到同一探测器、同一季节、
同一日子类型、同一时段的干燥时段。

---

## 5. 已知数据问题

"处理方式"是现在的流程的做法；规则（D…、P…）见 [`cleaning.md`](cleaning.md)，那里还列出了清洗时发现的问题
（例如 TDS90026、TDS90036、S3 缺失的小时、S5 夏令时）。

| 来源 | 问题 | 处理方式 |
|------|------|----------|
| S1 | 探测器网络在扩大：42 个（2021 年 7 月）、554 个（2021 年 12 月）、约 680 个（2023 年）、770 个（2025 年） | 研究月份 2024-05、2025-07、2025-08；每个探测器单独建基线（P10） |
| S1 | 约 2021 年 11 月 18 日之前没有 `s.d.` 元素 | 不在研究月份内；L2 没有空的 `sd` |
| S1 | 每天的快照数随月份变化（约 530–1,430） | 缺失的时段保持缺失（不补）；L3 每个时段记录 `periods` / `coverage`；连续缺 1–2 个时段时插值并标记（P6） |
| S1 | 文件时间 ≠ 测量时间：08:01 存档的文件里是 07:53–07:54 的数据 | `time` = 时段开始；L2 检查它在抓取时间之前 0–60 分钟内 |
| S1 | 少数存档文件在中途被截断（2025 年 7 月 29 日 919 份中有 1 份） | 3 个截断文件不进 L1（D7） |
| S1 | 00:00 那个时段带的是前一天的 `<date>` | 加一天（D6） |
| S1 | 相邻文件重叠（约 9% 的行重复）；打包文件偶尔把同一个文件存两次 | 字节相同的文件只解析一次（manifest）；L2 遇到同一（探测器、时间、车道）出现两次会报错 |
| S1 | 每天 2,880 个时段只有 1,730 个（约 40% 缺失） | 同上面的快照数 |
| S1 | `volume = 0` 时（27.7% 的行），`speed` 是等于限速的填充值（70/80/100/50/110，s.d. = 0），不是测量值 | 按车流加权的探测器车速（P4）不给它们权重；没有车的时段没有车速，去掉 |
| S1 | `occupancy = -1`（60 行）、`speed` 最高 300、`speed = 0` 但 `volume > 0`（2025 年 8 月 5 日 5,991 行） | `-1`（总是 volume 为 0）→ 0（D21）；车流 > 0 时车速为 0 或 > 130 的去掉（P2） |
| S1 / S2 | 772 个探测器有数据，但 S2 列出 807 个（2026-04 版本）；硬盘上有 S2 的 8 个版本（2021-08 至 2026-04） | 所有月份都用 S2 的 2025-10 版本（D2）；每个 S1 探测器都必须在里面（否则 L3 报错）；方向用 S1 的 `direction`（D1） |
| S2 | 区名写法：`Central & Western` 和 `Central and Western`（1 行）；97% 的 `Road_EN` 末尾有多余空格 | 去空格（D3）；两种写法都对应到天文台的区名（D11） |
| S2 / S3 | 运输署写 `Southern`，天文台写 `Southern District`（Eastern、Islands、North、Central & Western 同理） | 固定的 S2 → 天文台区名对照表；遇到不认识的区名报错（D11） |
| S3 | 雨量是每区的最小–最大范围，不是一个值 | 默认取中点；上限或全港最大值作为备选（P7） |
| S3 | 自由文字格式；措辞可能逐年变化 | 标题或时段格式不认识时报错（L2 S3） |
| S4 / S5 | 有 `24:00` 结束时间；`UUUU` 之后是临时记录 | `24:00` = 第二天 00:00（D20）；`provisional` 保留为一列 |
| S3 | 存档时间 ≠ 公告时间（20:02 存档的文件里是 19:02 的公告）；有些公告很晚才发（01:46） | 时段取自雨量句子，按公告自己的时间定日期；同一时段的多份公告必须一致（D10） |
| S6 | 每个文件只覆盖 3 年 | 所有版本都进 L1；每个日期取列出它的最新版本（L2） |
| S7 | 是预报，不是观测；约 2022 年 7 月起才有 | 可选；只有 L1，还没使用 |
