# 数据库说明

> 本文是 [`database_description.md`](database_description.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

本文档说明项目用到的每个数据来源，以及我们用它们建立的表：每个来源从哪里来、原始字段是什么意思、
预处理后怎样存储，以及各表之间怎样关联。

所有来源都在 2026 年 9 月对照实时服务和 DATA.GOV.HK 历史存档核对过。除特别说明外，所有时间都是
**香港时间（HKT，UTC+8）**，存储时不带时区。

---

## 1. 数据来源清单

"已下载"指 `data/raw/` 下硬盘上已有的数据（清单、位置和数据字典见
[`raw_data.zh.md`](raw_data.zh.md) 的"数据清单"一节）。"已解析"指 `src.download` 还会用它生成一张表（见第 3 节）。
数据处理流程正在重写，目前还没有任何来源有处理后的表。

| 编号 | 来源（提供者） | 获取方式 | 频率 | 已下载 | 用途 | 状态 |
|----|----------------|----------|------|--------|------|------|
| S1 | [交通车速、车流及道路占用率（原始数据）](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)，`rawSpeedVol-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 30 秒时段，每分钟发布 | 2024-01 至 2025-12（存档自 2021 年 6 月起；2021 年 11 月前只有 42 个探测器） | 目标变量 | **必需**；已下载 |
| S2 | [交通探测器位置](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv)，CSV（运输署） | 历史存档（`hkgovdata.download`、`src.download static-history`） | 按版本 | 8 个版本，2021-08 至 2026-04 | 探测器属性、空间关联 | **必需**；已下载 |
| S3 | [现时天气报告](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report)，`CurrentWeather.xml`（天文台） | 历史存档（`hkgovdata.download`） | 每小时 | 2024-01 至 2025-12（存档自 2021 年 6 月起） | **分区**过去一小时雨量 | **必需**；已下载 |
| S4 | [暴雨警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml)，`rstorm.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1998 年 3 月至今 | 每个时刻的警告状态 | **必需**；已下载；已解析 |
| S5 | [热带气旋警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml)，`tc.dat`（天文台） | 直接下载（`src.download warnings`） | 每次事件 | 1946 年至今 | 排除台风时段 | **必需**；已下载；已解析 |
| S6 | [香港公众假期](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal)，`en.json`（1823） | 直接下载 + 历史存档（`src.download holidays`） | 每年 | 各存档版本合起来覆盖 2018–2027 | 工作日 / 周末 / 假期 | **必需**；已下载；已解析 |
| S8 | [逐日总雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall)，`daily_HKO_RF_ALL.csv`（天文台） | 直接下载（`src.download static`） | 每天 | 1884 年至今 | 按日核对 | 辅助；已下载 |
| S9 | [智能灯柱交通探测器](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts)，`rawSpeedVol_SLP-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 30 秒时段 | 2024-01 至 2025-12 | 额外的探测器（格式与 S1 相同） | 可选；已下载 |
| S10 | 智能灯柱探测器位置，CSV（运输署） | 历史存档（`hkgovdata.download`） | 按版本 | 2023-12、2024-01 | S9 探测器的属性 | 可选；已下载 |
| S11 | 路网路段车速（处理后数据），`irnAvgSpeed-all.xml`（运输署） | 历史存档（`hkgovdata.download`） | 约 1 分钟 | 2024-01 至 2025-12 | 运输署自己算的路段车速，用于交叉核对 | 可选；已下载 |
| S14 | [路网路段](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv)，`speed_segments_info.csv`（运输署） | 历史存档（`hkgovdata.download`、`src.download static-history`） | 按版本 | 6 个版本，2021-08 至 2023-09 | S11 的路段 → 路线编号 | 可选；已下载 |
| S12 | [第二代道路网络](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2)，`RdNet_IRNP.gdb.zip`（运输署） | 历史存档（`hkgovdata.download`） | 按版本 | 2024-01 至 2025-12（34 个版本） | S11 路段的几何（`ROUTE_ID`） | 可选；已下载 |
| S13 | [特别交通消息（第二代）](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2)，`trafficnews.xml`（运输署） | 历史存档（`hkgovdata.download`） | 每条消息的每次更新 | 2024-01 至 2025-12 | 把事故 / 封路标记为干扰因素 | 可选；已下载 |
| S7 | [格点雨量临近预报](https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv)，CSV（天文台） | 历史存档（`hkgovdata.download`） | 约每 15 分钟 | 2024-01 至 2025-12（存档自约 2022 年 7 月起） | 局部（约 2 公里）雨量的代理变量 | 可选；已下载 |

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

**处理后的表：将随新流程重新设计。** 之前的表（`traffic_lane`、`traffic_15min`、`rainfall_district`，
规划中的 `detectors`、`rainfall_grid` 和 `calendar`，以及 `coverage` 日志和数据检查报告）已于 2026-09-29
连同生成它们的代码一起删除；它们的定义在该日期之前的 git 历史里。

除原始文件外，硬盘上现有的是 `src.download` 生成的几张小表（怎样生成见 [`processing.zh.md`](processing.zh.md)）。PK = 主键。

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
新流程不使用；保留给之后的分析。

---

## 4. 表之间的关系

之前的设计，将随新流程重新确定：

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

"处理方式"是之前的流程的做法；新流程会重新决定。

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
