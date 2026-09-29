"""Find DATA.GOV.HK resources and check their historical-archive coverage.

Project-agnostic: takes URLs / dataset IDs directly, no config file. Every
function returns the API's JSON response unchanged (no fields dropped, renamed or
added); summarising for humans is the CLI's job. API errors are raised with the
response body included.

Four independent lookups, use whichever fits what you already know:

    search_datasets(keyword) -- don't know the dataset; relevance-ranked search
                                 over dataset titles/descriptions (what the
                                 data.gov.hk search box itself uses)
    search_files(keyword)    -- the Historical Archive's own file-list search;
                                 returns whatever it returns
    dataset(dataset_id)      -- know the dataset id from the website URL; exact,
                                 full resource list (including API-only resources)
    coverage(url)            -- know a resource's file URL; every archived version
                                 and bundle of it within a date range

Reference, not a lookup:

    search_params()          -- every search_datasets parameter with its values,
                                 incl. the full category/provider/format lists
                                 (from search_params.md, as of 2026-09)

Typical chain: search-datasets -> take a dataset `id` -> dataset -> take a
resource `url` -> coverage. The CLI's `coverage --dataset ID` does the last
two steps for every resource of a dataset. To download what coverage shows,
write a plan for hkdata.download.

Note on search_files: it wraps the Historical Archive File List API that
DATA.GOV.HK publishes for developers; I find it awkward to use.
Recommended instead: search_datasets (the website's own search) to find the
dataset, dataset() to see its resources, coverage() to see what's archived.

Recommended in the CLI: add --brief to search-datasets and coverage when
scanning (one line per dataset / per resource); drop it to see every field of
the one you picked. Full output of `coverage --dataset` on a dataset with many
resources runs to thousands of lines.

CLI (every example below has been run):

    python -m hkdata.discover search-datasets weather
    python -m hkdata.discover search-datasets rainfall --brief
    python -m hkdata.discover search-datasets traffic --limit 50
    python -m hkdata.discover search-datasets weather --limit 2 --offset 5
    python -m hkdata.discover search-datasets "" --provider hk-hko --brief --limit 60
        other options: --page N (overrides --offset); advanced, usually left
        unset: --lang en|tc|sc, --search-content, --category ID..,
        --provider ID.., --format FMT..
    python -m hkdata.discover search-params
    python -m hkdata.discover search-params provider
        sections: parameters, category, provider, format
    python -m hkdata.discover search-files strategic --provider hk-td
        other options: --category ID
    python -m hkdata.discover dataset hk-td-sm_4-traffic-data-strategic-major-roads
    python -m hkdata.discover dataset hk-td-sm_4-traffic-data-strategic-major-roads --lang tc
    python -m hkdata.discover coverage https://resource.data.one.gov.hk/td/traffic-detectors/rawSpeedVol-all.xml --start 2026-09-01
    python -m hkdata.discover coverage --dataset hk-hko-rss-current-weather-report --start 2026-09-20
    python -m hkdata.discover coverage --dataset hk-hko-rss-current-weather-report --start 2024-01-01 --brief
        other options: --end YYYY-MM-DD (default: yesterday)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ARCHIVE_API = "https://app.data.gov.hk/v1/historical-archive"
CKAN_API = "https://data.gov.hk/{lang}-data/api/3/action"  # lang: en, tc, sc
SITE_SEARCH_API = "https://data.gov.hk/api/v1/datasets"
EARLIEST = date(2005, 3, 1)  # historical-archive API rejects start dates before this
TIMEOUT = 60  # seconds, for every request
SEARCH_PARAMS_FILE = Path(__file__).with_name("search_params.md")

# The site search API 401s without a browser-looking request.
_BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                    "Referer": "https://data.gov.hk/en-datasets"}


def _check(resp: requests.Response) -> requests.Response:
    """raise_for_status, with the response body added to the error message."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise requests.HTTPError(f"{exc}\nresponse body:\n{resp.text}", response=resp) from exc
    return resp


def _get(url: str, params: dict, headers: dict | None = None) -> dict:
    return _check(requests.get(url, params=params, headers=headers, timeout=TIMEOUT)).json()


def _yesterday() -> date:
    return date.today() - timedelta(days=1)


def search_datasets(keyword: str, limit: int = 12, offset: int = 0, page: int | None = None, lang: str = "en",
                    search_content: bool = False,
                    category: list[str] | None = None, provider: list[str] | None = None,
                    format: list[str] | None = None) -> dict:
    """Relevance-ranked search over dataset titles/descriptions -- the same
    endpoint the data.gov.hk website's own search box calls. Returns the API
    response unchanged: `total`, `totalPages`, and `datasets` (each with all
    fields and all three languages). Parameter values are passed to the API as-is,
    not validated; whatever the API returns for them is what you get.
    `search_params()` lists every parameter's values in full.

    Only `keyword` is usually needed; the other parameters' defaults match the
    website's own search box.

    Matching is not substring: "rain" returned 0 datasets while "rainfall"
    returned 4, and "rainstorm" returned 0 (tested 2026-09). Try several words.

    Parameters:
        keyword        -- free text, e.g. "weather", "road network".
        limit          -- results per request, positive int; default 12 (the
                          website's page size). Larger values work in one
                          request (limit=100 tested 2026-09).
        offset         -- number of results to skip, int >= 0; default 0.
        page           -- 1-based page number, or None (default). Takes priority
                          over `offset`: if given, `offset` is ignored and replaced
                          by (page - 1) * limit.
        lang           -- "en" (default), "tc" or "sc"; sent to the API as-is.
                          The response always carries all three languages.
        search_content -- False (default): match title/description only. True:
                          also match resource content (the website's "Search
                          Dataset Title, Description and Content" option).
                          Noisy in tests: "rainstorm" with it returned 3
                          datasets, all unrelated (library RSS, job ads, ...).
        category       -- None (default, = "All") or a list of category IDs,
                          e.g. ["transport", "climate-and-weather"].
        provider       -- None (default, = "All") or a list of provider IDs,
                          e.g. ["hk-td", "hk-hko"]. With keyword "" it lists
                          every dataset of that provider (hk-hko: 57, 2026-09).
        format         -- None (default, = "All") or a list of lower-case file
                          formats, e.g. ["xml", "csv"].
    """
    if page is not None:
        offset = (page - 1) * limit
    params = {"limit": limit, "offset": offset, "sortBy": "relevance", "keyword": keyword, "lang": lang}
    if search_content:
        params["searchContent"] = "true"
    if category:
        params["category"] = ",".join(category)
    if provider:
        params["provider"] = ",".join(provider)
    if format:
        params["format"] = ",".join(format)
    return _get(SITE_SEARCH_API, params, headers=_BROWSER_HEADERS)


def search_params() -> str:
    """Contents of search_params.md: every search_datasets parameter with its
    default and values, including the full category/provider/format lists
    (reference date 2026-09)."""
    return SEARCH_PARAMS_FILE.read_text()


def search_files(keyword: str, provider: str | None = None, category: str | None = None) -> dict:
    """Historical Archive list-files with `keyword` as its `search` param, over the
    whole archive (2005-03-01 to yesterday). Returns whatever the API returns,
    unchanged.

    TODO(update): how the API matches `keyword` is not documented here yet.

    Parameters:
        keyword  -- passed to the API's `search` param as-is.
        provider -- None (default, = all providers) or one provider id, e.g.
                    "hk-td", "hk-hko".
        category -- None (default, = all categories) or one category id, e.g.
                    "transport", "climate-and-weather".
    """
    params = {"start": f"{EARLIEST:%Y%m%d}", "end": f"{_yesterday():%Y%m%d}", "search": keyword}
    if provider:
        params["provider"] = provider
    if category:
        params["category"] = category
    return _get(f"{ARCHIVE_API}/list-files", params)


def dataset(dataset_id: str, lang: str = "en") -> dict:
    """CKAN package_show response, unchanged (`help`, `success`, `result`).
    `result` holds the dataset metadata plus every resource, including API-only
    ones that list-files/search won't surface. Text fields come in one language
    only, the one chosen by `lang`.

    Parameters:
        dataset_id -- the slug from the dataset's URL,
                      https://data.gov.hk/en-data/dataset/<dataset_id>, e.g.
                      "hk-td-sm_4-traffic-data-strategic-major-roads".
        lang       -- "en" (default), "tc" or "sc"; picks the site's
                      en-data / tc-data / sc-data API.
    """
    return _get(f"{CKAN_API.format(lang=lang)}/package_show", {"id": dataset_id})


def coverage(url: str, start: date = EARLIEST, end: date | None = None) -> dict:
    """list-file-versions response for `url`, unchanged. Notable fields:
    `data-files` (downloadable bundles; `period` 'M' = one whole month, 'D' = one
    day), `timestamps` (individual snapshots, YYYYMMDD-HHMM), `version-count`
    (number of snapshots in the range), `total-size`. With no archived copies in
    the range these are empty lists / 0, not missing.

    `timestamps` can be truncated: a 28-day range of rawSpeedVol-all.xml returned
    10000 timestamps against a version-count of 21191. Don't treat it as complete
    unless len(timestamps) == version-count.

    Parameters:
        url   -- the resource's file URL exactly as listed by search_files()/
                 dataset(), e.g. "https://resource.data.one.gov.hk/td/
                 traffic-detectors/rawSpeedVol-all.xml".
        start -- first day of the range, a date >= EARLIEST (2005-03-01, the
                 API's lower bound); default EARLIEST.
        end   -- last day of the range (inclusive), a date; default None, which
                 means yesterday.
    """
    if end is None:
        end = _yesterday()
    return _get(f"{ARCHIVE_API}/list-file-versions",
                {"url": url, "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}"})


def _collapse_months(timestamps: list[str]) -> list[str]:
    months = sorted({datetime.strptime(ts, "%Y%m%d").strftime("%Y-%m") for ts in timestamps})
    index = lambda m: int(m[:4]) * 12 + int(m[5:7])
    ranges, group = [], []
    for m in months:
        if group and index(m) - index(group[-1]) != 1:
            ranges.append(group)
            group = []
        group.append(m)
    if group:
        ranges.append(group)
    return [g[0] if len(g) == 1 else f"{g[0]}..{g[-1]}" for g in ranges]


def _collapse_days(timestamps: list[str]) -> list[str]:
    days = sorted({datetime.strptime(ts, "%Y%m%d").date() for ts in timestamps})
    ranges, group = [], []
    for d in days:
        if group and (d - group[-1]).days != 1:
            ranges.append(group)
            group = []
        group.append(d)
    if group:
        ranges.append(group)
    return [g[0].isoformat() if len(g) == 1 else f"{g[0].isoformat()}..{g[-1].isoformat()}" for g in ranges]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


# search-params section argument -> heading prefix in search_params.md
_PARAM_SECTIONS = {"parameters": "## All parameters", "category": "## category",
                   "provider": "## provider", "format": "## format"}


def _params_section(text: str, section: str) -> str:
    """The `## ...` block of search_params.md whose heading starts with
    _PARAM_SECTIONS[section]; raises if there isn't exactly one."""
    blocks = ["## " + b for b in text.split("\n## ")[1:]]
    found = [b for b in blocks if b.startswith(_PARAM_SECTIONS[section])]
    if len(found) != 1:
        raise ValueError(f"expected one '{_PARAM_SECTIONS[section]}' section in {SEARCH_PARAMS_FILE}, found {len(found)}")
    return found[0].rstrip("\n")


def _range_line(start: date, end: date, end_defaulted: bool) -> str:
    return f"range:           {start} .. {end}" + (" (end default: yesterday)" if end_defaulted else "")


def _bundle_ranges(bundles: list[dict]) -> tuple[str, str, list[dict]]:
    """Monthly and daily bundles collapsed into ranges, plus every bundle whose
    period is neither M nor D (left as-is)."""
    monthly = ", ".join(_collapse_months([b["timestamp"] for b in bundles if b["period"] == "M"])) or "(none)"
    daily = ", ".join(_collapse_days([b["timestamp"] for b in bundles if b["period"] == "D"])) or "(none)"
    return monthly, daily, [b for b in bundles if b["period"] not in ("M", "D")]


def _print_coverage(data: dict, start: date, end: date, end_defaulted: bool) -> None:
    timestamps = data["timestamps"]
    # `timestamps` can be long, so it's summarised; every other field is printed in full.
    print(_dump({k: v for k, v in data.items() if k not in ("data-files", "timestamps")}))
    print(_range_line(start, end, end_defaulted))
    truncated = len(timestamps) < data["version-count"]
    print(f"timestamps:      {len(timestamps)}" + (f", {timestamps[0]} .. {timestamps[-1]}" if timestamps else "")
          + (f" (truncated, version-count {data['version-count']})" if truncated else ""))
    monthly, daily, other = _bundle_ranges(data["data-files"])
    print(f"monthly bundles: {monthly}")
    print(f"daily bundles:   {daily}")
    if other:
        print(f"{len(other)} bundle(s) with period other than M/D:")
        for b in other:
            print(_dump(b))


def _brief_coverage(data: dict) -> str:
    """One-line summary: version count and bundle ranges. Bundles with a period
    other than M/D are counted here; the full (non-brief) output prints them."""
    monthly, daily, other = _bundle_ranges(data["data-files"])
    line = f"versions {data['version-count']} | monthly: {monthly} | daily: {daily}"
    return line + (f" | {len(other)} bundle(s) with other period (see full output)" if other else "")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m hkdata.discover", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sd = sub.add_parser("search-datasets", help="relevance-ranked search over dataset titles/descriptions")
    sd.add_argument("keyword", help='free text; not substring-matched ("rain" found 0, "rainfall" 4), so try several words')
    sd.add_argument("--brief", action="store_true",
                    help="one line per dataset: id | provider | name | format (default: full JSON)")
    sd.add_argument("--limit", type=int, default=12, help="results per request; default 12, the website's page size")
    sd.add_argument("--offset", type=int, default=0)
    sd.add_argument("--page", type=int, help="1-based; overrides --offset if both are given")
    adv = sd.add_argument_group("advanced", "usually leave unset: the defaults match the website's own search box. "
                                "All values: search-params [parameters|category|provider|format]")
    adv.add_argument("--lang", default="en", help="en (default), tc or sc")
    adv.add_argument("--search-content", action="store_true",
                     help="also match resource content; noisy in tests (rainstorm -> library RSS, job ads)")
    adv.add_argument("--category", nargs="+", help="category ID(s), e.g. transport")
    adv.add_argument("--provider", nargs="+",
                     help='provider ID(s), e.g. hk-td; with keyword "" lists all of a provider\'s datasets')
    adv.add_argument("--format", nargs="+", help="lower-case file format(s), e.g. xml csv")

    sp = sub.add_parser("search-params", help="every search-datasets parameter with its values")
    sp.add_argument("section", nargs="?", choices=list(_PARAM_SECTIONS), help="print only this section (default: all)")

    sf = sub.add_parser("search-files", help="keyword search over the Historical Archive's file list")
    sf.add_argument("keyword")
    sf.add_argument("--provider", help="e.g. hk-td, hk-hko")
    sf.add_argument("--category", help="e.g. transport, climate-and-weather")

    d = sub.add_parser("dataset", help="list every resource under a known dataset id")
    d.add_argument("dataset_id", help="the slug from the dataset's data.gov.hk URL")
    d.add_argument("--lang", default="en", help="en (default), tc or sc")

    c = sub.add_parser("coverage", help="summarise a resource's archive coverage")
    target = c.add_mutually_exclusive_group(required=True)
    target.add_argument("url", nargs="?", help="a resource's file URL")
    target.add_argument("--dataset", metavar="DATASET_ID",
                        help="every resource of this dataset; a resource the archive rejects "
                             "(e.g. 404, not archived) shows the API error and the rest continue")
    c.add_argument("--start", type=date.fromisoformat, default=EARLIEST)
    c.add_argument("--end", type=date.fromisoformat, help="default: yesterday")
    c.add_argument("--brief", action="store_true",
                   help="one line per resource: versions and bundle ranges, or the API error "
                        "(default: every response field)")

    args = parser.parse_args()

    if args.command == "search-datasets":
        data = search_datasets(args.keyword, args.limit, args.offset, args.page, lang=args.lang,
                               search_content=args.search_content,
                               category=args.category, provider=args.provider, format=args.format)
        datasets = data["datasets"]
        for ds in datasets:
            if args.brief:
                # names can contain line breaks; collapse whitespace to keep one line per dataset
                name = " ".join(ds["name"][args.lang].split())
                print(f"{ds['id']} | {ds['provider']} | {name} | {','.join(ds['format'])}")
            else:
                print(_dump(ds))
        print(_dump({k: v for k, v in data.items() if k != "datasets"}))
        offset = (args.page - 1) * args.limit if args.page is not None else args.offset
        shown = f"{offset + 1}-{offset + len(datasets)}" if datasets else "0"
        print(f"showing {shown} of {data['total']} dataset(s)")
    elif args.command == "search-params":
        text = search_params()
        print(text if args.section is None else _params_section(text, args.section))
    elif args.command == "search-files":
        data = search_files(args.keyword, args.provider, args.category)
        for f in data["files"]:
            print(_dump(f))
        print(_dump({k: v for k, v in data.items() if k != "files"}))
        print(f"{len(data['files'])} resource(s)")
    elif args.command == "dataset":
        print(_dump(dataset(args.dataset_id, args.lang)))
    elif args.command == "coverage":
        end = args.end if args.end is not None else _yesterday()
        if args.url is not None:
            data = coverage(args.url, args.start, end)
            if args.brief:
                print(_range_line(args.start, end, args.end is None))
                print(_brief_coverage(data))
            else:
                _print_coverage(data, args.start, end, args.end is None)
            return
        resources = dataset(args.dataset)["result"]["resources"]
        if args.brief:
            print(_range_line(args.start, end, args.end is None))
        failed = 0
        for i, res in enumerate(resources, 1):
            head = f"[{i}/{len(resources)}] {res['name']} | {res['url']}"
            if not args.brief:
                print(f"== [{i}/{len(resources)}] {res['name']}\n   {res['url']}")
            try:
                data = coverage(res["url"], args.start, end)
            except requests.HTTPError as exc:
                # One resource's error must not hide the others; it's printed (brief: status
                # and body, whitespace collapsed; full: whole message) and reflected in the exit status.
                failed += 1
                if args.brief:
                    print(f"{head} | coverage error: {exc.response.status_code} {' '.join(exc.response.text.split())}")
                else:
                    print(f"coverage error:\n{exc}")
                continue
            if args.brief:
                print(f"{head} | {_brief_coverage(data)}")
            else:
                _print_coverage(data, args.start, end, args.end is None)
        print(f"{len(resources)} resource(s), {failed} with a coverage error")
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
