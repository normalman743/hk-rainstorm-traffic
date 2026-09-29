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


def test_extract_raises_on_missing_day(tmp_path):
    bundle = _bundle(tmp_path / "b.zip", [("20250805-0007-rawSpeedVol-all.xml", b"a")])
    with pytest.raises(ValueError, match="20250807"):
        extract(bundle, tmp_path / "out", days=["20250807"])
