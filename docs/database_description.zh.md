# 数据库说明

> 本文是 [`database_description.md`](database_description.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

本文档说明项目用到的每个数据来源，以及我们用它们建立的表：每个来源从哪里来、原始字段是什么意思、
预处理后怎样存储，以及各表之间怎样关联。

所有来源都在 2026 年 9 月对照实时服务和 DATA.GOV.HK 历史存档核对过。除特别说明外，所有时间都是
**香港时间（HKT，UTC+8）**，存储时不带时区。

---

## 1. 数据来源清单

"已下载"指 `data/raw/` 下硬盘上已有的数据（清单、位置和数据字典见
[`raw_data.zh.md`](raw_data.zh.md) 的"数据清单"一节）。"已解析"指 `src.pipeline` 已把它处理成表；
这个处理流程正在重写，改为读取已下载的月度打包文件。

| 编号 | 来源（提供者） | 获取方式 | 频率 | 已下载 | 用途 | 状态 |
|----|----------------|----------|------|--------|------|------|
| S1 | [交通车速、车流及道路占用率（原始数据）](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)，`rawSpeedVol-all.xml`（运输署） | 历史存档（`hkdata.download`） | 30 秒时段，每分钟发布 | 2024-01 至 2025-12（存档自 2021 年 6 月起；2021 年 11 月前只有 42 个探测器） | 目标变量 | **必需**；已下载；已解析（旧流程，362 个选定日） |
| S2 | [交通探测器位置](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv)，CSV（运输署） | 历史存档（`hkdata.download`、`src.download static-history`） | 按版本 | 8 个版本，2021-08 至 2026-04 | 探测器属性、空间关联 | **必需**；已下载 |
| S3 | [现时天气报告](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report)，`CurrentWeather.xml`（天文台） | 历史存档（`hkdata.download`） | 每小时 | 2024-01 至 2025-12（存档自 2021 年 6 月起） | **分区**过去一小时雨量 | **必需**；已下载；已解析（旧流程，362 个选定日） |
| S4 | [暴雨警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml)，`rstorm.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1998 年 3 月至今 | 每个时刻的警告状态 | **必需**；已下载；已解析 |
| S5 | [热带气旋警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml)，`tc.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1946 年至今 | 排除台风时段 | **必需**；已下载；已解析 |
| S6 | [香港公众假期](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal)，`en.json`（1823） | 直接下载 + 历史存档（`src.download holidays`） | 每年 | 各存档版本合起来覆盖 2018–2027 | 工作日 / 周末 / 假期 | **必需**；已下载；已解析 |
| S8 | [逐日总雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall)，`daily_HKO_RF_ALL.csv`（天文台） | 直接下载（`src.download static`） | 每天 | 1884 年至今 | 按日核对 | 辅助；已下载 |
| S9 | [智能灯柱交通探测器](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts)，`rawSpeedVol_SLP-all.xml`（运输署） | 历史存档（`hkdata.download`） | 30 秒时段 | 2024-01 至 2025-12 | 额外的探测器（格式与 S1 相同） | 可选；已下载 |
| S10 | 智能灯柱探测器位置，CSV（运输署） | 历史存档（`hkdata.download`） | 按版本 | 2023-12、2024-01 | S9 探测器的属性 | 可选；已下载 |
| S11 | 路网路段车速（处理后数据），`irnAvgSpeed-all.xml`（运输署） | 历史存档（`hkdata.download`） | 约 1 分钟 | 2024-01 至 2025-12 | 运输署自己算的路段车速，用于交叉核对 | 可选；已下载 |
| N1 | [路网路段](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv)，`speed_segments_info.csv`（运输署） | 历史存档（`hkdata.download`、`src.download static-history`） | 按版本 | 6 个版本，2021-08 至 2023-09 | S11 的路段 → 路线编号 | 可选；已下载 |
| S12 | [第二代道路网络](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2)，`RdNet_IRNP.gdb.zip`（运输署） | 历史存档（`hkdata.download`） | 按版本 | 2024-01 至 2025-12（34 个版本） | S11 路段的几何（`ROUTE_ID`） | 可选；已下载 |
| S13 | [特别交通消息（第二代）](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2)，`trafficnews.xml`（运输署） | 历史存档（`hkdata.download`） | 每条消息的每次更新 | 2024-01 至 2025-12 | 把事故 / 封路标记为干扰因素 | 可选；已下载 |
| S7 | [格点雨量临近预报](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv)，CSV（天文台） | 历史存档（`hkdata.download`） | 约每 15 分钟 | 2024-01 至 2025-12（存档自约 2022 年 7 月起） | 局部（约 2 公里）雨量的代理变量 | 可选；已下载 |

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
**[`raw_data.zh.md`](raw_data.zh.md)**，使用相同的编号 S1–S13 和 N1，并注明每个来源的数据字典放在哪里。
每个来源怎样变成下面的表，见 **[`processing.zh.md`](processing.zh.md)**。

---

## 3. 处理后的数据库结构

每个处理后的 Parquet 文件在结构元数据（键 `hkrt`）里存一条 JSON 记录，包括表名、生成它的**代码版本**、日期和解析统计。
用 `src.storage.read_meta(path)` 读取。过时的文件会被处理流程重建，并被 `src.validate` 标出
（见 [`processing.zh.md`](processing.zh.md) 的版本规则一节）。

表存为 Parquet（大表，按天分文件）或 CSV（小表）。PK = 主键。

### `traffic_lane`：清洗前的事实表（来自 S1）

`data/processed/traffic_lane/<YYYY>/<YYYYMMDD>.parquet`（每个存档日一个文件），每天约 360 万行、约 11 MB。
由 `src/parse/traffic.py` 经 `python -m src.pipeline` 生成；用 `src.data.load_traffic_lane` 读取。

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `time` | 时间戳 | ✓ | 时段开始（`date` + `period_from`） |
| `detector_id` | 分类 | ✓ | 外键 → `detectors` |
| `lane` | 分类 | ✓ | 来自 `lane_id` 的车道标签 |
| `speed` | int16 | | km/h，原样保留 |
| `occupancy` | int16 | | %，原样保留 |
| `volume` | int16 | | 辆 / 30 秒 |
| `sd` | float32 | | 车速标准差；约 2021 年 11 月 18 日之前缺失 |
| `valid` | 分类 | | `Y`/`N`，原样保留 |

这一步只删除完全重复的行。其他清洗选择（无效行、零车流时的车速、离群值、缺口）之后作为 `PROPOSAL.md`
里的实验变量 P1–P6 再处理。`direction` 和 `period_to` 被丢弃，因为 S2 和 `time` + 30 秒已经提供了它们。

### `traffic_15min`：探测器 × 15 分钟表（来自 `traffic_lane`）

`data/processed/traffic_15min/<YYYY>/<YYYYMMDD>.parquet`，由 `python -m src.aggregate` 生成。每天约 7.4 万行、约 0.9 MB。

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `detector_id` | 分类 | ✓ | |
| `t_bin` | 时间戳 | ✓ | 15 分钟时段的开始 |
| `n_readings` | int32 | | 时段内的车道读数条数 |
| `n_periods` | int32 | | 不同的 30 秒时段数（最多 30） |
| `n_invalid`、`n_zero_volume`、`n_speed_over_130` | int32 | | 质量计数 |
| `speed_naive` | float32 | | 所有读数的简单平均 |
| `speed_clean` | float32 | | `valid == 'Y'` 且 `volume > 0` 的读数按车流加权平均 |
| `volume_sum` | float32 | | 车辆数，只算有效读数 |
| `occupancy_mean` | float32 | | %，只算有效读数 |

### `detectors`：维度表（来自 S2）

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `detector_id` | 字符串 | ✓ | 来自 `AID_ID_Number` |
| `district` | 字符串 | | 统一成 18 区的标准名称（见第 5 节） |
| `road_en`、`road_tc` | 字符串 | | 位置描述 |
| `latitude`、`longitude` | 浮点 | | WGS84 |
| `easting`、`northing` | 浮点 | | 香港 1980 方格网（米） |
| `direction`、`rotation` | 字符串、整数 | | 行车方向 |
| `n_lanes` | 整数 | | 从 `traffic_lane` 推出 |
| `road_type` | 字符串 | | 之后推出，例如快速公路 / 主干道 / 市区道路（问题 2 的特征） |

### `rainfall_district`：事实表（来自 S3）

`data/processed/rainfall_district/<YYYY>/<YYYYMMDD>.parquet`，每份公告 × 18 区各一行。
由 `src/parse/weather.py` 生成；用 `src.data.load_rainfall_district` 读取。

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `period_end` | 时间戳 | ✓ | 1 小时累计时段的结束，例如 07:45 |
| `district` | 分类 | ✓ | 18 区标准名称（运输署写法，见第 5 节） |
| `period_start` | 时间戳 | | `period_end` − 1 小时 |
| `rain_min_mm` | float32 | | 区内最低的雨量站读数（没列出则为 0） |
| `rain_max_mm` | float32 | | 区内最高的雨量站读数（没列出则为 0） |
| `bulletin_time` | 时间戳 | | 公告发布时间（取自标题，不是存档时间） |
| `listed` | 布尔 | | 该区出现在雨量那句话里 |
| `section_present` | 布尔 | | 公告里有没有雨量那句话 |

在有雨量那句话的公告里没列出的区，就是没下雨。没有那句话的公告表示全港都没下雨，
其时段推定为 `bulletin_time` 前至少 15 分钟的最后一个 HH:45。

### `rainfall_grid`：可选事实表（来自 S7）

| 列 | 类型 | PK | 说明 |
|----|------|----|------|
| `issue_time` | 时间戳 | ✓ | 临近预报发布时间 |
| `cell_id` | 整数 | ✓ | 网格单元（经纬度索引） |
| `rain_30min_mm` | 浮点 | | 只取第一个预报时效 |

另有 `detector_cell`（`detector_id` → 最近的 `cell_id` 及距离），只保留探测器附近的网格单元。

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

### `calendar`：推导出的维度表

每个日期一行：`date`（PK）、`weekday`、`is_weekend`、`is_holiday`、
`day_type`（`workday` / `saturday` / `sunday_holiday`）、`has_rainstorm_warning`、
`has_tc_signal`、`manifest_role`（`event` / `control` / 无）。

### `coverage`：处理流程日志

`data/processed/coverage.csv`，每个（`source`，`date`）一行：`status`（`ok` / `no_data` / `failed`）、
`version`、`n_snapshots`、`n_rows_raw`、`n_rows`、`n_periods`、`n_detectors`、`has_sd`、`n_periods_redated`、`n_truncated_files`（交通）、
`n_bulletins`、`n_with_rain_section`、`max_rain_mm`（天气）、`error`。

### `validation_report.md` / `validation_checks.csv`：数据检查

在 `data/processed/`，由 `python -m src.validate` 写出（每次 `src.pipeline` 运行后也会写）。
CSV 每个检查一行：`table`、`day`、`name`、`level`（`FAIL` / `WARN` / `INFO` / `OK`）、`value`、`detail`。
Markdown 报告另外给每张表做概况统计（NA、不同值的个数、最常见的值）。见 [`processing.zh.md`](processing.zh.md) 的检查一节。

### `day_manifest`：下载计划（已有）

`data/interim/day_manifest.csv`：`date`、`role`（`event` / `control`）、`episode_ids`、`max_level`、`max_level_name`。

---

## 4. 表之间的关系

```
                         calendar (date) ◀──── public_holidays (date)
                              ▲
                              │ date(time)
traffic_lane ──detector_id──▶ detectors ──district──▶ rainfall_district
  (time, detector_id, lane)        │                  (period_end, district)
        │                          │  nearest cell         ▲
        │                          └──────────────▶ rainfall_grid (optional)
        │                                                  │
        └──────── time aligned to rainfall window ─────────┘
        │
        └── time ∈ [start, end) ──▶ rainstorm_warnings / rainstorm_episodes / tc_signals
```

建模用的表（下一阶段）是按探测器和时间段聚合后的 `traffic_lane`，再通过这些键关联其他表。
每一个关联选择（聚合时间窗、雨量取最小 / 中间 / 最大值、时间滞后、警告编码）都是一个预处理实验。

---

## 5. 已知数据问题

| 来源 | 问题 | 处理方式 |
|------|------|----------|
| S1 | 探测器网络在扩大：42 个（2021 年 7 月）、554 个（2021 年 12 月）、约 680 个（2023 年）、770 个（2025 年） | 研究年份 2022–2025；每个探测器单独建基线 |
| S1 | 约 2021 年 11 月 18 日之前没有 `s.d.` 元素 | 解析器把它当作可选（`sd` = NaN） |
| S1 | 每天的快照数随月份变化（约 530–1,430） | 每天的覆盖情况记录在 `data/processed/coverage.csv` |
| S1 | 文件时间 ≠ 测量时间：08:01 存档的文件里是 07:53–07:54 的数据 | 用 `period_from` |
| S1 | 少数存档文件在中途被截断（2025 年 7 月 29 日 919 份中有 1 份） | 保留截断前完整的读数；计入 `n_truncated_files` |
| S1 | 00:00 那个时段带的是前一天的 `<date>` | 用文件的存档时间修正（覆盖表中的 `n_periods_redated`） |
| S1 | 相邻文件重叠（约 9% 的行重复）；打包文件偶尔把同一个文件存两次 | 按（`time`、`detector_id`、`lane`）去重 |
| S1 | 每天 2,880 个时段只有 1,730 个（约 40% 缺失） | 缺口处理 = 实验 P6 |
| S1 | `volume = 0` 时（27.7% 的行），`speed` 是等于限速的填充值（70/80/100/50/110，s.d. = 0），不是测量值 | 当作缺失 / 自由流，属于实验 P3 |
| S1 | `occupancy = -1`（60 行）、`speed` 最高 300、`speed = 0` 但 `volume > 0`（2025 年 8 月 5 日 5,991 行） | 物理范围过滤，实验 P2 |
| S1 / S2 | 772 个探测器有数据，但 S2 列出 807 个（2026-04 版本）；硬盘上有 S2 的 8 个版本（2021-08 至 2026-04） | 用当时生效的版本；内连接；报告没匹配上的编号 |
| S2 | 区名写法：`Central & Western` 和 `Central and Western`（1 行）；97% 的 `Road_EN` 末尾有多余空格 | 统一写法，去掉空格 |
| S2 / S3 | 运输署写 `Southern`，天文台写 `Southern District`（Eastern、Islands、North、Central & Western 同理） | 去掉 ` District` 后缀，`and` 统一为 `&` |
| S3 | 雨量是每区的最小–最大范围，不是一个值 | 取最小 / 中间 / 最大值 = 实验 P7 |
| S3 | 自由文字格式；措辞可能逐年变化 | 正则解析器，用每年的样本做单元测试 |
| S4 / S5 | 有 `24:00` 结束时间；`UUUU` 之后是临时记录 | 解析器已处理 |
| S3 | 存档时间 ≠ 公告时间（20:02 存档的文件里是 19:02 的公告）；有些公告很晚才发（01:46） | 用公告自己的时间戳，以它为准确定时段 |
| S6 | 每个文件只覆盖 3 年 | 合并各存档版本，按日期去重 |
| S7 | 是预报，不是观测；约 2022 年 7 月起才有 | 只作可选的敏感性检查 |

---

## 6. 数据量

| 范围 | 天数 | S1 ZIP（下载） | `traffic_lane` Parquet | S3 |
|------|------|----------------|------------------------|----|
| 1 天 | 1 | 31 MB | 10 MB | 50 kB |
| 红雨及以上事件 + 对照日，2022–2025 | 59 | 约 1.8 GB | 约 0.7 GB | 约 3 MB |
| 黄雨及以上事件 + 对照日，2022–2025 | 298 | 约 9.2 GB | 约 3.3 GB | 约 15 MB |
| 全部存档（2021 年 6 月 – 2026 年 9 月） | 约 1,950 | 约 64 GB | 约 21 GB | 约 0.1 GB |

处理流程把每天的 ZIP 转成 Parquet 后就删除 ZIP，所以硬盘占用大致等于 Parquet 那一列。
