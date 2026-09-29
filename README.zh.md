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
  之前按天处理的流程已删除（见"数据处理"一节）。

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
| S11、S14 | 路段车速（运输署处理后）、路段 → 路线 | 运输署 | 约 1 分钟 × 路段（约 4,400 个） | 2024-01 至 2025-12 | 可选 |
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
python -m src.download static-history   # S2、S14 的旧版本
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

## 数据处理

**正在重写。** 之前的流程（下载选定的日子 → 解析 → Parquet → 删除 ZIP，另有探测器 × 15 分钟表和数据检查）
已于 2026-09-29 连同其输出一起删除；该日期之前的 git 历史里还能找到。新流程将读取 `data/raw/` 里已有的月度打包文件。
`src.download` 自己生成的内容（警告信号、暴雨事件、假期，以及可选的选日子 `select-days`）见
[`docs/processing.zh.md`](docs/processing.zh.md)。

## 目前发现的数据问题

这些是预处理实验的素材。完整列表见
[`docs/database_description.zh.md`](docs/database_description.zh.md) 的"已知数据问题"一节。

- **探测器网络在扩大：** 42 个（2021 年 7 月）、554 个（2021 年 12 月）、约 680 个（2023 年）、770 个（2025 年）。
  位置表列出 807 个。
- **`s.d.` 约 2021 年 11 月 18 日起才有。**
- **快照时间 ≠ 测量时间：** 08:01 存档的文件里是 07:53:00–07:54:00 的数据；测量时间是 `<period_from>`。
- **午夜日期问题：** 00:00 那个时段带的是前一天的 `<date>`；文件的存档时间能看出真正的日期。
- **缺口：** 每天的快照数随月份变化（约 530–1,430）。2025 年 8 月 5 日 2,880 个 30 秒时段只有 1,730 个。
- **截断文件：** 少数存档的 XML 文件被截断（2025 年 7 月 29 日 919 份中有 1 份）。
- **重叠：** 相邻快照会重复读数（约 9% 的行），打包文件有时把同一个文件存两次。
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
├── docs/               # raw_data(.zh).md, processing(.zh).md, database_description(.zh).md, data_sources_notes.md, course_project.md
├── hkdata/             # 通用 DATA.GOV.HK 工具库：discover（搜索、存档覆盖情况）、download（按 plan 下载）
│   └── plans/          # data/raw 用到的下载 plan
├── src/
│   ├── download/       # plan 之外的来源：警告、静态文件、假期；选日子；fetch
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
