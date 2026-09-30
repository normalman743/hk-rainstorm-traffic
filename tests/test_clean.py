import zipfile

import pytest

from src.clean.files import extract, merge_identical

FOLDER = "https%3A%2F%2Fresource.data.one.gov.hk%2Ftd%2Ftraffic-detectors%2F/"


def _bundle(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members:
            z.writestr(FOLDER + name, data)
    return path


def _restore(folder, resource="rawSpeedVol-all.xml"):
    """Expand merged names back into the original (name, bytes) members, sorted."""
    out = []
    for p in folder.glob(f"*-{resource}"):
        stamp = p.name[: -len(resource) - 1]
        for t in stamp[9:].split("-"):
            out.append((f"{stamp[:8]}-{t}-{resource}", p.read_bytes()))
    return sorted(out)


def test_extract_and_merge_identical_are_lossless(tmp_path):
    members = [
        ("20250805-0007-rawSpeedVol-all.xml", b"period 00:00"),
        ("20250805-0009-rawSpeedVol-all.xml", b"period 00:01"),
        ("20250805-0010-rawSpeedVol-all.xml", b"period 00:00"),
        ("20250805-2056-rawSpeedVol-all.xml", b"period 20:50"),
        ("20250805-2056-rawSpeedVol-all.xml", b"period 20:50"),
        ("20250805-2059-rawSpeedVol-all.xml", b"period 20:50"),
    ]
    bundle = _bundle(tmp_path / "20250801.zip", members + [("20250806-0001-rawSpeedVol-all.xml", b"x")])
    out = tmp_path / "out"
    extract(bundle, out, days=["20250805"])
    assert (out / "20250805-2056-2056-rawSpeedVol-all.xml").exists()
    assert _restore(out) == sorted(members)

    renamed = merge_identical(out)
    assert sorted(p.name for p in renamed) == ["20250805-0007-0010-rawSpeedVol-all.xml",
                                               "20250805-2056-2056-2059-rawSpeedVol-all.xml"]
    assert sorted(p.name for p in out.iterdir()) == ["20250805-0007-0010-rawSpeedVol-all.xml",
                                                     "20250805-0009-rawSpeedVol-all.xml",
                                                     "20250805-2056-2056-2059-rawSpeedVol-all.xml"]
    assert _restore(out) == sorted(members)


def test_merge_identical_raises_across_dates(tmp_path):
    (tmp_path / "20250804-2359-rawSpeedVol-all.xml").write_bytes(b"a")
    (tmp_path / "20250805-0002-rawSpeedVol-all.xml").write_bytes(b"a")
    with pytest.raises(ValueError, match="different dates"):
        merge_identical(tmp_path)


def test_extract_raises_on_conflicting_member(tmp_path):
    bundle = _bundle(tmp_path / "b.zip", [
        ("20250805-2056-rawSpeedVol-all.xml", b"a"),
        ("20250805-2056-rawSpeedVol-all.xml", b"b"),
    ])
    with pytest.raises(ValueError, match="different content"):
        extract(bundle, tmp_path / "out")


S1_XML = (b'<?xml version="1.0" encoding="utf-8"?><raw_speed_volume_list><date>2025-08-05</date><periods>'
          b'<period><period_from>08:00:00</period_from><period_to>08:00:30</period_to><detectors>'
          b'<detector><detector_id>AID01101</detector_id><direction>South East</direction><lanes>'
          b'<lane><lane_id>Fast Lane</lane_id><speed>70</speed><occupancy>0</occupancy><volume>0</volume>'
          b'<s.d.>0</s.d.><valid>Y</valid></lane>'
          b'<lane><lane_id>Slow Lane</lane_id><speed>52</speed><occupancy/><volume>2</volume><valid>N</valid></lane>'
          b'</lanes></detector></detectors></period></periods></raw_speed_volume_list>')


def test_s1_parse_keeps_text_absent_and_empty():
    from src.clean.s1_parse import parse
    assert parse(S1_XML, "t") == [
        ("2025-08-05", "08:00:00", "08:00:30", "AID01101", "South East", 0, "Fast Lane", "70", "0", "0", "0", "Y"),
        ("2025-08-05", "08:00:00", "08:00:30", "AID01101", "South East", 1, "Slow Lane", "52", "", "2", None, "N"),
    ]


def test_s1_parse_raises_on_unknown_or_repeated_element():
    from src.clean.s1_parse import parse
    with pytest.raises(ValueError, match="unexpected <flow>"):
        parse(S1_XML.replace(b"<valid>N</valid>", b"<valid>N</valid><flow>1</flow>"), "t")
    with pytest.raises(ValueError, match="<speed> twice"):
        parse(S1_XML.replace(b"<speed>52</speed>", b"<speed>52</speed><speed>53</speed>"), "t")


S3_RAIN = ('</p>\nBetween 6:45 and 7:45 a.m., lightning was detected over all regions. The rainfall recorded in '
           'various regions were:<br/><br/>    <table border="0" cellspacing="0" cellpadding="0">\n'
           '    <tr><td>Islands District</td><td width="100" align="right">7 to 50&nbsp;mm;</td></tr>\n'
           '    <tr><td>Tuen Mun</td><td width="100" align="right">1&nbsp;mm.</td></tr>\n    </table><br/>')


def test_s3_rain_rows_as_written():
    from src.clean.s3_parse import rain_rows
    assert rain_rows(S3_RAIN, "t") == [("6:45 and 7:45 a.m.", "Islands District", "7", "50"),
                                       ("6:45 and 7:45 a.m.", "Tuen Mun", "1", None)]
    no_lightning = S3_RAIN.replace("lightning was detected over all regions. The", "the")
    assert rain_rows(no_lightning, "t") == rain_rows(S3_RAIN, "t")
    assert rain_rows("<p>At 8 a.m. at the Hong Kong Observatory</p>", "t") == []


def test_s3_rain_rows_raise_on_other_forms():
    from src.clean.s3_parse import rain_rows
    with pytest.raises(ValueError, match="another form"):
        rain_rows(S3_RAIN.replace("were:", "was:"), "t")
    with pytest.raises(ValueError, match="unexpected text"):
        rain_rows(S3_RAIN.replace("1&nbsp;mm.", "Trace&nbsp;mm."), "t")
    with pytest.raises(ValueError, match="2 times"):
        rain_rows(S3_RAIN + S3_RAIN, "t")


S13_XML = ('<?xml version="1.0" encoding="UTF-8"?><list><message><INCIDENT_NUMBER>IN-24-01</INCIDENT_NUMBER>'
           '<LOCATION_EN>Trade & Exhibition Centre &amp; &#26481;</LOCATION_EN><DISTRICT_EN></DISTRICT_EN>'
           '<ID>1</ID></message></list>').encode()


def test_s13_parse_keeps_bare_ampersand_as_written():
    from src.clean.s13_parse import FIELDS, parse
    rows, n_amp = parse(S13_XML, "t")
    assert n_amp == 1 and len(rows) == 1
    row = dict(zip(["position", *FIELDS], rows[0]))
    assert row["LOCATION_EN"] == "Trade & Exhibition Centre & 東"
    assert (row["INCIDENT_NUMBER"], row["DISTRICT_EN"], row["ID"], row["LATITUDE"]) == ("IN-24-01", "", "1", None)
    assert parse(S13_XML.replace(b"Trade & ", b"Trade "), "t")[1] == 0


def test_s13_parse_raises_on_other_errors():
    from src.clean.s13_parse import parse
    with pytest.raises(ValueError, match="t: "):
        parse(S13_XML.replace(b"&amp;", b"&nbsp;"), "t")
    with pytest.raises(ValueError, match="unexpected <item>"):
        parse(S13_XML.replace(b"<message>", b"<item>").replace(b"</message>", b"</item>"), "t")
    with pytest.raises(ValueError, match="<ID> twice"):
        parse(S13_XML.replace(b"<ID>1</ID>", b"<ID>1</ID><ID>2</ID>"), "t")


S11_XML = (b'<?xml version="1.0" encoding="utf-8"?><segment_speed_list xmlns:xsi="http://www.w3.org/2001/'
           b'XMLSchema-instance"><date>2025-08-05</date><time>08:01:00</time><irn_version>20221210</irn_version>'
           b'<segments><segment><segment_id>58280</segment_id><speed>65.3</speed><valid>Y</valid></segment>'
           b'<segment><segment_id>58736</segment_id><speed/></segment></segments></segment_speed_list>')


def test_s11_parse_keeps_text_absent_and_empty():
    from src.clean.s11_parse import _head_of_truncated, parse
    head = ("2025-08-05", "08:01:00", "20221210")
    assert parse(S11_XML, "t") == (head, [("58280", "65.3", "Y"), ("58736", "", None)])
    assert _head_of_truncated(S11_XML[:260], "t") == head
    with pytest.raises(ValueError, match="0 <irn_version>"):
        _head_of_truncated(S11_XML[:180], "t")


def test_s11_parse_raises_on_unknown_or_repeated_element():
    from src.clean.s11_parse import parse
    with pytest.raises(ValueError, match="unexpected <flow>"):
        parse(S11_XML.replace(b"<speed/>", b"<speed/><flow>1</flow>"), "t")
    with pytest.raises(ValueError, match="<time> twice"):
        parse(S11_XML.replace(b"<time>08:01:00</time>", b"<time>08:01:00</time><time>08:03:00</time>"), "t")


def _s7(body: bytes) -> bytes:
    from src.clean.s7_parse import HEADER
    return HEADER + b"\n" + body


S7_BODY = b"202508011612,202508011642,23.487,112.956,0.00\n202508011612,202508011642,23.487,112.976,00.1\n"


def test_s7_parse_keeps_text_as_written():
    from src.clean.s7_parse import malformed, parse
    assert malformed(_s7(S7_BODY), "t") is None
    assert parse(_s7(S7_BODY), "t").to_pylist() == [
        {"updated": "202508011612", "ending": "202508011642", "latitude": "23.487", "longitude": "112.956",
         "rainfall": "0.00"},
        {"updated": "202508011612", "ending": "202508011642", "latitude": "23.487", "longitude": "112.976",
         "rainfall": "00.1"}]


def test_s7_malformed_files_are_named_and_other_forms_raise():
    from src.clean.s7_parse import malformed
    assert malformed(_s7(S7_BODY[:-5]), "t").startswith("no final newline")
    assert malformed(_s7(S7_BODY + b"5.291,1.73\n"), "t").startswith("line 4: 2 fields")
    assert malformed(_s7(S7_BODY + b"\n"), "t").startswith("line 4: 1 fields")
    with pytest.raises(ValueError, match="header"):
        malformed(S7_BODY, "t")
    with pytest.raises(ValueError, match="'\"'"):
        malformed(_s7(S7_BODY.replace(b"0.00", b'"0.00"')), "t")


def test_versions_parse_reads_by_bom_and_keeps_values_as_written():
    import codecs
    from src.clean.versions_parse import decode, parse
    text = "AID_ID_Number\tRoad_EN\r\nAID20011\tMut Wah Street \r\n"
    assert decode(codecs.BOM_UTF16_LE + text.encode("utf-16-le")) == (text, "UTF-16 LE BOM")
    assert decode(codecs.BOM_UTF8 + text.encode()) == (text, "UTF-8 BOM")
    assert parse(text, "t") == (["AID_ID_Number", "Road_EN"], [["AID20011", "Mut Wah Street "]], "\t")
    assert parse('route,irn_id\n"9, A",375', "t") == (["route", "irn_id"], [["9, A", "375"]], ",")


def test_versions_parse_raises_on_bad_rows_and_bytes():
    from src.clean.versions_parse import decode, parse
    with pytest.raises(ValueError, match="data row 1 has 3 fields"):
        parse("a,b\n1,2,3\n", "t")
    with pytest.raises(ValueError, match="data row 2 has 0 fields"):
        parse("a,b\n1,2\n\n", "t")
    with pytest.raises(ValueError, match="repeated name"):
        parse("a,a\n1,2\n", "t")
    with pytest.raises(UnicodeDecodeError):
        decode(b"Road\ncaf\xe9\n")


def test_extract_raises_on_missing_day(tmp_path):
    bundle = _bundle(tmp_path / "b.zip", [("20250805-0007-rawSpeedVol-all.xml", b"a")])
    with pytest.raises(ValueError, match="20250807"):
        extract(bundle, tmp_path / "out", days=["20250807"])


# The samples below are lines copied from the raw files (file:line in the comments). The error
# cases are made up: the files have none.
RSTORM = ("A\t1998\t4\t12\t5\t15\t1998\t4\t12\t8\t0\t2\t45\t\n"  # rstorm.dat:1, ends with a tab
          "A\t2026\t8\t31\t12\t25\t2026\t8\t31\t14\t5\t01\t40\n"  # rstorm.dat:974
          "UUUU\n").encode()                                       # rstorm.dat:975
TC = ("0\tMSN\tX\t0\tN\t915 \t12\t3\t2005\tX\t445 \t13\t3\t2005\tX\t1930\n"           # tc.dat:1696
      "200603\tT\tPRAPIROON\t1\tX\t540\t4\t8\t2006\tX\t1540\t4\t8\t2006\tX\t1000\t\t\n"  # tc.dat:1733
      "202102\tTD/TD\tno name(E)(5-6Jul2021)/ no name(W)(5-8Jul2021)\t1\tX\t415\t6\t7\t2021\tX"
      "\t1410\t7\t7\t2021\tX\t3355\n"                                                  # tc.dat:2290
      "UUUU\n").encode()                                                               # tc.dat:2513


def test_signals_parse_keeps_real_lines_as_written():
    from src.clean.signals_parse import parse
    rows = parse(RSTORM, 13, "t")
    assert rows[0] == (1, "A", "1998", "4", "12", "5", "15", "1998", "4", "12", "8", "0", "2", "45", 1)
    assert rows[1][-3:] == ("01", "40", 0)
    assert rows[2] == (3, "UUUU", *[None] * 12, 0)
    rows = parse(TC, 16, "t")
    assert (rows[0][2], rows[0][6], rows[0][11], rows[0][-1]) == ("MSN", "915 ", "445 ", 0)
    assert rows[1][-2:] == ("1000", 2)
    assert rows[2][2:4] == ("TD/TD", "no name(E)(5-6Jul2021)/ no name(W)(5-8Jul2021)")
    assert rows[3] == (4, "UUUU", *[None] * 15, 0)


def test_signals_parse_raises_on_bad_lines():
    from src.clean.signals_parse import parse
    with pytest.raises(ValueError, match="line 1 has 3 fields"):
        parse(b"A\t2026\t8\n", 13, "t")
    with pytest.raises(ValueError, match="line 2 has 14 fields"):
        parse(RSTORM.replace(b"\t01\t40\n", b"\t01\t40\tX\n"), 13, "t")
    with pytest.raises(ValueError, match="no final newline"):
        parse(RSTORM[:-1], 13, "t")
    with pytest.raises(ValueError, match="contains"):
        parse(RSTORM.replace(b"\n", b"\r\n"), 13, "t")


def _s8(days: str) -> bytes:
    from src.clean.s8_parse import HEADER, LEGEND, TITLE
    return "\n".join(["﻿" + TITLE[0], TITLE[1], ",".join(HEADER), *days.splitlines(), "", *LEGEND, ""]).encode()


S8_DAYS = "1884,3,1,0.0,C\n1884,12,6,Trace,C\n1900,2,29,***,"  # daily_HKO_RF_ALL.csv:4, 284, 5847


def test_s8_parse_keeps_days_as_written():
    from src.clean.s8_parse import parse
    assert parse(_s8(S8_DAYS), "t") == [
        (4, "1884", "3", "1", "0.0", "C"), (5, "1884", "12", "6", "Trace", "C"), (6, "1900", "2", "29", "***", "")]


def test_s8_parse_raises_on_changed_text_or_fields():
    from src.clean.s8_parse import parse
    with pytest.raises(ValueError, match="line 4 has 4 fields"):
        parse(_s8("1884,3,1,0.0"), "t")
    with pytest.raises(ValueError, match="last lines"):
        parse(_s8(S8_DAYS).replace("Trace means".encode(), b"Trace is"), "t")
    with pytest.raises(ValueError, match="first lines"):
        parse(_s8(S8_DAYS).replace("年/Year".encode(), b"Year"), "t")


# 20250501.zip, 20250519-1025-en.json: the calendar and its first event, values as written
S6_CALENDAR = {"prodid": "-//1823 Contact Centre, HKSARG//Hong Kong Public Holidays//EN", "version": "2.0",
               "calscale": "GREGORIAN", "x-wr-timezone": "Asia/Hong_Kong",
               "x-wr-calname": "Hong Kong Public Holidays", "x-wr-caldesc": "Hong Kong Public Holidays"}
S6_EVENT = {"dtstart": ["20240101", {"value": "DATE"}], "dtend": ["20240102", {"value": "DATE"}],
            "dtstamp": "20250506T032740Z", "transp": "TRANSPARENT", "uid": "20240101@1823.gov.hk",
            "summary": "The first day of January"}


def _s6(event: dict) -> bytes:
    import json
    return b"\xef\xbb\xbf" + json.dumps({"vcalendar": [{**S6_CALENDAR, "vevent": [event]}]}, indent="\t").encode()


def test_s6_parse_splits_values_and_parameters():
    from src.clean.s6_parse import parse
    assert parse(_s6(S6_EVENT), "t") == [
        (0, *S6_CALENDAR.values(), "20240101", '{"value": "DATE"}', "20240102", '{"value": "DATE"}',
         "20250506T032740Z", "TRANSPARENT", "20240101@1823.gov.hk", "The first day of January")]
    before_2025_05 = {k: v for k, v in S6_EVENT.items() if k != "dtstamp"}
    assert parse(_s6(before_2025_05), "t")[0][11] is None


def test_s6_parse_raises_on_unknown_keys_forms_and_repeats():
    from src.clean.s6_parse import parse
    with pytest.raises(ValueError, match="repeated key"):
        parse(b'{"vcalendar": [], "vcalendar": []}', "t")
    with pytest.raises(ValueError, match="top level"):
        parse(b'{"vcalendar": [{}, {}]}', "t")
    with pytest.raises(ValueError, match="unknown keys"):
        parse(_s6({**S6_EVENT, "rrule": "FREQ=YEARLY"}), "t")
    with pytest.raises(ValueError, match="only dtstart, dtend may have parameters"):
        parse(_s6({**S6_EVENT, "summary": ["The first day of January", {"language": "en"}]}), "t")
    with pytest.raises(ValueError, match=r"is not \[value"):
        parse(_s6({**S6_EVENT, "dtstart": "20240101"}), "t")


def _l2_s1_con(blocks):
    """DuckDB with views l1, l1_all, fetch from blocks = [(date, period_from, detector, direction,
    [(lane_id, speed, volume, occupancy, sd, valid), ...]), ...]; one file per block, fetched 5 min later."""
    import datetime as dt

    import duckdb
    import pandas as pd
    rows, fetch = [], []
    for i, (date, pfrom, det, direction, lanes) in enumerate(blocks):
        t0 = dt.datetime.strptime(pfrom, "%H:%M:%S")
        pto = (t0 + dt.timedelta(seconds=30)).strftime("%H:%M:%S")
        day = dt.date.fromisoformat(date) + dt.timedelta(days=pfrom in ("00:00:00", "00:00:30"))
        fetch.append(("b.zip", i, dt.datetime.combine(day, t0.time()) + dt.timedelta(minutes=5)))
        for pos, lane in enumerate(lanes):
            rows.append(("b.zip", i, date, pfrom, pto, det, direction, pos, *lane))
    con = duckdb.connect()
    l1 = pd.DataFrame(rows, columns=["bundle", "index", "date", "period_from", "period_to", "detector_id",
                                     "direction", "lane_position", "lane_id", "speed", "volume",
                                     "occupancy", "sd", "valid"])
    l1["index"] = l1["index"].astype("int32")
    f = pd.DataFrame(fetch, columns=["bundle", "index", "fetch_time"])
    con.register("l1_df", l1)
    con.register("fetch_df", f)
    con.sql("create view l1 as select * from l1_df")
    con.sql("create view l1_all as select * from l1_df")
    con.sql("create view fetches as select * from fetch_df")
    return con


def _lanes(*names, speed="80", volume="4", occupancy="5", sd="1.5", valid="Y"):
    return [(n, speed, volume, occupancy, sd, valid) for n in names]


def test_l2_s1_applies_the_rules():
    from src.clean.l2_s1 import clean
    fs = ("Fast Lane", "Slow Lane")
    blocks = [
        # D6: 00:00 carries the previous day; D3: trailing space; D21: occupancy -1 with volume 0.
        ("2025-06-30", "00:00:00", "AID00001", "North ", [("Fast Lane", "70", "0", "-1", "0", "Y"),
                                                         ("Slow Lane", "60", "2", "3", "1", "Y")]),
        ("2025-07-01", "00:10:00", "AID00001", "North ", _lanes(*fs)),
        ("2025-07-01", "00:10:30", "AID00001", "North ", _lanes("Fast Lane")),  # D14
        ("2025-07-01", "00:11:00", "AID00001", "North ", _lanes(*fs)),
        # D4 and D12
        ("2025-07-01", "00:10:00", "TDS90026", "West", _lanes("Fast Lane", "Middle Lane", "Middle Lane", "Slow Lane")),
        ("2025-07-01", "00:10:30", "TDS90026", "West", _lanes("Fast Lane", "Middle Lane", "Slow Lane")),
        ("2025-07-01", "00:11:00", "TDS90026", "West", _lanes("Fast Lane", "Middle Lane", "Middle Lane", "Slow Lane")),
        # D13: two complete blocks give the ratios for hour 0, one block misses Slow Lane
        ("2025-07-01", "00:10:00", "TDS90036", "North West",
         [("Fast Lane", "90", "4", "4", "2", "Y"), ("Middle Lane 1", "80", "3", "3", "2", "Y"),
          ("Middle Lane 2", "70", "3", "3", "2", "Y"), ("Slow Lane", "40", "1", "2", "1", "Y")]),
        ("2025-07-01", "00:10:30", "TDS90036", "North West",
         [("Fast Lane", "90", "4", "4", "2", "Y"), ("Middle Lane 1", "80", "3", "3", "2", "Y"),
          ("Middle Lane 2", "70", "3", "3", "2", "Y"), ("Slow Lane", "64", "1", "2", "1", "Y")]),
        ("2025-07-01", "00:11:00", "TDS90036", "North West",
         [("Fast Lane", "100", "8", "8", "4", "Y"), ("Middle Lane 1", "80", "6", "6", "4", "Y"),
          ("Middle Lane 2", "60", "6", "6", "4", "N")]),
        # D5
        ("2024-05-30", "08:24:30", "AID02215", "South", _lanes(*fs)),
        ("2024-05-30", "08:25:00", "AID02215", "South", [("Fast Lane", "97", "5", "2", "0", "Y"),
                                                          ("Fast Lane", "92", "4", "2", "0", "Y"),
                                                          ("Slow Lane", "105", "1", "0", "0", "Y"),
                                                          ("Slow Lane", "86", "7", "4", "0", "Y")]),
        # D16
        ("2025-07-01", "00:10:00", "AID09115", None, _lanes(*fs)),
        ("2025-07-01", "00:10:30", "AID09115", "East", _lanes(*fs)),
    ]
    con = _l2_s1_con(blocks)
    counts = {(r, w): n for r, w, n in clean(con, "202507")}
    l2 = con.sql("select * from l2").df()

    a = l2[l2.detector_id == "AID00001"].sort_values(["time", "lane_id"])
    assert str(a.time.iloc[0]) == "2025-07-01 00:00:00" and set(a.direction) == {"North"}
    assert a.occupancy.iloc[0] == 0 and a.l2_rule.iloc[0] == "D21"
    assert "2025-07-01 00:10:30" not in set(a.time.astype(str))
    t26 = l2[l2.detector_id == "TDS90026"]
    assert set(t26.lane_id) == {"Fast Lane", "Middle Lane 1", "Middle Lane 2", "Slow Lane"}
    assert len(t26) == 8
    slow = l2[(l2.detector_id == "TDS90036") & (l2.l2_rule == "D13")]
    assert len(slow) == 1 and slow.lane_id.iloc[0] == "Slow Lane"
    # volume: 20 x (2 / 20); occupancy: 20 x (4 / 20); speed: 80 x median(40/80, 64/80); sd: 4 x 0.5
    assert slow[["volume", "occupancy", "speed", "sd"]].iloc[0].tolist() == pytest.approx([2, 4, 52, 2])
    assert not slow.valid.iloc[0]
    d5 = l2[(l2.detector_id == "AID02215") & (l2.l2_rule == "D5")].set_index("lane_id")
    assert d5.loc["Fast Lane", "speed"] == 94.5 and d5.loc["Slow Lane", "volume"] == 4
    assert set(l2[l2.detector_id == "AID09115"].direction) == {"East"}
    assert counts[("D16", "rows with direction filled")] == 2
    assert counts[("D14", "blocks dropped")] == 1 and counts[("D12", "blocks dropped")] == 1
    assert counts[("D6", "rows re-dated (00:00:00, 00:00:30)")] == 2
    assert counts[("L2", "rows out")] == len(l2) == 6 + 8 + 12 + 4 + 4


def test_l2_s1_raises_on_what_no_rule_covers():
    from src.clean.l2_s1 import clean
    base = ("2025-07-01", "00:00:30", "AID00001", "North")
    with pytest.raises(ValueError, match="not covered by D4 / D5"):
        clean(_l2_s1_con([(*base, _lanes("Fast Lane", "Fast Lane"))]), "202507")
    with pytest.raises(ValueError, match="no rule"):
        clean(_l2_s1_con([(*base, _lanes("Fast Lane", "Slow Lane")),
                          ("2025-07-01", "00:01:00", "AID00001", "North", _lanes("Fast Lane", "Slow Lane")),
                          ("2025-07-01", "00:01:30", "AID00001", "North", _lanes("Fast Lane", "Middle Lane"))]),
              "202507")
    with pytest.raises(ValueError, match="negative occupancy"):
        clean(_l2_s1_con([(*base, [("Fast Lane", "70", "3", "-1", "0", "Y")])]), "202507")


def test_l2_s3_period_end_dates_by_bulletin_and_raises_on_other_forms():
    from datetime import datetime

    from src.clean.l2_s3 import period_end

    assert period_end("11:45 p.m. and 12:45 a.m.", datetime(2025, 8, 5, 1, 0), "x") == datetime(2025, 8, 5, 0, 45)
    assert period_end("6:45 and 7:45 a.m.", datetime(2025, 8, 5, 8, 2), "x") == datetime(2025, 8, 5, 7, 45)
    with pytest.raises(ValueError, match="not one hour"):
        period_end("5:45 and 7:45 a.m.", datetime(2025, 8, 5, 8, 2), "x")
    with pytest.raises(ValueError, match="another form"):
        period_end("6:30 and 7:30 a.m.", datetime(2025, 8, 5, 8, 2), "x")


def test_l2_ref_signal_times_and_daily_rain():
    from datetime import datetime

    import pandas as pd

    from src.clean.l2_ref import daily, rainstorm, tropical

    s4 = pd.DataFrame([["1", "A", "2000", "4", "2", "22", "15", "2000", "4", "2", "24", "00", "1", "45"],
                       ["2", "UUUU"] + [None] * 12],
                      columns=["line", "colour", "start_year", "start_month", "start_day", "start_hour",
                               "start_minute", "end_year", "end_month", "end_day", "end_hour", "end_minute",
                               "duration_hours", "duration_minutes"])
    out, n2400 = rainstorm(s4)
    assert out.end.tolist() == [datetime(2000, 4, 3)] and n2400 == 1 and not out.provisional.any()
    with pytest.raises(ValueError, match="duration"):
        rainstorm(s4.assign(duration_minutes="50"))

    cols = ["line", "cyclone", "intensity", "name", "signal", "direction", "start_time", "start_day",
            "start_month", "start_year", "start_flag", "end_time", "end_day", "end_month", "end_year",
            "end_flag", "duration", "trailing_tabs"]
    s5 = pd.DataFrame([[1, "195306", "TST", "BETTY", "3", "*", "1040", "31", "10", "1953", "S",
                        "2155", "1", "11", "1953", "X", "3615", 0],
                       [2, "0", "MSN", "X", "0", "ENE", "915 ", "3 ", "1", "2005", "X",
                        "945", "3", "1", "2005", "X", "30", 0]], columns=cols)
    out, msn, spaced, n2400, summer = tropical(s5)
    assert out.start.tolist() == [datetime(1953, 10, 31, 9, 40)] and (msn, spaced, summer) == (1, 2, 1)
    with pytest.raises(ValueError, match="flag"):
        tropical(s5.assign(start_flag="Q"))

    s8 = pd.DataFrame({"年/Year": ["1900", "2025", "2025"], "月/Month": ["2", "8", "8"], "日/Day": ["29", "4", "5"],
                       "數值/Value": ["***", "Trace", "352.3"], "數據完整性/data Completeness": ["", "C", "C"],
                       "line": [1, 2, 3]})
    out, left = daily(s8)
    assert out.rain_mm.tolist() == [0.0, 352.3] and out.trace.tolist() == [True, False] and left == 1
    with pytest.raises(ValueError, match="values"):
        daily(s8.assign(**{"數值/Value": ["***", "#", "1.0"]}))


def test_l3_episodes_and_month_edges():
    from datetime import datetime

    import pandas as pd

    from src.l3 import Options, _episodes, _month_edge, options

    s4 = pd.DataFrame({"start": [datetime(2025, 8, 5, 5, 50), datetime(2025, 8, 5, 3), datetime(2025, 8, 5, 22, 55)],
                       "end": [datetime(2025, 8, 5, 17, 5), datetime(2025, 8, 5, 5, 50), datetime(2025, 8, 6, 0, 30)],
                       "level": [3, 1, 1]})
    e = _episodes(s4)
    assert e.episode.tolist() == [0, 0, 1]
    assert e.episode_start.tolist() == [datetime(2025, 8, 5, 3)] * 2 + [datetime(2025, 8, 5, 22, 55)]
    assert _month_edge(datetime(2025, 8, 31, 22, 45)) and _month_edge(datetime(2025, 7, 1, 0, 30))
    assert not _month_edge(datetime(2025, 8, 31, 22, 30)) and not _month_edge(datetime(2025, 8, 30, 23, 0))
    assert options(["minutes=60", "speed_agg=mean"]).name() == "speed_agg=mean__minutes=60"
    assert Options().name() == "default"
