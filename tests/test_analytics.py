import numpy as np
import pandas as pd
import pytest

from cac40_app.analytics import (
    classify_timing,
    compute_performance,
    earnings_reaction,
    period_start,
    reaction_summary,
    top_flop,
)


@pytest.fixture
def closes():
    idx = pd.bdate_range("2026-01-01", "2026-03-31")
    return pd.DataFrame(
        {
            "UP": np.linspace(100, 150, len(idx)),
            "DOWN": np.linspace(100, 80, len(idx)),
            "FLAT": 100.0,
        },
        index=idx,
    )


def test_period_start_ytd_uses_last_close_of_previous_year():
    assert period_start(pd.Timestamp("2026-10-23"), "Depuis le 1er janvier") == pd.Timestamp("2025-12-31")


def test_period_start_one_day_is_previous_close():
    assert period_start(pd.Timestamp("2026-10-23"), "1 jour") == pd.Timestamp("2026-10-22")


def test_compute_performance_sorted(closes):
    perf = compute_performance(closes, pd.Timestamp("2025-12-31"))
    assert list(perf["ticker"]) == ["UP", "FLAT", "DOWN"]
    assert perf.loc[0, "perf_pct"] == pytest.approx(50)
    assert perf.loc[2, "perf_pct"] == pytest.approx(-20)


def test_one_day_performance_uses_previous_session(closes):
    end = closes.index[-1]
    perf = compute_performance(closes, period_start(end, "1 jour"), end).set_index("ticker")
    expected = (closes["UP"].iloc[-1] / closes["UP"].iloc[-2] - 1) * 100
    assert perf.loc["UP", "perf_pct"] == pytest.approx(expected)


def test_top_flop():
    perf = pd.DataFrame({"ticker": list("abcdef"), "perf_pct": [5, -3, 10, 0, -8, 2]})
    top, flop = top_flop(perf, 2)
    assert list(top["ticker"]) == ["c", "a"]
    assert list(flop["ticker"]) == ["e", "b"]


@pytest.mark.parametrize(
    "ts,expected",
    [
        ("2026-07-29 07:00", "avant_ouverture"),
        ("2026-07-29 00:00", "avant_ouverture"),
        ("2026-07-29 17:45", "apres_cloture"),
    ],
)
def test_classify_timing(ts, expected):
    assert classify_timing(pd.Timestamp(ts, tz="Europe/Paris")) == expected


def test_classify_timing_converts_yahoo_new_york_time():
    # "12 AM EDT" sur Yahoo = 6h à Paris -> avant l'ouverture
    assert classify_timing(pd.Timestamp("2026-07-29 00:00", tz="America/New_York")) == "avant_ouverture"


def _series():
    idx = pd.bdate_range("2026-07-20", "2026-08-10")
    s = pd.Series(100.0, index=idx)
    s[s.index >= "2026-07-29"] = 110.0  # saut le 29
    return s


def test_reaction_before_open_same_day():
    r = earnings_reaction(_series(), pd.Timestamp("2026-07-29 07:00", tz="Europe/Paris"))
    assert r["date_reaction"] == pd.Timestamp("2026-07-29")
    assert r["date_base"] == pd.Timestamp("2026-07-28")
    assert r["reaction_pct"] == pytest.approx(10)
    assert r["derive_pct"] == pytest.approx(10)


def test_reaction_after_close_next_day():
    s = _series()
    r = earnings_reaction(s, pd.Timestamp("2026-07-28 17:45", tz="Europe/Paris"))
    assert r["date_base"] == pd.Timestamp("2026-07-28")
    assert r["date_reaction"] == pd.Timestamp("2026-07-29")
    assert r["reaction_pct"] == pytest.approx(10)


def test_reaction_excess_vs_index():
    s = _series()
    idx = s.copy() * 0 + 100
    idx[idx.index >= "2026-07-29"] = 102.0
    r = earnings_reaction(s, pd.Timestamp("2026-07-29 07:00", tz="Europe/Paris"), idx)
    assert r["cac40_pct"] == pytest.approx(2)
    assert r["surperf_pct"] == pytest.approx(8)


def test_reaction_future_event_returns_none():
    assert earnings_reaction(_series(), pd.Timestamp("2026-09-01 07:00", tz="Europe/Paris")) is None


def test_reaction_summary():
    df = pd.DataFrame({"ticker": ["A", "A", "B"], "reaction_pct": [4.0, -2.0, 1.0]})
    s = reaction_summary(df).set_index("ticker")
    assert s.loc["A", "mouvement_moyen_abs_pct"] == pytest.approx(3)
    assert s.loc["A", "part_hausses_pct"] == pytest.approx(50)
    assert s.index[0] == "A"
