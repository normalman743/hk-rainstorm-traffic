# search_datasets parameter values

Reference date: 2026-09. Values may change on DATA.GOV.HK after this date.

Sources: category and provider IDs come from the DATA.GOV.HK Developer Center "API Specification" page (Historical Archive File List API section); the category names there match the data.gov.hk dataset search page's "Data Category" dropdown one-to-one. format values come from that search page's "Data Format" dropdown. The search page's own request, e.g. `category=law-and-security,recreation-and-culture&provider=hk-aw,hk-cstb&format=xls,xml`, shows it uses the same category/provider IDs and lower-case formats.

Values are passed to the API as-is and are not validated here: whatever the API returns for an unlisted value (empty result, error, ...) is what you get.

Usually only `keyword` is needed: every other default matches the website's own search box.

Observed behaviour (tested 2026-09):
- `keyword` is not substring-matched: "rain" returned 0 datasets, "rainfall" 4, "rainstorm" 0. Try several words.
- `limit` defaults to 12, the website's page size; larger values work in one request (limit=100 tested).
- `search_content=True` is noisy: "rainstorm" with it returned 3 datasets, all unrelated (library RSS, job ads, ...).
- `provider` with keyword "" lists every dataset of that provider (hk-hko: 57).

## All parameters

| parameter | default | values | sent as |
|---|---|---|---|
| keyword | (required) | free text | `keyword` |
| limit | 12 (website's page size) | positive int; results per request | `limit` |
| offset | 0 | int >= 0; results to skip | `offset` |
| page | None | 1-based page; if given, offset = (page - 1) * limit | (converted to `offset`) |
| lang | "en" | "en", "tc", "sc" | `lang` |
| search_content | False | True also matches resource content ("Search Dataset Title, Description and Content") | `searchContent=true` |
| category | None (= All) | list of category IDs below | `category`, comma-joined |
| provider | None (= All) | list of provider IDs below | `provider`, comma-joined |
| format | None (= All) | list of formats below, lower-case | `format`, comma-joined |

`sortBy=relevance` is always sent and not configurable.

## category (20)

| ID | name |
|---|---|
| `city-management` | City Management and Utilities |
| `climate-and-weather` | Climate and Weather |
| `commerce-and-industry` | Commerce and Industry |
| `social-welfare` | Community and Social Welfare |
| `development` | Development, Geography and Land Information |
| `education` | Education |
| `legislature` | Election and Legislature |
| `employment-and-labour` | Employment and Labour |
| `environment` | Environment |
| `finance` | Finance |
| `food` | Food |
| `health` | Health |
| `housing` | Housing |
| `law-and-security` | Law and Security |
| `population` | Population |
| `recreation-and-culture` | Recreation, Sports and Culture |
| `information-technology-and-broadcasting` | Technology and Broadcasting |
| `tourism` | Tourism |
| `transport` | Transportation |
| `miscellaneous` | Miscellaneous |

## provider (129)

| ID | name |
|---|---|
| `aahk` | Airport Authority Hong Kong |
| `amigo` | Amigo (Taxi Fleet Licensee) |
| `big-boss-taxi` | Big Boss Taxi (Taxi Fleet Licensee) |
| `cc` | Consumer Council |
| `centaline` | Centaline Property Agency Limited |
| `cfs` | Centre for Food Safety |
| `chsc` | Committee on Home-School Co-operation |
| `ckf` | Chuen Kee Ferry Limited |
| `clp` | CLP Power Hong Kong Limited |
| `compcomm` | Competition Commission |
| `ctb` | Citybus Limited |
| `cyberport` | Hong Kong Cyberport Management Company Limited |
| `dc` | District Councils |
| `eac` | Electoral Affairs Commission |
| `ff` | Fortune Ferry Company Limited |
| `hk-afcd` | Agriculture, Fisheries and Conservation Department |
| `hk-ams` | Auxiliary Medical Service |
| `hk-archsd` | Architectural Services Department |
| `hk-aud` | Audit Commission |
| `hk-aw` | Administration Wing, Chief Secretary for Administration's Office |
| `hk-bd` | Buildings Department |
| `hk-cad` | Civil Aviation Department |
| `hk-cas` | Civil Aid Service |
| `hk-cedb` | Commerce and Economic Development Bureau |
| `hk-cedd` | Civil Engineering and Development Department |
| `hk-censtatd` | Census and Statistics Department |
| `hk-ceo` | Chief Executive's Office |
| `hk-cmab` | Constitutional and Mainland Affairs Bureau |
| `hk-cpu` | Central Policy Unit |
| `hk-cepu` | Chief Executive's Policy Unit |
| `hk-cr` | Companies Registry |
| `hk-csb` | Civil Service Bureau |
| `hk-csd` | Correctional Services Department |
| `hk-cso` | Chief Secretary for Administration's Office |
| `hk-cstb` | Culture, Sports and Tourism Bureau |
| `hk-customs` | Customs and Excise Department |
| `hk-devb` | Development Bureau |
| `hk-dh` | Department of Health |
| `hk-doj` | Department of Justice |
| `hk-dpo` | Digital Policy Office |
| `hk-dsd` | Drainage Services Department |
| `hk-eabfu` | Economic Analysis and Business Facilitation Unit |
| `hk-edb` | Education Bureau |
| `hk-eeb` | Environment and Ecology Bureau |
| `hk-emsd` | Electrical and Mechanical Services Department |
| `hk-epd` | Environmental Protection Department |
| `hk-fehd` | Food and Environmental Hygiene Department |
| `hk-fsd` | Fire Services Department |
| `hk-fso` | Financial Secretary's Office |
| `hk-fstb` | Financial Services and the Treasury Bureau |
| `hk-gfs` | Government Flying Service |
| `hk-gld` | Government Logistics Department |
| `hk-govtlab` | Government Laboratory |
| `hk-gpa` | Government Property Agency |
| `hk-had` | Home Affairs Department |
| `hk-hb` | Housing Bureau |
| `hk-hhb` | Health Bureau |
| `hk-hkma` | Hong Kong Monetary Authority |
| `hk-hko` | Hong Kong Observatory |
| `hk-hkpf` | Hong Kong Police Force |
| `hk-hkpo` | Hongkong Post |
| `hk-housing` | Hong Kong Housing Authority |
| `hk-hyab` | Home and Youth Affairs Bureau |
| `hk-hyd` | Highways Department |
| `hk-icac` | Independent Commission Against Corruption |
| `hk-immd` | Immigration Department |
| `hk-investhk` | Invest Hong Kong |
| `hk-ipd` | Intellectual Property Department |
| `hk-ird` | Inland Revenue Department |
| `hk-isd` | Information Services Department |
| `hk-itc` | Innovation and Technology Commission |
| `hk-itib` | Innovation, Technology and Industry Bureau |
| `hk-jsscs` | Joint Secretariat for the Advisory Bodies on Civil Service and Judicial Salaries and Conditions of Service |
| `hk-lad` | Legal Aid Department |
| `hk-landsd` | Lands Department |
| `hk-lcsd` | Leisure and Cultural Services Department |
| `hk-ld` | Labour Department |
| `hk-lr` | Land Registry |
| `hk-lwb` | Labour and Welfare Bureau |
| `hk-md` | Marine Department |
| `hk-ofca` | Office of the Communications Authority |
| `hk-ofnaa` | Office for Film, Newspaper and Article Administration |
| `hk-omb` | Office of the Ombudsman |
| `hk-oro` | Official Receiver's Office |
| `hk-pland` | Planning Department |
| `hk-psc` | Public Service Commission |
| `hk-reo` | Registration and Electoral Office |
| `hk-rthk` | Radio Television Hong Kong |
| `hk-rvd` | Rating and Valuation Department |
| `hk-sb` | Security Bureau |
| `hk-sciocs` | Secretariat, Commissioner on Interception of Communications and Surveillance |
| `hk-swd` | Social Welfare Department |
| `hk-td` | Transport Department |
| `hk-tid` | Trade and Industry Department |
| `hk-tlb` | Transport and Logistics Bureau |
| `hk-try` | Treasury |
| `hk-ugc` | University Grants Committee Secretariat |
| `hk-wfsfaa` | Working Family and Student Financial Assistance Agency |
| `hk-wsd` | Water Supplies Department |
| `hkcaavq` | Hong Kong Council for Accreditation of Academic and Vocational Qualifications |
| `hkcert` | Hong Kong Computer Emergency Response Team Coordination Centre |
| `hkeaa` | Hong Kong Examinations and Assessment Authority |
| `hkecic` | Hong Kong Export Credit Insurance Corporation |
| `hkelectric` | The Hongkong Electric Company, Limited |
| `hkhs` | Hong Kong Housing Society |
| `hkirc` | Hong Kong Internet Registration Corporation Limited |
| `hkkf` | Hong Kong & Kowloon Ferry Limited |
| `hkpc` | Hong Kong Productivity Council |
| `hkstp` | Hong Kong Science and Technology Parks Corporation |
| `hktdc` | Hong Kong Trade Development Council |
| `hktramways` | Hong Kong Tramways, Limited |
| `hospital` | Hospital Authority |
| `ia` | Insurance Authority |
| `joie` | Joie (Taxi Fleet Licensee) |
| `legco` | Legislative Council |
| `llb` | Liquor Licensing Board |
| `mpfa` | Mandatory Provident Fund Schemes Authority |
| `mtr` | MTR Corporation Limited |
| `nlb` | New Lantao Bus Company (1973) Limited |
| `pckt` | Peng Chau Kai To Limited |
| `rehabsociety` | The Hong Kong Society for Rehabilitation |
| `starferry` | The "Star" Ferry Company, Limited |
| `sunferry` | Sun Ferry Services Company Limited |
| `towngas` | The Hong Kong and China Gas Company Limited |
| `tpd` | Town Planning Board |
| `traway` | Tsui Wah Ferry Service (H.K.) Limited |
| `ura` | Urban Renewal Authority |
| `wkcda` | West Kowloon Cultural District Authority |
| `28hse` | 28Hse Limited |

## format (38)

Listed as shown in the dropdown; send lower-case (e.g. `xml`, `csv`, `geojson`).

3DS, API, ASC, ASCII, CESIUM3DTILES, CSV, DAE, DGN, DWG, FBX, FGDB, GEOPACKAGE, GEOTIFF, GFS, GLTF, GML, GTFS, GeoJSON, ICS, JPEG, JSON, KML, KMZ, MAX, MDB, OBJ, OSGB, PNG, RINEX, RSS, RTCM, SHP, VRML, XLS, XLSM, XLSX, XML, ZIP
