# 原始数据字典

> 本文是 [`raw_data.md`](raw_data.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

本文档说明每个**原始**数据来源在发布时的样子：来自哪里、怎样获取、格式和结构、每个字段的含义、
实际出现哪些取值，以及检查真实数据时发现的问题。处理后的表格见
[`processing.zh.md`](processing.zh.md) 和 [`database_description.md`](database_description.md)。

文中标为"实测"的数字，来自 2026 年 9 月对真实数据的只读审计。除特别说明外，交通数据用的是 2025 年 8 月 5 日（黑雨当天）。

除特别说明外，所有时间均为**香港时间（HKT，UTC+8）**。

## 数据清单（硬盘上，2026-09-29）

以下都在 `data/raw/` 下。**主要** = 核心分析要用；**可选** = 扩展分析（路段车速、智能灯柱、交通事故、雷达预报）。

| 编号 | 数据 | 提供者 | 时间粒度 | 空间单位 | 硬盘上有 | 大小 | 级别 |
|----|------|--------|----------|----------|----------|------|------|
| S1 | 交通探测器读数（车速、车流、占用率） | 运输署 | 30 秒时段 | 车道 × 探测器（约 790 个） | 2024-01 至 2025-12，月度打包 | 23 GB | 主要 |
| S2 | 交通探测器位置 | 运输署 | 按版本 | 探测器 | 2021-08 至 2026-04，8 个版本 | 0.3 MB | 主要 |
| S3 | 现时天气报告（分区雨量） | 天文台 | 每小时 | 18 区（最小–最大毫米） | 2024-01 至 2025-12，月度打包 | 28 MB | 主要 |
| S4 | 暴雨警告信号 | 天文台 | 每个信号 | 全港 | 1998-04 至 2026-08 | 37 kB | 主要 |
| S5 | 热带气旋警告信号 | 天文台 | 每个信号 | 全港 | 1946 至 2026-09 | 136 kB | 主要 |
| S6 | 公众假期 | 1823 | 每天 | 全港 | 2018 至 2027（合并） | 8 kB | 主要 |
| S8 | 逐日总雨量 | 天文台 | 每天 | 1 个站（天文台总部） | 1884-03 至 2026-08 | 0.8 MB | 主要 |
| S9 | 智能灯柱探测器读数 | 运输署 | 30 秒时段 | 车道 × 探测器（17 个有数据） | 2024-01 至 2025-12，月度打包 | 0.9 GB | 可选 |
| S10 | 智能灯柱探测器位置 | 运输署 | 按版本 | 探测器 | 2023-12、2024-01 | 8 kB | 可选 |
| S11 | 路段车速（运输署处理后） | 运输署 | 约 1 分钟一份 | 路段（约 4,400 个） | 2024-01 至 2025-12，月度打包 | 13 GB | 可选 |
| S14 | 路段 → 路线编号 | 运输署 | 按版本 | 路段 | 2021-08 至 2023-09，6 个版本 | 0.2 MB | 可选 |
| S12 | 路网几何（FGDB） | 运输署 | 按版本（2024–25 年共 34 个） | 道路中心线（35,837 条） | 2024-01 至 2025-12，月度打包 | 0.6 GB | 可选 |
| S13 | 特别交通消息（事故、封路） | 运输署 | 每条消息的每次更新 | 位置文字；部分有区和经纬度 | 2024-01 至 2025-12，月度打包 | 61 MB | 可选 |
| S7 | 格点雨量临近预报（雷达**预报**） | 天文台 | 每 15 分钟，预报 +30 至 +120 分钟 | 约 2 公里网格，121 × 121 | 2024-01 至 2025-12，月度打包 | 12 GB | 可选 |

编号：**S** = 使用的来源；**N** = 拿不到或不使用的来源。（S14 在 2026-09-29 之前叫 N1，因为 S11 要用它而改名。）

2026-09-30 起，S1、S7、S9、S11 在硬盘上只保留三个月：2024-05、2025-07、2025-08，也就是先处理的这三个月
（分别为 3.1、1.8、0.1、1.7 GB）。其余 21 个月的打包文件（共 46.5 GB）已删除，可以用下面的 plan 重新下载；
删除清单在 `data/interim/deleted_bundles.txt`。

拿不到历史数据的：N2 自动气象站逐小时雨量，以及天文台 JSON 版的现时天气报告（`weather.php?dataType=rhrread`），两者都不在历史存档中。

### 文件放在哪里、由谁下载

按数据来源分两个下载工具：

**`hkdata.download`（DATA.GOV.HK 历史存档）**：S1、S2（3 个版本）、S3、S7、S9–S14（S14：1 个版本）。
按 `hkdata/plans/` 里的 plan 下载；目录结构为 `data/raw/<网址主机>/<网址路径>/`：

| Plan | 内容 | 大小 |
|------|------|------|
| `2024_2025_main.json` | S1、S3、S13、S2（2022-03、2024-02、2025-10）、S14（2023-09） | 25.2 GB |
| `2024_2025_optional.json` | S11、S9、S7、S10 | 28.1 GB |
| `road_network_2024_2025.json` | S12 | 0.6 GB |

```bash
python -m hkdata.download run hkdata/plans/2024_2025_main.json --out data/raw
```

```
<网址主机>/<网址路径>/bundle/<YYYYMMDD>.zip          存档的月度打包文件，原样保存
<网址主机>/<网址路径>/data-dictionary/<日期>/<文件名>  存档的数据字典各版本
<网址主机>/<网址路径>/schema/<日期>/<文件名>           存档的结构定义各版本（只有 S13 有）
```

打包文件里每个成员的名字是 `<URL 编码的目录>/<YYYYMMDD-HHMM>-<文件名>`，即一份快照的存档时间。
每个打包文件还附带一个约 3 kB 的 `<日期>-0000-data-dictionary.pdf`，里面只有一句"请用 get-data-dictionary 获取"；
真正的数据字典在 `data-dictionary/` 里。

**`src.download`（旧的下载工具）**：历史存档里没有的数据，或 plan 没有包含的版本：

| 命令 | 写入 | 数据 |
|------|------|------|
| `warnings` | `hko/rstorm.dat`、`hko/tc.dat`（及解析后的 `rainstorm_warnings.csv`、`tc_signals.csv`） | S4、S5（不在 DATA.GOV.HK 上） |
| `static` | `hko/daily_HKO_RF_ALL.csv`、`td/traffic_speed_volume_occ_info.csv` | S8；S2 实时副本（与其 2026-04 版本相同） |
| `static-history` | `td/traffic_speed_volume_occ_info/<YYYYMMDD>.csv`、`td/speed_segments_info/<YYYYMMDD>.csv` | S2 的 2021-08 至 2021-12 和 2026-04 版本；S14 的 2021-08 至 2022-10 版本 |
| `holidays` | `calendar/public_holidays.csv` | S6（所有存档版本合并） |

两边都有的版本已逐字节核对，`src.download` 的副本已删除。
这些数据的数据字典是手动存进 `hko/data-dictionary/`、`calendar/data-dictionary/` 和 `td/data-dictionary/` 的（见"数据字典"一节）。

---

## 历史文件怎样获取

S1 和 S3 的实时网址永远只返回**最新**的文件。过去的版本要从
[DATA.GOV.HK 历史存档 API](https://data.gov.hk/en/help/api-spec) 获取：

| 接口 | 参数 | 返回 |
|----------|------------|---------|
| `https://app.data.gov.hk/v1/historical-archive/list-file-versions` | `url`（实时网址）、`start`、`end`（`YYYYMMDD`） | JSON：`timestamps`（每个存档版本一个，格式 `YYYYMMDD-HHMM`）、`data-files`（ZIP 打包文件，通常每月一个）、`data-dictionary-dates` |
| `https://app.data.gov.hk/v1/historical-archive/get-file` | `url`、`time` | HTTP 302 跳转到文件。`time=YYYYMMDD-HHMM` 取一份快照；`time=YYYYMMDD`（打包文件的时间戳）取整个打包 ZIP |
| `https://app.data.gov.hk/v1/historical-archive/get-data-dictionary` | `url`、`date` | HTTP 302 跳转到 `date` 当天生效的数据字典（该日或之前最新的版本） |
| `https://app.data.gov.hk/v1/historical-archive/get-schema` | `url`、`date` | 同上，取结构定义（例如 XSD） |

交通数据的打包文件每月约 1 GB。包内文件名为
`<URL 编码后的实时网址>/<YYYYMMDD-HHMM>-rawSpeedVol-all.xml`。`hkdata.download` 保存整个月度打包文件
（见"数据清单"一节），也可以用 HTTP 分段请求只取打包文件中某几天的文件。各接口在测试中的实际回应记录在它的模块说明里。

**存档时间 ≠ 测量时间。** 版本的时间戳是存档系统抓取文件的时间，不是数据的测量时间（见 S1 和 S3）。

---

## 数据字典

每个数据来源旁边都有官方数据字典，放在 `data-dictionary/` 文件夹里（文件名保留存档的 `<日期>-` 前缀）。
2024–2025 年间字典有改动的，保留了多个版本。很多版本提取文字后完全相同，下表列出内容不同的版本。

| 来源 | 数据字典（在 `data/raw/` 下） | 不同的内容 |
|------|------------------------------|------------|
| S1、S2、S11、S14 | 各资源文件夹及 `td/data-dictionary/` 里的 `dataspec-traffic-data-strategic-major-roads.pdf`（20210812、20211118、20240418） | 20211118 → 20240418（最后更新 2022 年 11 月 30 日）：只改了措辞（`valid`、占用率定义），结构不变 |
| S9、S10 | `dataspec-traffic-data-slp.pdf`（20231228、20240418） | 一种：XML 结构与 S1 相同 |
| S3 | `HKO_Open_Data_API_Documentation.pdf`（11 个版本） | 三种；它说明的是 JSON API，**不是我们用的 RSS 文件** |
| S4、S5 | `hko/data-dictionary/hko-webpage-warndb3.shtml.html`、`…warndb1.shtml.html` | **没有官方数据字典**：保存的是天文台数据库网页（2026-09-29），里面有临时记录、信号编号沿革等说明 |
| S6 | `calendar/data-dictionary/…-1823_cal_dictionary.pdf`（4 个版本） | – |
| S7 | `HKO_gridded_rainfall_nowcast_documentation.pdf`（6 个版本） | 一种 |
| S8 | `hko/data-dictionary/20250227-data_dictionary_daily_total_rainfall.pdf` | – |
| S12 | `rdnet_dataspec.zip`（5 个版本）：FGDB、GML、KML 各一份 PDF | – |
| S13 | `Data_Specification_for_STN_Eng_v4.0.pdf`（2 个版本）+ `schema/20210608/20210608-trafficnews.xsd` | 一种 |

阅读时发现：

| 发现 | 详情 |
|------|------|
| `valid` = 探测器在线 / 离线 | S1/S9：2022 年的字典把 `Y` 定义为 "Detector Online"、`N` 为 "Detector Offline"（2021 年写的是 "valid / non-valid"） |
| 字典里的列名 ≠ 文件 | S2 字典写 `Device_ID`，文件里是 `AID_ID_Number`；S14 字典写 `segment_id`、`road name`，文件里是 `irn_id`、`ucase(route)`。以文件为准 |
| S3 格式没有文档 | RSS 公告是自由文字；我们的解析器遇到任何意外都会直接报错（见 S3） |
| 存档里有截断的字典文件 | 6 个版本缺少 PDF 结尾标记 `%%EOF`（天文台 API 文档 20240921、20241022、20241116、20250311；格点临近预报 20240921、20241010）；第二天的版本是完整的 |
| 存档链接损坏 | 字典版本 20221214（运输署主要道路）和 20240229（天文台 API）跳转到存储服务器上不存在的文件（404），所以硬盘上没有；S14 改为保存 20211118 和 20240418 |

---

## S1. 交通探测器读数（`rawSpeedVol-all.xml`）

| | |
|---|---|
| 数据集 | [主要干道及道路交通数据](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)，资源 "Traffic Speed, Volume and Road Occupancy (Raw Data)" |
| 实时网址 | `https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml` |
| 结构定义 | [`SpeedVolOcc-BR.xsd`](https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/SpeedVolOcc-BR.xsd) |
| 发布频率 | 每分钟一次；每个文件含**两个 30 秒时段** |
| 存档 | **2021 年 6 月**起。每天的快照数随月份变化，约 530–1,430 份（例如 2025 年 8 月 5 日有 946 份） |
| 大小 | 每个文件约 710 kB；每天解压后约 670 MB，压缩后约 31 MB |
| 探测器数量 | 42（2021 年 7 月）、554（2021 年 12 月）、约 680（2023 年）、770（2025 年） |

### 结构

```xml
<raw_speed_volume_list>
  <date>2025-08-05</date>
  <periods>
    <period>
      <period_from>07:53:00</period_from><period_to>07:53:30</period_to>
      <detectors>
        <detector>
          <detector_id>AID01101</detector_id>
          <direction>South East</direction>
          <lanes>
            <lane>
              <lane_id>Middle Lane</lane_id>
              <speed>43</speed><occupancy>1</occupancy><volume>2</volume>
              <s.d.>5.7</s.d.><valid>Y</valid>
            </lane>
            ... 每条车道一个 <lane> ...
          </lanes>
        </detector>
        ... 约 770 个探测器 ...
      </detectors>
    </period>
    <period> ... 下一个 30 秒 ... </period>
  </periods>
</raw_speed_volume_list>
```

一条读数 = 一个探测器的一条车道在一个 30 秒时段内的数据。每个文件约 4,200 条读数。

### 字段

| 层级 | 字段 | 类型 | 单位 | 官方说明（XSD 原文） | 含义与实测取值 |
|-------|-------|------|------|----------------------------|-----------------------------|
| 文件 | `date` | 日期 | – | Date of the data | 测量日期。**00:00 那个时段的日期是错的**（见下方数据问题） |
| 时段 | `period_from` | 时间 | – | Timestamp of data period starts | 30 秒时段的开始时间，`HH:MM:00` 或 `HH:MM:30` |
| 时段 | `period_to` | 时间 | – | Timestamp of data period ends | 永远是 `period_from` + 30 秒（冗余字段） |
| 探测器 | `detector_id` | 字符串 | – | Reference ID for AID | 例如 `AID01101`、`TDS90070`、`TDSIEC10001`。对应 S2 的 `AID_ID_Number` |
| 探测器 | `direction` | 字符串 | – | Direction of AID | 例如 `South East`；与 S2 的 `Direction` 相同 |
| 车道 | `lane_id` | 字符串 | – | Reference ID for Lane of AID | 7 种：`Fast Lane` 快线（37%）、`Slow Lane` 慢线（35%）、`Middle Lane` 中线（20%），以及宽路上的 `Middle Lane 1`–`4` |
| 车道 | `speed` | 整数 | km/h | Average speed of lane | 平均车速。0–300，中位数 70。**`volume = 0` 时是填充值**（见下方数据问题） |
| 车道 | `occupancy` | 整数 | % | Occupancy of lane | 占用率：时段内有车压在探测器上的时间比例。0–100；37% 的读数是 0；另有 `-1` |
| 车道 | `volume` | 整数 | 辆/30 秒 | – | 车流量。0–61；27.7% 的读数是 0 |
| 车道 | `s.d.` | 小数 | km/h | – | 车速标准差；55% 是 0（没有车或只有一辆车）。**约 2021 年 11 月 18 日之前没有这个字段** |
| 车道 | `valid` | `Y`/`N` | – | Data validity：Detector Online `Y`，Detector Offline `N`（数据字典，2022 年） | 探测器在线 / 离线；0.5% 的读数为 `N`。`N` 的读数数值看起来都正常，只能靠这个标记识别 |

### 数据问题（实测）

| 问题 | 证据 | 影响 |
|-------|----------|-------------|
| 存档时间 ≠ 测量时间 | 08:01 存档的文件里是 07:53:00–07:54:00 的数据（延迟约 5–10 分钟） | 用 `period_from` 定时间，不能用文件名 |
| 时段缺失 | 2025 年 8 月 5 日每天 2,880 个时段只有 1,730 个（约 40% 缺失）。检查过的三个月里，缺失比例为 27.0%（2024-05）、46.6%（2025-07）、41.0%（2025-08）；最长的连续缺失是 35 分钟（2024-05-30），2025 年最多 10 分钟。每个不同的文件都正好有两个时段，所以缺的时段就是存档没有抓取的那些分钟 | 缺失表现为**这一行不存在**，而不是 NA |
| 相同副本 | 存档经常在两个或更多抓取时间存下同一个文件（例如 2025 年 8 月 5 日的 00:07 和 00:10）：2024-05 在 32,718 个成员中有 113 个多余副本，2025-07 为 26,101 个中 2,261 个，2025-08 为 28,445 个中 2,096 个。同一个成员名也会出现两次（三个月分别 30 / 6 / 43 个名字），内容总是完全相同 | 每组相同文件只读一份（`src.clean.manifest`）；文件名保留全部抓取时间 |
| 不同文件之间没有重叠 | 把相同副本归组后，每个 30 秒时段只出现在一个文件里（三个月都是如此），下面的截断文件除外。2025 年 8 月 5 日看到的约 9% 重复行来自相同副本，而不是文件互相重叠 | 不需要按（时间，探测器，车道）去重 |
| 午夜日期错误 | 00:00 那个时段带的是**前一天**的 `<date>`：三个月里含 00:00:00 和 00:00:30 的 83 个文件（抓取时间 00:06–00:10）全部写的是前一天 | 用存档时间修正日期 |
| 截断文件 | 少数文件在中途被截断：三个月里有 3 个（抓取于 2025-07-17 14:18、2025-07-29 10:28、2025-08-11 02:00）。每个都正好断在 393,216 或 196,608 字节（384 / 192 KiB），并且和相隔 1–3 分钟抓取的一个完整文件的开头逐字节相同 | 跳过这些文件 |
| 同一车道出现两次 | TDS90026 在 2025-07 和 2025-08 几乎每个文件里（49,590 个）都列出两条叫 `Middle Lane` 的车道（方向 `West`），数值不同。AID02215 在一个时段（2024-05-30 08:25:00）把 `Fast Lane` 和 `Slow Lane` 各列了两次 | 靠 `lane_id` 分不开这两条车道；待定问题 |
| 方向缺失 | AID09115、AID09116、AID90008、AID90009（沙田大埔公路上的四个新探测器）在 2025-07-25 10:34:30 之前的每个文件里都没有 `<direction>`（268,072 条读数；AID09115 从 2025-07 打包文件一开始就这样，另外三个从 07-03 起）。从 10:36:00 起有了：`East`、`East`、`West`、`West`。S2 从 2025-10 版本才列出这四个探测器，方向相同。S1 其他字段从来没有缺失或为空，所有数字、日期和时间格式都正确 | 方向可取自 S2 2025-10 版本或之后的 S1 文件；待定问题 |
| 结构变化 | `<s.d.>` 从约 2021 年 11 月 18 日起才出现（数据字典版本 `20211118`） | 更早的数据没有 `sd` |
| 车速填充值 | `volume = 0` 时，`speed` 是 70 / 80 / 100 / 50 / 110（即限速），且 99.9% 的情况下 `s.d.` = 0 | 不是测量值 |
| 自相矛盾 | `speed = 0` 但 `volume > 0`：5,991 条；`occupancy = -1`：60 条 | 需要清洗规则 |
| 超出范围 | `speed > 130`：15,711 条（0.4%），大多是快线上的 131–136；最大值 300 | 需要清洗规则 |
| 探测器卡住，还是车真的停了？ | `occupancy = 100`：1,533 条，其中 1,415 条车速和车流都是 0。TDSLTR20004 在 2025 年 8 月 5 日 06:34 到 15:26 一直是 100%，正值黑雨 | 需要判断：探测器故障，还是道路水浸 |
| 只报告了部分时间 | AID01133 在 2025 年 8 月 5 日 20:45 之后才有数据（219 个时段） | 要看每个探测器各自的覆盖率 |

三个月（2024-05、2025-07、2025-08；3.329 亿条读数）的数字来自 `python -m src.clean.manifest`、
`src.clean.s1_periods` 和 `src.clean.s1_rows`，结果表在 `data/interim/checks/`。

---

## S2. 交通探测器位置（`traffic_speed_volume_occ_info.csv`）

| | |
|---|---|
| 网址 | `https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv` |
| 格式 | CSV，带 BOM 的 UTF-8，807 行 × 11 列（2026-04 版本），一行一个探测器 |
| 历史 | 硬盘上有 8 个存档版本：2021-08、2021-09、2021-11、2021-12、2022-03（700 行）、2024-02（786 行）、2025-10（790 行）、2026-04（807 行）。分析哪个时间，就用当时生效的版本 |

| 字段 | 类型 | 说明 | 实测 |
|-------|------|-------------|----------|
| `AID_ID_Number` | 字符串 | 探测器编号；对应 S1 的 `detector_id` | 807 个，互不重复，没有 NA。S1 中出现的探测器全部能在这里找到；有 35 个列出的探测器在 2025 年 8 月 5 日没有数据 |
| `District` | 字符串 | 所在区（共 18 区） | 有 19 种写法：`Central & Western`（13 个）**和** `Central and Western`（1 个）。最多的是元朗 131 个、沙田 105 个 |
| `Road_EN`、`Road_TC`、`Road_SC` | 字符串 | 位置描述（英文、繁体、简体）：道路、地标、方向 | 97% 末尾有**多余的空格**。有两个名字各被两个探测器共用（AID04108/AID04121、AID04109/AID04122，相距约 30 米），所以关联时必须用编号，不能用名字 |
| `Easting`、`Northing` | 整数 | 香港 1980 方格网坐标 | 单位：米 |
| `Latitude`、`Longitude` | 小数 | WGS84 经纬度 | 北纬 22.25–22.51，东经 113.94–114.27 |
| `Direction` | 字符串 | 行车方向 | 8 种：`West` 127、`North West` 117、`South East` 114、`East` 108、`North East` 105、`South` 85、`South West` 79、`North` 72 |
| `Rotation` | 整数 | 方向角度（度），用于在地图上画箭头 | 0–355 |

---

## S3. 现时天气报告（`CurrentWeather.xml`）

| | |
|---|---|
| 数据集 | [现时天气报告](https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report) |
| 实时网址 | `https://rss.weather.gov.hk/rss/CurrentWeather.xml` |
| 格式 | RSS 2.0；内容是 `<description><![CDATA[ ... ]]>` 里的一段 **HTML 自由文字** |
| 发布频率 | 每小时一份公告；2021 年 6 月起每天存档约 24 份 |
| 大小 | 每个文件约 2 kB |

### 结构

| 元素 | 内容 | 例子 |
|---------|---------|---------|
| `item/title` | 公告发布时间（香港时间） | `Bulletin updated at 08:02 HKT 05/08/2025` |
| `item/pubDate` | 同一时刻，但用 **GMT（格林尼治时间）** | `Tue, 05 Aug 2025 00:02:00 GMT` |
| `item/category` | 天气类别代码 | `R` |
| `description` | 观测时刻、天文台气温和湿度 | `At 8 a.m. at the Hong Kong Observatory: Air temperature: 25 degrees Celsius; Relative Humidity: 95 per cent` |
| `description` | 正在生效的警告 | `The Black Rainstorm Warning Signal has been issued.` |
| `description` | 约 25 个气象站的气温 | `King's Park 24 degrees; ...` |
| **`description`** | **各区过去一小时雨量** | `Between 6:45 and 7:45 a.m., lightning was detected over all regions. The rainfall recorded in various regions were: Southern District 27 to 60 mm; Wan Chai 24 to 38 mm; Kwun Tong 1 mm; ...` |

我们用的是雨量那一句，它的格式在 2021 到 2025 年的样本中完全一致。
- 每一项的格式是 `<区名> <最小值> to <最大值> mm`；区内所有雨量站读数相同时，写成 `<区名> <数值> mm`。
  最小值和最大值是该区各雨量站读数的最小和最大。
- **没下雨的区不会列出。** 如果所有区都没下雨，**整句都不会出现**。
  这一点已用 S8 核对过：没有这句话的那些天，天文台逐日雨量都是 0.0 毫米。
- 统计时段写在句子里，在 HH:45 结束，**不是**报告开头 "At 8 a.m." 的那个整点。
  时段可能跨越午夜或中午，例如 `Between 11:45 p.m. and 0:45 a.m.`、`Between 11:45 a.m. and 12:45 p.m.`。
- 区名用的是天文台的写法：`Southern District`、`Eastern District`、`Islands District`、
  `North District`、`Central & Western District`。其余 13 个区的写法和 S2 相同。
- 公告通常在时段结束后约 17 分钟发布，偶尔更晚（例如 01:46）。
  存档可能在公告发布后最多一小时才抓到它：20:02 存档的文件里是 19:02 的公告。

---

## S4. 暴雨警告信号（`rstorm.dat`）

| | |
|---|---|
| 网页 | [暴雨警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb3.shtml) |
| 数据文件 | `https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat`（网页背后实际读取的文件） |
| 格式 | 制表符分隔，**没有表头**，一行一个信号；1998 年 4 月 12 日至今共 974 个信号 |

例子：`R	2026	8	27	5	5	2026	8	27	9	20	04	15`，表示红雨，2026 年 8 月 27 日 05:05 至 09:20，持续 4 小时 15 分钟。

| 列 | 说明 | 实测 |
|--------|-------------|----------|
| 1 | 颜色：`A` 黄、`R` 红、`B` 黑 | 黄 778、红 161、黑 35 |
| 2–6 | 开始时间：年、月、日、时、分 | – |
| 7–11 | 结束时间：年、月、日、时、分 | 午夜可能写成 **`24:00`**（2 例） |
| 12–13 | 持续时间：时、分 | 10 分钟至 17 小时 25 分钟 |

`UUUU` 这一行标记"之后的记录是临时数据"。它目前在文件最后一行，所以没有临时记录。
警告升级（黄 → 红 → 黑）时，前一个信号结束的那一分钟正是下一个开始的时间；
我们把这样连在一起的信号合并成一次**暴雨事件**。2022–2025 年按事件最高级别统计：

| 年份 | 黄 | 红 | 黑 |
|------|-------|-----|-------|
| 2022 | 19 | 2 | 0 |
| 2023 | 23 | 5 | 2 |
| 2024 | 37 | 4 | 0 |
| 2025 | 24 | 6 | 4 |

---

## S5. 热带气旋警告信号（`tc.dat`）

| | |
|---|---|
| 网页 | [热带气旋警告信号数据库](https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml) |
| 数据文件 | `https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat` |
| 格式 | 制表符分隔，带 BOM 的 UTF-8，**没有表头**；1946 年至今共 2,512 行（1,262 个热带气旋信号 + 1,250 行其他记录） |

例子：`202603	SuperT	SAUDEL	1	X	1810	31	8	2026	X	010	4	9	2026	X	7800`。

| 列 | 说明 | 实测 |
|--------|-------------|----------|
| 1 | 热带气旋编号（年份 + 序号） | 483 个热带气旋 |
| 2 | 强度：`TD` 热带低气压、`TS` 热带风暴、`STS` 强烈热带风暴、`T` 台风、`ST` 强台风、`SuperT` 超强台风；也有 `TST`、`TSupT`、`TD/TD` 这类组合代码（官方没有说明）。**`MSN` 行不是热带气旋信号**（1,250 行，已跳过） | `T` 394、`STS` 231、`TSupT` 178、`TS` 177、`TST` 113、`SuperT` 71、`TD` 56、`ST` 41 |
| 3 | 名字；`NIL` 表示没有名字 | 109 个没有名字 |
| 4 | 信号：1、3、8、9、10 号 | 1 号 538、3 号 428、8 号 242、9 号 35、10 号 19 |
| 5 | 8 号信号的方向（`NE`/`NW`/`SE`/`SW`）；其他信号为 `X`；部分旧记录为 `*` | – |
| 6 | 开始时间 `HHMM`（省略了开头的 0：`10` = 00:10；`2400` = 午夜） | – |
| 7–9 | 开始日、月、年 | – |
| 10 | 标记 `X` / `S`（官方没有说明；`S` 只出现在旧记录） | – |
| 11 | 结束时间 `HHMM` | – |
| 12–14 | 结束日、月、年 | – |
| 15 | 标记，同第 10 列 | – |
| 16 | 持续时间 `HHHMM`（`7800` = 78 小时 00 分钟） | – |

---

## S6. 公众假期（`en.json`）

| | |
|---|---|
| 数据集 | [香港公众假期](https://data.gov.hk/en-data/dataset/hk-dpo-statistic-cal) |
| 实时网址 | `https://www.1823.gov.hk/common/ical/en.json`（另有 `tc.json`、`sc.json`） |
| 格式 | iCalendar 风格的 JSON，带 BOM 的 UTF-8 |
| 覆盖 | **每个文件只覆盖三年**（当前的实时文件是 2025–2027）。2019 年以来存档的 10 个版本合起来覆盖 2018–2027 |

结构：`vcalendar[0].vevent[]`，每个假期一个对象：

| 字段 | 说明 | 例子 |
|-------|-------------|---------|
| `dtstart` | `[日期, {"value": "DATE"}]`，假期日期 | `["20250101", {"value": "DATE"}]` |
| `dtend` | 下一天（不包含） | `["20250102", ...]` |
| `summary` | 假期名称 | `The first day of January` |
| `uid` | `YYYYMMDD@1823.gov.hk` | – |
| `dtstamp`、`transp` | 日历元数据 | 不使用 |

实测：2018–2027 每年都是 17 个假期；170 个中有 29 个落在周末。
同一个假期在不同版本中写法不同（例如 "Lunar New Year’s Day" 的撇号有弯、直两种），所以一共有 30 种名称。**使用时只看日期，不看名称。**

---

## S8. 逐日总雨量（`daily_HKO_RF_ALL.csv`）

| | |
|---|---|
| 数据集 | [逐日总雨量](https://data.gov.hk/en-data/dataset/hk-hko-rss-daily-total-rainfall) |
| 网址 | `https://data.weather.gov.hk/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv`（`src.download static` 用的） |
| 数据集网址 | 数据集列出的是 `https://data.weather.gov.hk/weatherAPI/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv`。只有这个网址在历史存档中（2024–2025 年月度打包 24 个）；上面那个网址没有存档版本 |
| 格式 | CSV，带 BOM 的 UTF-8：2 行标题、1 行中英文表头、数据，最后是几行注释 |
| 覆盖 | 天文台总部，1884 年至今逐日（49,492 天） |

| 列 | 说明 | 实测 |
|--------|-------------|----------|
| `年/Year`、`月/Month`、`日/Day` | 日期 | – |
| `數值/Value` | 当日雨量（毫米），**是文字** | `0.0` 22,756 天；**`Trace`** 6,926 天（微量，少于 0.05 毫米）；**`***`** 1 天（没有数据） |
| `數據完整性/data Completeness` | `C` 完整，`#` 不完整 | 除 `***` 那天为空外，全部是 `C` |

直接把 `Value` 转成数字，`Trace` 会变成 NaN，但它应该当作约等于 0。
2022–2025 年有 238 天是 `Trace`，没有 `***`。

---

## 可选来源

2024–2025 年已下载（见"数据清单"），尚未解析。除特别说明外，这里的"实测"数字来自一个月度打包文件（2025-08）。

### S9. 智能灯柱探测器读数（`rawSpeedVol_SLP-all.xml`）

| | |
|---|---|
| 数据集 | [智能灯柱上的交通探测器收集的交通数据](https://data.gov.hk/en-data/dataset/hk-td-tis_33-traffic-data-traffic-detectors-installed-at-smart-lampposts) |
| 实时网址 | `https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol_SLP-all.xml` |
| 格式 | **与 S1 相同**：根元素、结构定义（`SpeedVolOcc-BR.xsd`）、字段和编码都一样（数据字典 20231228） |
| 实测 | 2025-08 有 28,465 份快照（每天最多 948 份），每月解压后 0.34 GB；17 个探测器有数据（`AID20011` 至 `AID20060`，抽查 57 份快照），S10 列出 20 个 |
| 检查（2024-05、2025-07、2025-08；550 万条读数） | 文件规律与 S1 相同：有相同副本（多余副本 142 / 2,260 / 2,028 个），每个文件两个时段，每个时段只在一个不同的文件里，时段缺失 26.9 / 46.3 / 40.8%（最长连续缺失 42、15、9 分钟）。没有截断文件。探测器 20、18、17 个（都在 S10 里）；每个探测器的方向固定；车道只有 `Fast`、`Middle`、`Slow Lane`。没有缺失或为空的字段，所有值格式正确。`valid = N`：9,162 / 84 / 36 条 |
| 同一车道出现两次 | 有 49 个文件里，某个探测器把一条车道列了两次，通常紧挨着（622 个键：2024-05 有 568 个，2025-07 的一个文件有 26 个，2025-08 的一个文件有 28 个）。615 个键两次读数完全相同；7 个不同（AID20031 2024-05-02 07:34:00，AID20022 05-16 08:02:00 和 05-17 17:55:30，AID20054 05-20 17:22:00） |

### S10. 智能灯柱探测器位置（`traffic_speed_volume_occ_info-slp.csv`）

| | |
|---|---|
| 网址 | `https://static.data.gov.hk/td/traffic-data-slp/info/traffic_speed_volume_occ_info-slp.csv` |
| 列 | 与 S2 相同的 11 列（`AID_ID_Number`、`District`、`Road_EN`、…、`Rotation`） |
| 版本 | 存档只有两个。**两者编码不同**：2023-12（13 行）是**带 BOM 的 UTF-16、制表符分隔**；2024-01（20 行）是带 BOM 的 UTF-8、逗号分隔。要按 BOM 判断编码，不能写死 |
| 实测 | 所在区：观塘、湾仔、油尖旺。`Road_EN` 末尾带方括号里的编号。AID20051 的 `Direction` 是 `East`，但 `Road_EN` 写的是 "Westbound"（`Rotation` 270） |

### S11. 路段车速（`irnAvgSpeed-all.xml`）

| | |
|---|---|
| 数据集 | [主要干道及道路交通数据](https://data.gov.hk/en-data/dataset/hk-td-sm_4-traffic-data-strategic-major-roads)，资源 "Traffic Speeds of Road Network Segments (Processed Data)" |
| 实时网址 | `https://resource.data.one.gov.hk/td/traffic-detectors/irnAvgSpeed-all.xml` |
| 结构 | `<segment_speed_list>`：`date`、`time`、`irn_version`，然后 `<segments>` 里每个 `<segment>` 有 `segment_id`、`speed`（小数，km/h，"current average speed"）、`valid`（`Y` 在线 / `N` 离线） |
| 实测 | 2025-08 有 21,414 份快照（相隔约 1–2 分钟），每月解压后 7.9 GB；每个文件 4,405 个路段，一份样本中 41 个 `valid = N`。17:02 存档的文件 `time` 是 16:55。`irn_version` 为 `20221210` |
| 关联 | `segment_id` 就是 S12 道路中心线的 `ROUTE_ID`：一份 2025-08 快照的 4,405 个编号中，4,395 个能在 2025-08 的 CENTERLINE 图层中找到（其余 10 个尚未对照旧版本） |

### S14. 路段表（`speed_segments_info.csv`）

`https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv`，
4,255 行 × 2 列（2023-09）：`irn_id`（路段编号）和 `ucase(route)`（路段所属的**路线编号**；共 174 个，例如路线 `9` 有 423 个路段）。
没有坐标：几何在 S12。硬盘上有 6 个版本（2021-08 至 2023-09）。

### S12. 第二代路网（`RdNet_IRNP.gdb.zip`）

| | |
|---|---|
| 数据集 | [道路网络（第二代）](https://data.gov.hk/en-data/dataset/hk-td-tis_15-road-network-v2) |
| 网址 | `https://static.data.gov.hk/td/road-network-v2/RdNet_IRNP.gdb.zip`：该数据集唯一进了历史存档的资源（各图层的 GML / KMZ 文件都没有存档） |
| 格式 | ZIP 里的 Esri File Geodatabase，在打包文件中名为 `<YYYYMMDD-HHMM>-RdNet_IRNP.gdb.zip`；每个版本约 17 MB，2024–2025 年共 34 个版本 |
| 图层 | 17 个：`CENTERLINE`、`INTERSECTION`、`SPEED_LIMIT`、`BUS_ONLY_LANE`、`TURN`、`ROUNDABOUT`、`TRAFFIC_FEATURES`、`PEDESTRIAN_ZONE`、`NSR`、`PERMIT`、`PROHIBITION`、`VEHICLE_RESTRICTION`、`RUN_IN_OUT`、`ONSTREETPARK`、`GISP_ON_STREET_PARKING`、`TUN_BRIDGE_TOLL`、`TUN_BRIDGE_TV_TOLL` |
| CENTERLINE | 35,837 条（2025-08）；列 `STREET_ENAME`、`STREET_CNAME`、`ELEVATION`、`ST_CODE`、`EXIT_NUM`、`ROUTE_NUM`、`REMARKS`、`ROUTE_ID`、`TRAVEL_DIRECTION`、`CRE_DATE`、`LAST_UPD_DATE_V`、`ALIAS_ENAME`、`ALIAS_CNAME`、`SHAPE_Length`；坐标系 EPSG:2326（香港 1980 方格网，与 S2 的 `Easting` / `Northing` 相同） |
| 读取 | `geopandas` / `pyogrio`（已装在 conda base）。几何带 M 值，pyogrio 会去掉并给出警告 |

### S13. 特别交通消息（`trafficnews.xml`）

| | |
|---|---|
| 数据集 | [特别交通消息（第二代）](https://data.gov.hk/en-data/dataset/hk-td-tis_19-special-traffic-news-v2) |
| 实时网址 | `https://www.td.gov.hk/en/special_news/trafficnews.xml` |
| 结构 | `<list>` 里若干 `<message>`，字段见 XSD：`INCIDENT_NUMBER`、`INCIDENT_HEADING_EN/CN`、`INCIDENT_DETAIL_EN/CN`、`LOCATION_EN/CN`\*、`DISTRICT_EN/CN`\*、`DIRECTION_EN/CN`\*、`ANNOUNCEMENT_DATE`（`YYYY-MM-DDTHH:MM:SS`）、`INCIDENT_STATUS_EN/CN`（`NEW` / `UPDATED` / `CLOSED`）、`NEAR_LANDMARK_EN/CN`\*、`BETWEEN_LANDMARK_EN/CN`\*、`ID`、`CONTENT_EN/CN`、`LATITUDE`\*、`LONGITUDE`\*（\* 可选） |
| 实测 | 2025-08 有 3,390 份快照（每天最多 166 份）。每份快照是当时仍有效的消息列表（一份样本只有 1 条消息），所以同一条消息会在多份快照中重复出现。可选字段经常缺失（那份样本没有区，也没有经纬度） |

### N2. 自动气象站逐小时雨量（`hourlyRainfall.php`）

`https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en`：JSON，含 `obsTime`，
以及 36 个站各自的 `automaticWeatherStation`、`automaticWeatherStationID`、`value`、`unit`。
**它不在历史存档中**：对任何日期范围，API 都返回 `Not Found`。所以只能从现在开始实时采集。
这就是我们改为按区（S3）把雨量对应到道路的原因。

### S7. 格点雨量临近预报

`https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv`，约 2022 年 7 月起有存档，每天约 96 份（每 15 分钟）。
每份是 121 × 121 的网格（约 2 公里）× 4 个预报时效（+30 至 +120 分钟）= 58,564 行，
列为 `Updated Date and Time`、`Ending Date and Time`、`Latitude`、`Longitude`、`Half-hourly Nowcast Accumulated Rainfall (mm)`；时间格式为 `YYYYMMDDHHMM`。
它是基于雷达的**预报**，不是雨量站的实测值，最多只能用作更细空间尺度的敏感性检查。数据字典注明这是临时数据。

实测（2025-08）：网格范围北纬 21.328–23.487 度、东经 112.956–115.291 度（远大于香港）；
02:30 存档的文件更新时间是 02:12，结束时间为 02:42、03:12、03:42、04:12；每月解压后 8 GB。
