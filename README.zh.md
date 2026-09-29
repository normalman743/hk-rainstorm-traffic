# hk-rainstorm-traffic

> 本文是 [`README.md`](README.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

香港哪些道路对暴雨最敏感？把天文台的雨量和警告数据与运输署的交通探测器数据整合起来，研究预处理和特征工程如何影响拥堵预测。

> 课程项目。重点是**数据预处理与整合**：每一个主要的清洗 / 聚合 / 匹配决定都当作实验变量，
> 衡量它如何改变后续结果。
> 完整研究计划见 [`PROPOSAL.md`](PROPOSAL.md)；另见
> [`docs/raw_data.zh.md`](docs/raw_data.zh.md)（每个原始数据来源和字段）、
> [`docs/processing.zh.md`](docs/processing.zh.md)（每个处理步骤做什么）和
> [`docs/database_description.zh.md`](docs/database_description.zh.md)（处理后的表）。

## 当前进度（2026-09-29）

- **数据：已齐全。** 分析需要的所有来源，加上可选的扩展数据，都已下载了 2024-01 至 2025-12
  （原始月度打包文件约 53 GB），每个都配有官方数据字典。
  清单见 [`docs/raw_data.zh.md`](docs/raw_data.zh.md) 的"数据清单"一节。
- **下一步：数据处理。** 正在编写脚本，把原始打包文件处理成分析用的表。
  下方的"数据处理流程"一节描述的仍是之前按天处理的流程。

## 研究问题

1. **敏感性：** 控制时段和星期几之后，暴雨期间哪些路段的车速下降 / 占用率上升最大？
2. **预测：** 道路属性加上雨量特征，能否比只用时间的基线模型更好地预测暴雨期间的拥堵？
3. **预处理的影响：** 离群值处理、聚合时间窗、雨量与道路的匹配方式、警告编码方式等选择，会在多大程度上改变问题 1 和问题 2 的答案？

## 数据来源

全部是免费的香港政府公开数据。大文件都不提交：`data/` 已被 git 忽略，由下面的下载命令重新生成。
完整清单、文件位置、字段和数据问题见 [`docs/raw_data.zh.md`](docs/raw_data.zh.md)。

| 编号 | 数据 | 提供者 | 粒度 | 硬盘上有 | 级别 |
|----|------|--------|------|----------|------|
| S1 | [交通探测器读数](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)（车速、车流、占用率） | 运输署 | 30 秒 × 车道 × 探测器（约 790 个） | 2024-01 至 2025-12 | 主要 |
| S2 | 交通探测器位置 | 运输署 | 每个探测器，8 个版本 | 2021-08 至 2026-04 | 主要 |
| S3 | [现时天气报告](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report)：各区过去一小时雨量 | 天文台 | 每小时 × 18 区 | 2024-01 至 2025-12 | 主要 |
| S4、S5 | [暴雨](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) / [热带气旋](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml)警告信号 | 天文台 | 每个信号 | 1998 / 1946 年至今 | 主要 |
| S6 | [公众假期](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) | 1823 | 每天 | 2018 至 2027 | 主要 |
| S8 | 天文台总部[逐日总雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) | 天文台 | 每天 | 1884 年至今 | 主要 |
| S9、S10 | [智能灯柱探测器](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts)：读数、位置 | 运输署 | 30 秒 × 车道 × 探测器（17 个） | 2024-01 至 2025-12 | 可选 |
| S11、N1 | 路段车速（运输署处理后）、路段 → 路线 | 运输署 | 约 1 分钟 × 路段（约 4,400 个） | 2024-01 至 2025-12 | 可选 |
| S12 | [第二代路网](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2)几何 | 运输署 | 每个版本（34 个） | 2024-01 至 2025-12 | 可选 |
| S13 | [特别交通消息](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2)（事故、封路） | 运输署 | 每条消息的每次更新 | 2024-01 至 2025-12 | 可选 |
| S7 | [格点雨量临近预报](https://data.gov.hk/en-data/dataset/hk-hko-rss-gridded-rainfall-nowcast-in-hong-kong)（雷达**预报**） | 天文台 | 15 分钟 × 约 2 公里网格 | 2024-01 至 2025-12 | 可选 |

气象站级别的逐小时雨量（`hourlyRainfall.php`）**不在**历史存档中，所以雨量按区对应到道路。

### 下载数据

```bash
pip install -r requirements.txt

# DATA.GOV.HK 历史存档，按 plan 下载（已有的文件会跳过；先显示大小并询问）
python -m hkdata.download run hkdata/plans/2024_2025_main.json --out data/raw          # 25.2 GB
python -m hkdata.download run hkdata/plans/2024_2025_optional.json --out data/raw      # 28.1 GB
python -m hkdata.download run hkdata/plans/road_network_2024_2025.json --out data/raw  #  0.6 GB

# 历史存档里没有的来源，或 plan 没有包含的版本（几秒钟）
python -m src.download warnings         # S4、S5
python -m src.download static           # S8、S2 实时副本
python -m src.download static-history   # S2、N1 的旧版本
python -m src.download holidays         # S6
```

`hkdata` 是本仓库里一个通用的 DATA.GOV.HK 工具库：`python -m hkdata.discover` 用来查找数据集、查看存档里有什么；
`python -m hkdata.download` 把 plan（哪些资源、哪些月份）转成对存档的请求。详见各模块的说明文字。

### 怎样访问历史存档

DATA.GOV.HK 资源的历史版本来自[历史存档 API](https://data.gov.hk/en/help/api-spec)：

```bash
# 列出一个文件在某段日期内的版本：返回 "timestamps" 和 "data-files"（月度 ZIP 打包文件）
curl -G "https://app.data.gov.hk/v1/historical-archive/list-file-versions" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "start=20250805&end=20250805"

# 一份快照（time = YYYYMMDD-HHMM）或整个打包文件（time = 打包文件的 YYYYMMDD 时间戳）
curl -L -G "https://app.data.gov.hk/v1/historical-archive/get-file" \
  --data-urlencode "url=https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml" \
  --data "time=20250805-0801" -o rawSpeedVol-20250805-0801.xml
```

交通数据的月度打包文件约 1 GB，一天的 XML 解压后约 670 MB。plan 把整个月度打包文件保存在
`data/raw/<网址主机>/<网址路径>/bundle/`，旁边是该资源的数据字典（`data-dictionary/`）。
`hkdata.download` 也可以用 HTTP 分段请求只取打包文件中的某几天。

## 数据处理流程

> **正在重写。** 本节描述的是之前的流程：它自己下载选定的日子，解析后删除 ZIP。
> 新流程将直接读取 `data/raw/` 里已有的月度打包文件（见"当前进度"）。

共四步。每一步都会跳过**用当前代码版本**已完成的工作，并重建旧版本生成的结果，所以中断或改代码后任何一步都可以重跑。
进度条显示已完成的天数和已下载的文件数。第 3 步之后，`src.validate` 会检查所有已处理的日子，
并给每张表做概况统计（NA、不同值的个数、最常见的值）；见 [`docs/processing.zh.md`](docs/processing.zh.md)。

```bash
pip install -r requirements.txt

# 1. 参考数据（几秒钟）
python -m src.download warnings     # 暴雨 + 台风信号 -> data/raw/hko/、data/interim/rainstorm_episodes.csv
python -m src.download static       # 探测器位置、路段表、天文台逐日雨量 -> data/raw/td/、data/raw/hko/
python -m src.download holidays     # 2018-2027 公众假期 -> data/raw/calendar/public_holidays.csv

# 2. 选日子 -> data/interim/day_manifest.csv
python -m src.download select-days --min-level R      # 红/黑雨事件 + 对照日：59 天（建议从这里开始）
python -m src.download select-days                    # 黄雨及以上：298 天

# 3. 按天下载 -> Parquet -> 删除 ZIP -> data/processed/{traffic_lane,rainfall_district}/
python -m src.pipeline --manifest                     # 或 --days 2025-08-05 ... / --range START END

# 4. 探测器 × 15 分钟表 -> data/processed/traffic_15min/
python -m src.aggregate --manifest

# 全面检查 -> data/processed/validation_report.md（第 3 步也会自动运行）
python -m src.validate --manifest
```

然后在 Python 里：

```python
from datetime import date
import pandas as pd
from src.data import load_traffic_lane, load_rainfall_district

lanes = load_traffic_lane([date(2025, 8, 5)])       # 约 360 万行：time, detector_id, lane, speed, occupancy, volume, sd, valid
rain = load_rainfall_district([date(2025, 8, 5)])   # 24 小时 × 18 区
t15 = pd.read_parquet("data/processed/traffic_15min/2025/20250805.parquet")
```

### 各步骤细节

**`select-days`** 的选项：`--years`（默认 `2022-2025`；2021 年到 11 月前只有 42 个探测器）、`--months`（默认 `4-10`）、
`--min-level` `A`/`R`/`B`（算作事件的最低警告级别）、`--pad-hours`（默认 3，每次事件前后各加几小时）、
`--controls`（默认 2）。对照日是事件日之前一或两周的同一星期几，且当天没有暴雨警告、也没有热带气旋信号。

| 设置（2022–2025，4–10 月） | 天数（事件 + 对照） | 下载量（用完删除） | 保留在硬盘上 | 耗时（第 3 步） |
|---|---|---|---|---|
| `--min-level B` | 20（9 + 11） | 约 0.6 GB | 约 0.2 GB | 约 10 分钟 |
| `--min-level R` | 59（28 + 31） | 约 1.8 GB | 约 0.7 GB | 约 25 分钟 |
| `--min-level A`（默认） | 298（129 + 169） | 约 9.2 GB | 约 3.3 GB | 约 2 小时 |

**`pipeline`** 在主进程里下载（每天 16 个线程，`--workers`），在 `--jobs` 个工作进程里解析（默认 3 个；
每个进程处理一天交通数据约需 1.6 GB 内存）。下载最多领先解析 `--jobs` 天，所以硬盘上同时只有几个 ZIP。
实测：`--jobs 3` 时每天交通数据约 24 秒（受下载速度限制），`--jobs 1` 时约 34 秒。`--keep-raw` 保留 ZIP。
每天的覆盖情况（快照数、行数、时段数、探测器数、修正日期的时段数、公告数、最大雨量、错误）写入
`data/processed/coverage.csv`。某天失败会记录在那里，然后继续处理其他日子。
之后 `src.validate` 写出 `data/processed/validation_report.md`，并列出每个 FAIL / WARN（`--no-validate` 跳过）。

**`aggregate`** 为每个探测器的每个 15 分钟时段写一行：读数计数（`n_readings`、`n_periods`、`n_invalid`、
`n_zero_volume`、`n_speed_over_130`）、`volume_sum`、`occupancy_mean`，以及两种车速，方便直接比较基本清洗规则的效果：
`speed_naive`（所有读数的简单平均）和 `speed_clean`（`valid == 'Y'` 且 `volume > 0` 的读数按车流加权平均）。
每天约 10 秒、约 0.9 MB。

如果只想要原始 XML，`python -m src.download fetch <sources> --days|--range|--manifest` 只下载 ZIP、不解析。

## 目前发现的数据问题

这些是预处理实验的素材。完整列表见
[`docs/database_description.zh.md`](docs/database_description.zh.md) 的"已知数据问题"一节。

- **探测器网络在扩大：** 42 个（2021 年 7 月）、554 个（2021 年 12 月）、约 680 个（2023 年）、770 个（2025 年）。
  位置表列出 807 个。
- **`s.d.` 约 2021 年 11 月 18 日起才有。**
- **快照时间 ≠ 测量时间：** 08:01 存档的文件里是 07:53:00–07:54:00 的数据。解析器用 `<period_from>`。
- **午夜日期问题：** 00:00 那个时段带的是前一天的 `<date>`。解析器用文件的存档时间修正（覆盖表中的 `n_periods_redated`）。
- **缺口：** 每天的快照数随月份变化（约 530–1,430）。2025 年 8 月 5 日 2,880 个 30 秒时段只有 1,730 个。
- **截断文件：** 少数存档的 XML 文件被截断（2025 年 7 月 29 日 919 份中有 1 份）。解析器保留截断前完整的读数，
  并统计这类文件（覆盖表中的 `n_truncated_files`）。
- **重叠：** 相邻快照会重复读数（约 9% 的行），打包文件有时把同一个文件存两次。两者都会去重。
- **车速填充值：** `volume = 0` 时（约 28% 的读数），`speed` 是道路限速（70/80/100/50/110，s.d. = 0），不是测量值。
- **超出范围的值：** 车速最高 300 km/h、occupancy = −1、车速为 0 但车流 > 0；约 0.5% 的读数 `valid = N`。
- **名称：** 探测器表里同时有 `Central & Western` 和 `Central and Western`，大多数道路名末尾有多余空格。
  天文台写 `Southern District`，运输署写 `Southern`。
- **雨量是每区的最小–最大范围。** 公告里没列出的区就是没下雨。没有雨量那句话的公告表示全港都没下雨。
  雨量所属的小时是句子里写的那个时段（例如 06:45–07:45），不是公告开头 "At 8 a.m." 的时间。
- **警告数据库：** 有 `24:00` 这种结束时间；`UUUU` 之后的行是临时记录。
- **所有时间都是香港时间（UTC+8）**，存储时不带时区。

### 重点时段

2025 年有四次黑雨事件，是现行制度下首次在一年内出现四次（[arXiv:2508.07600](https://arxiv.org/pdf/2508.07600)）。
其他值得关注的事件：[2023 年 9 月 7–8 日破纪录暴雨](https://en.wikipedia.org/wiki/2023_Hong_Kong_rainstorm_and_floods)，
以及 2025 年 8 月 4–5 日的黑雨。

## 仓库结构

```
.
├── README(.zh).md, PROPOSAL.md, requirements.txt
├── docs/               # raw_data(.zh).md, processing(.zh).md, database_description(.zh).md, data_sources_notes.md
├── hkdata/             # 通用 DATA.GOV.HK 工具库：discover（搜索、存档覆盖情况）、download（按 plan 下载）
│   └── plans/          # data/raw 用到的下载 plan
├── src/
│   ├── download/       # 第 1-2 步（及 fetch）：存档客户端、警告、静态文件、假期、选日子
│   ├── parse/          # 交通 XML 和天气公告 -> 表
│   ├── pipeline.py     # 第 3 步：下载 -> Parquet -> 删除 ZIP，并行，带进度条
│   ├── aggregate.py    # 第 4 步：探测器 × 15 分钟表
│   ├── validate.py     # 检查所有表并做概况统计 -> validation_report.md
│   ├── storage.py      # 记录生成代码版本的 Parquet 文件
│   ├── data.py         # 读取处理后的表
│   └── config.py       # 路径和数据来源网址
├── tests/
├── data/               # git 忽略；raw/ 由下载命令生成，interim/ 和 processed/ 由处理流程生成
├── notebooks/          # 探索性分析和实验报告（待定）
└── results/            # 图表（待定）
```

## 许可与出处

代码：MIT（待定）。数据：© 香港特区政府运输署及香港天文台，按
[DATA.GOV.HK 条款及细则](https://data.gov.hk/en/terms-and-conditions)使用。
天文台注明自动气象站雨量是临时数据，与官方气候记录不同。我们会注明每个数字用的是哪个来源。
