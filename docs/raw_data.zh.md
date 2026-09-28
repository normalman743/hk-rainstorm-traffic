# 原始数据字典

> 本文是 [`raw_data.md`](raw_data.md) 的中文版，两者内容一致。字段名、文件名和代码保留英文原文。

本文档说明每个**原始**数据来源在发布时的样子：来自哪里、怎样获取、格式和结构、每个字段的含义、
实际出现哪些取值，以及检查真实数据时发现的问题。处理后的表格见
[`processing.zh.md`](processing.zh.md) 和 [`database_description.md`](database_description.md)。

文中标为"实测"的数字，来自 2026 年 9 月对真实数据的只读审计。除特别说明外，交通数据用的是 2025 年 8 月 5 日（黑雨当天）。

除特别说明外，所有时间均为**香港时间（HKT，UTC+8）**。

| 编号 | 数据 | 提供者 | 格式 | 用途 | 由谁下载 |
|----|--------|----------|--------|----------|---------------|
| S1 | 交通探测器读数 | 运输署 | XML，每分钟一个文件 | 目标变量（车速、车流、占用率） | `src.pipeline`（第 3 步） |
| S2 | 交通探测器位置 | 运输署 | CSV | 探测器属性、按区关联雨量 | `src.download static` |
| S3 | 现时天气报告 | 香港天文台 | RSS/XML，每小时 | 分区雨量 | `src.pipeline`（第 3 步） |
| S4 | 暴雨警告信号 | 香港天文台 | 制表符分隔的文本 | 警告状态、选择事件日 | `src.download warnings` |
| S5 | 热带气旋警告信号 | 香港天文台 | 制表符分隔的文本 | 排除台风时段 | `src.download warnings` |
| S6 | 公众假期 | 1823（香港特区政府） | JSON | 日期类型 | `src.download holidays` |
| S8 | 逐日总雨量 | 香港天文台 | CSV | 按日核对 | `src.download static` |

考虑过但不使用：N1 道路路段表、N2 自动气象站逐小时雨量，以及 S7 格点雨量临近预报（可选扩展）。见文末。

---

## 历史文件怎样获取

S1 和 S3 的实时网址永远只返回**最新**的文件。过去的版本要从
[DATA.GOV.HK 历史存档 API](https://data.gov.hk/en/help/api-spec) 获取：

| 接口 | 参数 | 返回 |
|----------|------------|---------|
| `https://app.data.gov.hk/v1/historical-archive/list-file-versions` | `url`（实时网址）、`start`、`end`（`YYYYMMDD`） | JSON：`timestamps`（每个存档版本一个，格式 `YYYYMMDD-HHMM`）、`data-files`（ZIP 打包文件，通常每月一个）、`data-dictionary-dates` |
| `https://app.data.gov.hk/v1/historical-archive/get-file` | `url`、`time` | HTTP 302 跳转到文件。`time=YYYYMMDD-HHMM` 取一份快照；`time=YYYYMMDD`（打包文件的时间戳）取整个打包 ZIP |

交通数据的打包文件每月约 1 GB。包内文件名为
`<URL 编码后的实时网址>/<YYYYMMDD-HHMM>-rawSpeedVol-all.xml`，另附一份数据字典 PDF。
我们的下载器用 HTTP 分段请求读取打包文件的 ZIP 目录，只取所需那一天的文件（压缩后约 31 MB，而不是 1 GB）。

**存档时间 ≠ 测量时间。** 版本的时间戳是存档系统抓取文件的时间，不是数据的测量时间（见 S1 和 S3）。

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
| 车道 | `valid` | `Y`/`N` | – | – | 运输署的有效性标记；0.5% 的读数为 `N`。`N` 的读数数值看起来都正常，只能靠这个标记识别 |

### 数据问题（实测）

| 问题 | 证据 | 影响 |
|-------|----------|-------------|
| 存档时间 ≠ 测量时间 | 08:01 存档的文件里是 07:53:00–07:54:00 的数据（延迟约 5–10 分钟） | 用 `period_from` 定时间，不能用文件名 |
| 时段缺失 | 2025 年 8 月 5 日每天 2,880 个时段只有 1,730 个（约 40% 缺失） | 缺失表现为**这一行不存在**，而不是 NA |
| 相邻文件重叠 | 相邻文件重复同样的读数；约 9% 的行是重复的 | 按（时间，探测器，车道）去重 |
| 午夜日期错误 | 00:00 那个时段带的是**前一天**的 `<date>` | 用存档时间修正日期 |
| 重复文件 | 月度打包文件偶尔把同一个文件存两次 | 丢弃完全相同的副本 |
| 截断文件 | 少数文件在中途被截断（2025 年 7 月 29 日 919 份中有 1 份） | 保留截断前完整的读数 |
| 结构变化 | `<s.d.>` 从约 2021 年 11 月 18 日起才出现（数据字典版本 `20211118`） | 更早的数据没有 `sd` |
| 车速填充值 | `volume = 0` 时，`speed` 是 70 / 80 / 100 / 50 / 110（即限速），且 99.9% 的情况下 `s.d.` = 0 | 不是测量值 |
| 自相矛盾 | `speed = 0` 但 `volume > 0`：5,991 条；`occupancy = -1`：60 条 | 需要清洗规则 |
| 超出范围 | `speed > 130`：15,711 条（0.4%），大多是快线上的 131–136；最大值 300 | 需要清洗规则 |
| 探测器卡住，还是车真的停了？ | `occupancy = 100`：1,533 条，其中 1,415 条车速和车流都是 0。TDSLTR20004 在 2025 年 8 月 5 日 06:34 到 15:26 一直是 100%，正值黑雨 | 需要判断：探测器故障，还是道路水浸 |
| 只报告了部分时间 | AID01133 在 2025 年 8 月 5 日 20:45 之后才有数据（219 个时段） | 要看每个探测器各自的覆盖率 |

---

## S2. 交通探测器位置（`traffic_speed_volume_occ_info.csv`）

| | |
|---|---|
| 网址 | `https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/traffic_speed_volume_occ_info.csv` |
| 格式 | CSV，带 BOM 的 UTF-8，807 行 × 11 列，一行一个探测器 |
| 历史 | 只有最新版本（后来新增的探测器会出现，已撤除的不会出现） |

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
| 网址 | `https://data.weather.gov.hk/cis/csvfile/HKO/ALL/daily_HKO_RF_ALL.csv` |
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

## 不使用的来源（S7 是可选扩展）

### N1. 道路路段表（`speed_segments_info.csv`）

`https://static.data.gov.hk/td/traffic-data-strategic-major-roads/info/speed_segments_info.csv`，
4,255 行 × 2 列：`irn_id`（路段编号）和 `ucase(route)`（路段所属的**路线编号**；共 174 个，例如路线 `9` 有 423 个路段）。
它没有坐标，也没法对应到探测器；它是配合处理后的路段车速数据 `irnAvgSpeed-all.xml` 用的。
我们的研究单元是探测器，所以不用它。

### N2. 自动气象站逐小时雨量（`hourlyRainfall.php`）

`https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en`：JSON，含 `obsTime`，
以及 36 个站各自的 `automaticWeatherStation`、`automaticWeatherStationID`、`value`、`unit`。
**它不在历史存档中**：对任何日期范围，API 都返回 `Not Found`。所以只能从现在开始实时采集。
这就是我们改为按区（S3）把雨量对应到道路的原因。

### S7. 格点雨量临近预报（可选）

`https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv`，约 2022 年 7 月起有存档，每天约 96 份。
每份是 121 × 121 的网格（约 2 公里）× 4 个预报时效（+30 至 +120 分钟），
列为 `Updated Date and Time`、`Ending Date and Time`、`Latitude`、`Longitude`、`Half-hourly Nowcast Accumulated Rainfall (mm)`。
它是基于雷达的**预报**，不是雨量站的实测值，最多只能用作更细空间尺度的敏感性检查。
