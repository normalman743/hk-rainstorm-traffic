import io
import zipfile
from datetime import datetime

import pytest

from src.download.archive import extract_member
from src.download.warnings import group_episodes, parse_rainstorm, parse_tc

RSTORM = (
    "A\t2025\t8\t4\t21\t45\t2025\t8\t4\t23\t10\t01\t25\t\n"
    "R\t2025\t8\t4\t23\t10\t2025\t8\t5\t1\t0\t01\t50\t\n"
    "B\t2025\t8\t5\t1\t0\t2025\t8\t5\t4\t30\t03\t30\t\n"
    "A\t2019\t5\t20\t22\t5\t2019\t5\t20\t24\t0\t01\t55\n"
    "\n"
    "UUUU\n"
    "A\t2026\t8\t31\t12\t25\t2026\t8\t31\t14\t5\t01\t40\n"
)

TC = (
    "﻿194601\tT\tNIL\t1\tX\t1610\t16\t7\t1946\tS\t1215\t17\t7\t1946\tS\t2005\n"
    "0\tMSN\tX\t0\tE\t2300\t12\t9\t2026\tX\t1345\t13\t9\t2026\tX\t1445\n"
    "202603\tSuperT\tSAUDEL\t8\tNE\t10\t31\t8\t2026\tX\t2400\t31\t8\t2026\tX\t2350\n"
    "UUUU\n"
)


def test_parse_rainstorm_handles_midnight_and_provisional():
    signals = parse_rainstorm(RSTORM)
    assert [s.level for s in signals] == [1, 1, 2, 3, 1]  # sorted by start
    assert signals[0].end == datetime(2019, 5, 21, 0, 0)  # "24:00" rolls over
    assert signals[-1].provisional and not signals[0].provisional


def test_group_episodes_chains_upgrades():
    episodes = group_episodes(parse_rainstorm(RSTORM))
    assert len(episodes) == 3
    black = episodes[1]
    assert (black.start, black.end) == (datetime(2025, 8, 4, 21, 45), datetime(2025, 8, 5, 4, 30))
    assert black.max_level == 3 and black.n_signals == 3


def test_parse_tc_skips_monsoon_rows_and_pads_hhmm():
    signals = parse_tc(TC)
    assert len(signals) == 2
    assert signals[0].name == "" and signals[0].start == datetime(1946, 7, 16, 16, 10)
    saudel = signals[1]
    assert (saudel.signal, saudel.direction) == ("8", "NE")
    assert saudel.start == datetime(2026, 8, 31, 0, 10)
    assert saudel.end == datetime(2026, 9, 1, 0, 0)


@pytest.mark.parametrize("method", [zipfile.ZIP_DEFLATED, zipfile.ZIP_STORED])
def test_extract_member_from_raw_bytes(method):
    buf = io.BytesIO()
    payload = b"<raw_speed_volume_list>" + b"x" * 5000 + b"</raw_speed_volume_list>"
    with zipfile.ZipFile(buf, "w", compression=method) as zf:
        zf.writestr("a/20250805-0000-rawSpeedVol-all.xml", b"first")
        zf.writestr("a/20250805-0002-rawSpeedVol-all.xml", payload)
    raw = buf.getvalue()
    info = zipfile.ZipFile(io.BytesIO(raw)).infolist()[1]

    assert extract_member(raw[info.header_offset:], info) == payload
    # Too few bytes -> None so the caller fetches a bigger range.
    assert extract_member(raw[info.header_offset:info.header_offset + 60], info) is None
