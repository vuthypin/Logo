"""Exporte les données du tableau de bord en JSON pour l'application mobile.

Usage : python scripts/export_data.py mobile/data.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cac40_app.analytics import PARIS_TZ, PERIODS, compute_performance, period_start, reaction_summary  # noqa: E402
from cac40_app.data import (  # noqa: E402
    INDEX_TICKER,
    compute_reactions,
    fetch_closes,
    fetch_earnings_calendar,
    load_constituents,
)

HISTORY_YEARS = 4  # pour mesurer les réactions passées
CHART_DAYS = 400  # profondeur des courbes envoyées au téléphone (~ 13 mois de séances)


def _num(v, digits: int = 2):
    if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
        return None
    return round(float(v), digits)


def _day(ts) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(PARIS_TZ)
    return ts.strftime("%Y-%m-%d")


def build_payload(
    constituents: pd.DataFrame,
    closes_all: pd.DataFrame,
    calendar: pd.DataFrame,
    now: pd.Timestamp,
) -> dict:
    index_closes = closes_all.get(INDEX_TICKER)
    closes = closes_all.drop(columns=[INDEX_TICKER], errors="ignore")
    last_date = closes.dropna(how="all").index.max()

    perfs = {
        p: compute_performance(closes, period_start(last_date, p), last_date).set_index("ticker")["perf_pct"]
        for p in PERIODS
    }
    index_perf = {}
    if index_closes is not None:
        for p in PERIODS:
            ip = compute_performance(index_closes.to_frame(INDEX_TICKER), period_start(last_date, p), last_date)
            index_perf[p] = _num(ip["perf_pct"].iloc[0]) if not ip.empty else None

    reactions = compute_reactions(calendar, closes, index_closes)
    summary = reaction_summary(reactions).set_index("ticker") if not reactions.empty else pd.DataFrame()
    future = calendar[calendar["date"] >= now.normalize()]
    next_dates = future.groupby("ticker")["date"].min()

    chart = closes_all.iloc[-CHART_DAYS:]
    chart_start = chart.index.min()

    stocks = []
    for _, c in constituents.iterrows():
        t = c["ticker"]
        if t not in closes:
            continue
        ev = reactions[reactions["ticker"] == t].sort_values("date") if not reactions.empty else pd.DataFrame()
        stats = summary.loc[t] if t in summary.index else None
        stocks.append(
            {
                "ticker": t,
                "name": c["name"],
                "sector": c["sector"],
                "last": _num(closes[t].dropna().iloc[-1]) if closes[t].notna().any() else None,
                "closes": [_num(v) for v in chart[t]],
                "perf": {p: _num(perfs[p].get(t)) for p in PERIODS},
                "next_earnings": _day(next_dates.get(t)),
                "stats": None
                if stats is None
                else {
                    "n": int(stats["nb_publications"]),
                    "avg_abs": _num(stats["mouvement_moyen_abs_pct"]),
                    "avg": _num(stats["reaction_moyenne_pct"]),
                    "up_share": _num(stats["part_hausses_pct"], 0),
                    "max": _num(stats["plus_forte_hausse_pct"]),
                    "min": _num(stats["plus_forte_baisse_pct"]),
                },
                "events": [
                    {
                        "date": _day(e["date"]),
                        "reaction_date": _day(e["date_reaction"]),
                        "in_chart": bool(pd.Timestamp(e["date_reaction"]) >= chart_start),
                        "reaction": _num(e["reaction_pct"]),
                        "excess": _num(e.get("surperf_pct")),
                        "drift": _num(e.get("derive_pct")),
                        "surprise": _num(e.get("surprise_pct")),
                    }
                    for _, e in ev.iterrows()
                ],
            }
        )

    names = dict(zip(constituents["ticker"], constituents["name"]))
    upcoming = [
        {
            "ticker": r["ticker"],
            "name": names.get(r["ticker"], r["ticker"]),
            "date": _day(r["date"]),
            "eps_estimate": _num(r.get("bpa_estime"), 3),
            "avg_abs": _num(summary["mouvement_moyen_abs_pct"].get(r["ticker"])) if not summary.empty else None,
        }
        for _, r in future.sort_values("date").iterrows()
        if r["ticker"] in names
    ]

    return {
        "updated_at": now.isoformat(timespec="minutes"),
        "last_session": _day(last_date),
        "periods": list(PERIODS),
        "dates": [d.strftime("%Y-%m-%d") for d in chart.index],
        "index": {
            "name": "CAC 40",
            "last": _num(index_closes.dropna().iloc[-1]) if index_closes is not None else None,
            "closes": [_num(v) for v in chart[INDEX_TICKER]] if INDEX_TICKER in chart else [],
            "perf": index_perf,
        },
        "stocks": stocks,
        "upcoming": upcoming,
    }


def main(out: str) -> None:
    constituents = load_constituents()
    tickers = list(constituents["ticker"])
    start = pd.Timestamp.today().normalize() - pd.DateOffset(years=HISTORY_YEARS)
    closes_all = fetch_closes(tickers + [INDEX_TICKER], start)
    if closes_all.empty:
        raise SystemExit("Aucun cours récupéré : export annulé.")
    calendar = fetch_earnings_calendar(tickers, limit=4 * HISTORY_YEARS)
    payload = build_payload(constituents, closes_all, calendar, pd.Timestamp.now(tz=PARIS_TZ))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out} : {len(payload['stocks'])} valeurs, {len(payload['upcoming'])} publications à venir")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mobile/data.json")
