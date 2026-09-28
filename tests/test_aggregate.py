import pandas as pd
import pytest

from src.aggregate import aggregate


def test_aggregate_naive_vs_clean():
    t0, t1 = pd.Timestamp("2025-08-05 08:00:00"), pd.Timestamp("2025-08-05 08:14:30")
    lanes = pd.DataFrame({
        "time": [t0, t0, t0, t1, pd.Timestamp("2025-08-05 08:15:00")],
        "detector_id": pd.Categorical(["A", "A", "A", "A", "A"]),
        "lane": pd.Categorical(["Fast", "Slow", "Middle", "Fast", "Fast"]),
        "speed": pd.array([60, 40, 70, 200, 50], dtype="Int16"),     # 70 = placeholder, 200 = invalid
        "occupancy": pd.array([5, 10, 0, 3, 4], dtype="Int16"),
        "volume": pd.array([3, 1, 0, 2, 4], dtype="Int16"),
        "sd": [1.0, 1.0, 0.0, 1.0, 1.0],
        "valid": pd.Categorical(["Y", "Y", "Y", "N", "Y"]),
    })
    out = aggregate(lanes)
    first = out.iloc[0]
    assert len(out) == 2 and first["t_bin"] == t0
    assert (first["n_readings"], first["n_periods"], first["n_invalid"], first["n_zero_volume"],
            first["n_speed_over_130"]) == (4, 2, 1, 1, 1)
    assert first["speed_naive"] == pytest.approx((60 + 40 + 70 + 200) / 4)
    assert first["speed_clean"] == pytest.approx((60 * 3 + 40 * 1) / 4)   # drops placeholder and invalid
    assert first["volume_sum"] == 4 and first["occupancy_mean"] == pytest.approx(5)
    assert out.iloc[1]["speed_clean"] == pytest.approx(50)
