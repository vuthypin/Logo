import numpy as np
import pandas as pd

from cac40_app.data import INDEX_TICKER
from scripts.export_data import build_payload


def test_build_payload_structure():
    constituents = pd.DataFrame({"ticker": ["A.PA", "B.PA"], "name": ["Alpha", "Beta"], "sector": ["X", "Y"]})
    idx = pd.bdate_range("2025-01-01", "2026-10-23")
    closes = pd.DataFrame(
        {"A.PA": np.linspace(100, 200, len(idx)), "B.PA": np.linspace(100, 50, len(idx)), INDEX_TICKER: 7000.0},
        index=idx,
    )
    closes.loc[closes.index >= "2026-07-29", "A.PA"] *= 1.05
    calendar = pd.DataFrame(
        {
            "ticker": ["A.PA", "A.PA"],
            "date": pd.to_datetime(["2026-07-29 07:00", "2026-11-05 07:00"]).tz_localize("Europe/Paris"),
            "source": "test",
        }
    )
    now = pd.Timestamp("2026-10-24 08:00", tz="Europe/Paris")
    p = build_payload(constituents, closes, calendar, now)

    assert p["last_session"] == "2026-10-23"
    assert len(p["dates"]) == len(p["index"]["closes"]) == len(p["stocks"][0]["closes"])
    a = next(s for s in p["stocks"] if s["ticker"] == "A.PA")
    assert a["next_earnings"] == "2026-11-05"
    assert a["events"][0]["reaction"] > 4
    assert a["perf"]["1 an"] > 0
    assert p["upcoming"] == [{"ticker": "A.PA", "name": "Alpha", "date": "2026-11-05", "eps_estimate": None, "avg_abs": a["stats"]["avg_abs"]}]
