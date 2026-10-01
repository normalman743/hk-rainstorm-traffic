# hk-rainstorm-traffic

> 本文是 [`README.md`](README.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

香港哪些道路对暴雨最敏感？把天文台的雨量和警告数据与运输署的交通探测器数据整合起来，研究预处理和特征工程如何影响拥堵预测。

> 课程项目。重点是**数据预处理与整合**：每一个主要的清洗 / 聚合 / 匹配决定都当作实验变量，
> 衡量它如何改变后续结果。
>
> **报告草稿（IEEE 格式，PDF）：[`report/main.pdf`](report/main.pdf)。**
> **后续研究数据**（整个 `data/` 文件夹，约 13 GB，截至 2026-10-01）：[Google Drive](https://drive.google.com/drive/folders/1PbwMZtaP58idOqs0kwuPo_p8RRdwfTlG?usp=sharing)；
> 每个文件夹的内容和放置位置见 [`docs/findings_and_next.md`](docs/findings_and_next.md) 第 5 节。
> 研究计划：[`docs/PROPOSAL.md`](docs/PROPOSAL.md)。目前的发现与后续工作：
> [`docs/findings_and_next.md`](docs/findings_and_next.md)。清洗规则：
> [`docs/cleaning.md`](docs/cleaning.md)。另见
> [`docs/raw_data.zh.md`](docs/raw_data.zh.md)（每个原始数据来源和字段）、
> [`docs/processing.zh.md`](docs/processing.zh.md)（每个处理步骤做什么）和
> [`docs/database_description.zh.md`](docs/database_description.zh.md)（处理后的表）。

## 当前进度（2026-10-01）

- **数据：已齐全。** 分析需要的所有来源，加上可选的扩展数据，都已下载了 2024-01 至 2025-12
  （原始月度打包文件约 53 GB），每个都配有官方数据字典。
  清单见 [`docs/raw_data.zh.md`](docs/raw_data.zh.md) 的"数据清单"一节。
- **流程：三个月已端到端跑通**（2024-05、2025-07、2025-08；主要来源 S1–S6、S8）：
  L1 → L2（按来源清洗）→ L3（探测器 × 15 分钟分析表）→ EDA、RQ1、RQ2、RQ3。
  报告草稿（[`report/main.pdf`](report/main.pdf)，6 页）由这些结果写成。
- **下一步：** 审核 [`docs/cleaning.md`](docs/cleaning.md) 中标为 "pending review" 的决定，
  验证各个假设（S13 交通消息、逐次黑雨分析）；见
  [`docs/findings_and_next.md`](docs/findings_and_next.md)。

## 研究问题

1. **敏感性：** 控制时段和星期几之后，暴雨期间哪些路段的车速下降 / 占用率上升最大？
2. **预测：** 道路属性加上雨量特征，能否比只用时间的基线模型更好地预测暴雨期间的拥堵？
3. **预处理的影响：** 离群值处理、聚合时间窗、雨量与道路的匹配方式、警告编码方式等选择，会在多大程度上改变问题 1 和问题 2 的答案？

## 数据来源

全部是免费的香港政府公开数据。大文件都不提交：`data/` 已被 git 忽略，由下面的下载命令重新生成，或从 [Google Drive 上的后续研究数据](https://drive.google.com/drive/folders/1PbwMZtaP58idOqs0kwuPo_p8RRdwfTlG?usp=sharing)获取（三个月的原始文件、L1、L2、L3）。
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

# 需要重新下载存档时，另行安装独立的下载工具。
python -m pip install "git+https://github.com/normalman743/hkgovdata.git"

# DATA.GOV.HK 历史存档，按 plan 下载（已有的文件会跳过；先显示大小并询问）
python -m hkgovdata.download run plans/2024_2025_main.json --out data/raw          # 25.2 GB
python -m hkgovdata.download run plans/2024_2025_optional.json --out data/raw      # 28.1 GB
python -m hkgovdata.download run plans/road_network_2024_2025.json --out data/raw  #  0.6 GB

# 历史存档里没有的来源，或 plan 没有包含的版本（几秒钟）
python -m src.download warnings         # S4、S5
python -m src.download static           # S8、S2 实时副本
python -m src.download static-history   # S2、S14 的旧版本
python -m src.download holidays         # S6
```

[`hkgovdata`](https://github.com/normalman743/hkgovdata) 是独立的 DATA.GOV.HK 工具：
`python -m hkgovdata.discover` 用来查找数据集、查看存档覆盖情况；
`python -m hkgovdata.download` 按 plan 下载。本课程仓库保留自己的 `plans/`。
清洗和分析直接读取 `data/raw/`，不要求安装下载工具。本地的 `hkgovdata/` 独立仓库
被外层 Git 忽略；开发工具时可执行 `python -m pip install -e ./hkgovdata`。

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
`hkgovdata.download` 也可以用 HTTP 分段请求只取打包文件中的某几天。

## 数据处理

分层：**L1** 是原始文件的原样内容，存为 Parquet：所有值都是字符串，元素不存在记为 null，元素为空记为 `""`。
**L2**（清洗；已定的规则和待定的问题见 [`docs/cleaning.md`](docs/cleaning.md)）给每个主要来源定类型并清洗，每条规则都记录了处理数量。
**L3** 是分析表，每个探测器每 15 分钟一行，带本区雨量、警告等级和干燥天气基线；每个预处理步骤
（[`docs/PROPOSAL.md`](docs/PROPOSAL.md) 中的 P1–P11）都有默认做法和供 RQ3 比较的备选。
之前按天处理的流程已于 2026-09-29 删除，该日期之前的 git 历史里还能找到。

从 `data/raw/` 里的月度打包文件生成 L1（月份任意；解析程序只处理 manifest 里登记的月份）：

```bash
export PYTHONPATH=.
# 第 1、2 步一条命令做完（哪一步出错就停在哪一步）：
python -m src.clean.l1 202405 202507 202508

# 1. manifest：登记这些月份打包文件里的每个文件；字节完全相同的副本只解析一次。
#    新旧月份要一起写上：manifest 和 checks/*.csv 会整张重写。
python -m src.clean.manifest 202405 202507 202508

# 2. 解析 -> data/interim/l1/<来源>/<年月或版本>.parquet
python -m src.clean.s1_periods --source s1 && python -m src.clean.s1_parse --source s1  # S1 探测器读数
python -m src.clean.s1_periods --source s9 && python -m src.clean.s1_parse --source s9  # S9 灯柱读数
python -m src.clean.s3_parse          # S3 天气公报
python -m src.clean.s13_parse         # S13 交通消息
python -m src.clean.s11_parse         # S11 路段车速
python -m src.clean.s7_parse          # S7 雨量临近预报
python -m src.clean.s12_parse         # S12 路网，所有图层（几何保留 Z / M）
python -m src.clean.versions_parse    # S2 / S10 / S14 的所有版本
python -m src.clean.s6_parse          # S6 公众假期的所有版本
python -m src.clean.signals_parse     # S4 暴雨警告 / S5 热带气旋信号
python -m src.clean.s8_parse          # S8 每日雨量

# 3. 检查（可选，生成 L1 不需要）-> data/interim/checks/
python -m src.clean.s1_rows --source s1 && python -m src.clean.s1_rows --source s9
python -m src.clean.s3_checks && python -m src.clean.s13_checks && python -m src.clean.s11_checks
python -m src.clean.s7_checks && python -m src.clean.versions_checks
python -m src.clean.structure         # S4 S5 S6 S8 S12：预设格式对照实际数据，列出所有例外
```

L2、L3、分析和报告（在 L1 之后；所需的包见 `requirements.txt`，报告需要装有 `latexmk` 的 LaTeX）：

```bash
# 4. L2 -> data/interim/l2/，处理数量写到 data/interim/checks/
python -m src.clean.l2_s1 202405 202507 202508   # S1 读数，每月一个 Parquet
python -m src.clean.l2_s3                          # S3 每小时每区雨量
python -m src.clean.l2_ref                         # S2 探测器、S4 / S5 信号、S6 假期、S8 每日雨量

# 5. L3 -> data/interim/l3/<名称>.parquet
python -m src.l3                                   # 默认表
python -m src.l3 speed_agg=mean                    # 变体：任意 选项=值（RQ3）

# 6. 分析 -> report/figures/*.pdf、report/results/*.json|csv
python -m src.analysis.eda
python -m src.analysis.rq1
python -m src.analysis.rq2
python -m src.analysis.rq3                         # 会补建缺少的 L3 变体；约 40 分钟

# 7. 报告 -> report/main.pdf
cd report && latexmk -pdf main.tex
```

解析程序遇到不认识的内容（新的元素、表头或文件格式）会直接报错，不会跳过：先看是什么情况，再决定怎么处理。
每个解析程序保留什么、跳过什么，写在各自的 docstring 里；发现的问题见
[`docs/raw_data.zh.md`](docs/raw_data.zh.md)。

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
├── README.md, README.zh.md      # 本文件（英文 / 中文）
├── requirements.txt             # Python 包（下载、L1、L2、L3、分析、测试）
├── docs/
│   ├── PROPOSAL.md              # 研究计划，按第一批结果重写（2026-10-01）
│   ├── findings_and_next.md     # 目前的发现，以及接下来必须做 / 可以做的事（中文）
│   ├── cleaning.md              # 每条 L2 规则（D1–D22）的证据、决定人和处理数量；待定问题；L3 选项
│   ├── raw_data(.zh).md         # 每个原始来源的发布形式：获取方式、字段、取值、发现的问题
│   ├── processing(.zh).md       # 原始来源怎样变成表：L1、L2、L3、分析、src.download
│   ├── database_description(.zh).md  # 来源、表及其关联；已知数据问题
│   ├── data_sources_notes.md    # 在用的来源与仅供参考的来源
│   └── course_project.md        # 课程的项目要求（从 Canvas 复制）
├── plans/                       # hkgovdata 的存档下载 plan（主要、可选、路网）
├── src/
│   ├── config.py                # 路径和数据来源网址
│   ├── download/                # plan 之外的来源
│   │   ├── __main__.py          # 命令行：warnings、static、static-history、holidays、select-days
│   │   ├── archive.py           # DATA.GOV.HK 历史存档客户端
│   │   ├── warnings.py          # 天文台暴雨 / 热带气旋数据库 -> CSV（S4、S5）
│   │   ├── static.py            # 探测器位置、每日雨量（S2、S8）
│   │   ├── holidays.py          # 公众假期，合并所有存档版本（S6）
│   │   └── select_days.py       # 选事件日和对照日（可选）
│   ├── clean/                   # L1（原样）和 L2（清洗后）
│   │   ├── l1.py                # 一条命令做完 L1：manifest，然后所有解析程序
│   │   ├── manifest.py          # 列出月度打包文件中的每个文件，字节相同的副本归为一组
│   │   ├── files.py             # 从打包文件中读取快照文件
│   │   ├── s1_periods.py        # 每个 S1 / S9 文件包含哪些 30 秒时段；缺失和重复的时段
│   │   ├── s1_parse.py          # S1 / S9 的 L1：每条车道读数
│   │   ├── s1_rows.py           # S1 / S9 行级检查（重复键、空值、格式）
│   │   ├── s3_parse.py, s3_checks.py        # S3 天气公报和各区雨量：L1、检查
│   │   ├── signals_parse.py     # S4 / S5 警告信号的 L1
│   │   ├── s6_parse.py          # S6 假期的 L1，所有版本
│   │   ├── s8_parse.py          # S8 每日雨量的 L1
│   │   ├── versions_parse.py, versions_checks.py  # S2 / S10 / S14 所有版本：L1、检查
│   │   ├── s7_parse.py, s7_checks.py        # S7 雨量临近预报（可选）：L1、检查
│   │   ├── s11_parse.py, s11_checks.py      # S11 路段车速（可选）：L1、检查
│   │   ├── s12_parse.py         # S12 路网（可选）的 L1，所有图层
│   │   ├── s13_parse.py, s13_checks.py      # S13 交通消息（可选）：L1、检查
│   │   ├── structure.py         # L1 的值对照预设格式（S4 S5 S6 S8 S12）
│   │   ├── l2_s1.py             # S1 的 L2：定类型，D3–D6、D12–D14、D16、D21；每月一个 Parquet
│   │   ├── l2_s3.py             # S3 的 L2：每小时每区雨量，无缺口（D8–D10）
│   │   └── l2_ref.py            # S2 / S4 / S5 / S6 / S8 的 L2（D2、D3、D11、D17–D20、D22）
│   ├── l3.py                    # L3 分析表（探测器 × 时段）及 P1–P11 选项
│   └── analysis/
│       ├── common.py            # 输出目录、L3 连接、标签、绘图样式
│       ├── eda.py               # 覆盖率、事件、车速 / 车流与雨量和警告的关系、2025-08-05
│       ├── rq1.py               # RQ1：每个探测器和每区的敏感度、暴露量、稳定性、地图
│       ├── rq2.py               # RQ2：按事件留出的预测（基线、线性模型、LightGBM）
│       └── rq3.py               # RQ3：消融实验，每次只换一个预处理备选
├── tests/
│   ├── test_download.py         # src.download 的测试
│   └── test_clean.py            # L1 / L2 / L3 规则的测试
├── report/
│   ├── main.tex, refs.bib       # 报告源文件（IEEEtran）
│   ├── main.pdf                 # 编译好的报告
│   ├── figures/                 # src.analysis 生成的图（eda_*、rq1_*、rq2_*、rq3_*）
│   └── results/                 # src.analysis 生成的数字（eda / rq1 / rq2 / rq3 的 .json、.csv）
├── data/                        # git 忽略：raw/（下载）、interim/（l1、l2、l3、manifest、checks）
└── hkgovdata/                   # 可选的独立本地仓库，外层 Git 忽略
```

## 许可与出处

代码：MIT（待定）。数据：© 香港特区政府运输署及香港天文台，按
[DATA.GOV.HK 条款及细则](https://data.gov.hk/en/terms-and-conditions)使用。
天文台注明自动气象站雨量是临时数据，与官方气候记录不同。我们会注明每个数字用的是哪个来源。
