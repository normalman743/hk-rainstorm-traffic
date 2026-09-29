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
        ("2025-08-05", "08:00:00", "08:00:30", "AID01101", "South East", "Fast Lane", "70", "0", "0", "0", "Y"),
        ("2025-08-05", "08:00:00", "08:00:30", "AID01101", "South East", "Slow Lane", "52", "", "2", None, "N"),
    ]


def test_s1_parse_raises_on_unknown_or_repeated_element():
    from src.clean.s1_parse import parse
    with pytest.raises(ValueError, match="unexpected <flow>"):
        parse(S1_XML.replace(b"<valid>N</valid>", b"<valid>N</valid><flow>1</flow>"), "t")
    with pytest.raises(ValueError, match="<speed> twice"):
        parse(S1_XML.replace(b"<speed>52</speed>", b"<speed>52</speed><speed>53</speed>"), "t")


def test_extract_raises_on_missing_day(tmp_path):
    bundle = _bundle(tmp_path / "b.zip", [("20250805-0007-rawSpeedVol-all.xml", b"a")])
    with pytest.raises(ValueError, match="20250807"):
        extract(bundle, tmp_path / "out", days=["20250807"])
