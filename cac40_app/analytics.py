"""Calculs purs (sans accès réseau) : performances, classements, réactions aux résultats."""

from __future__ import annotations

import pandas as pd

PARIS_TZ = "Europe/Paris"

# Libellé -> décalage. "YTD" est traité à part (depuis le 1er janvier).
PERIODS = {
    "1 jour": pd.DateOffset(days=1),
    "5 jours": pd.DateOffset(days=7),
    "1 mois": pd.DateOffset(months=1),
    "3 mois": pd.DateOffset(months=3),
    "6 mois": pd.DateOffset(months=6),
    "Depuis le 1er janvier": None,
    "1 an": pd.DateOffset(years=1),
}


def period_start(end: pd.Timestamp, period: str) -> pd.Timestamp:
    """Date de début d'une période se terminant à `end`."""
    end = pd.Timestamp(end).normalize()
    if period not in PERIODS:
        raise ValueError(f"Période inconnue : {period}")
    if PERIODS[period] is None:
        # Base = dernière clôture de l'année précédente.
        return pd.Timestamp(year=end.year - 1, month=12, day=31)
    return end - PERIODS[period]


def _base_close(series: pd.Series, start: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """Dernière clôture disponible à `start` ou avant (sinon la première après)."""
    s = series.dropna()
    if s.empty:
        return None
    before = s[s.index <= start]
    if not before.empty:
        return before.index[-1], float(before.iloc[-1])
    return s.index[0], float(s.iloc[0])


def compute_performance(
    closes: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Performance (%) de chaque colonne de `closes` entre `start` et `end`.

    Pour "1 jour", `start` = veille : la base est la clôture précédente, comme
    sur les sites boursiers.
    """
    if end is not None:
        closes = closes[closes.index <= pd.Timestamp(end)]
    rows = []
    for ticker in closes.columns:
        s = closes[ticker].dropna()
        if s.empty:
            continue
        base = _base_close(s, pd.Timestamp(start))
        if base is None:
            continue
        base_date, base_close = base
        last_date, last_close = s.index[-1], float(s.iloc[-1])
        if last_date <= base_date or base_close == 0:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date_debut": base_date,
                "cours_debut": base_close,
                "date_fin": last_date,
                "cours_fin": last_close,
                "perf_pct": (last_close / base_close - 1) * 100,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("perf_pct", ascending=False).reset_index(drop=True)


def top_flop(perf: pd.DataFrame, n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Les `n` meilleures et les `n` pires performances."""
    ordered = perf.sort_values("perf_pct", ascending=False)
    top = ordered.head(n).reset_index(drop=True)
    flop = ordered.tail(n).sort_values("perf_pct").reset_index(drop=True)
    return top, flop


def classify_timing(event_ts: pd.Timestamp) -> str:
    """'avant_ouverture' ou 'apres_cloture' selon l'heure de publication (heure de Paris).

    Une heure absente (minuit pile) est traitée comme une publication avant
    l'ouverture, cas le plus fréquent pour les sociétés du CAC 40.
    """
    ts = pd.Timestamp(event_ts)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(PARIS_TZ)
    minutes = ts.hour * 60 + ts.minute
    if minutes == 0 or minutes < 9 * 60:
        return "avant_ouverture"
    if minutes >= 17 * 60 + 30:
        return "apres_cloture"
    # Pendant la séance : la réaction démarre le jour même.
    return "avant_ouverture" if minutes < 13 * 60 else "apres_cloture"


def earnings_reaction(
    closes: pd.Series,
    event_ts: pd.Timestamp,
    index_closes: pd.Series | None = None,
    timing: str | None = None,
    drift_days: int = 5,
) -> dict | None:
    """Réaction du cours à une publication de résultats.

    - réaction J : variation entre la dernière clôture avant la publication et
      la première clôture après ;
    - dérive : variation entre cette même base et la clôture `drift_days`
      séances après la réaction ;
    - surperf. : réaction J moins la variation du CAC 40 sur la même séance.
    """
    s = closes.dropna()
    if s.empty:
        return None
    ts = pd.Timestamp(event_ts)
    timing = timing or classify_timing(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(PARIS_TZ).tz_localize(None)
    day = ts.normalize()

    if timing == "apres_cloture":
        base_part = s[s.index <= day]
        react_part = s[s.index > day]
    else:
        base_part = s[s.index < day]
        react_part = s[s.index >= day]
    if base_part.empty or react_part.empty:
        return None

    base_date, base_close = base_part.index[-1], float(base_part.iloc[-1])
    react_date, react_close = react_part.index[0], float(react_part.iloc[0])
    result = {
        "date_base": base_date,
        "date_reaction": react_date,
        "reaction_pct": (react_close / base_close - 1) * 100,
        "derive_pct": None,
        "cac40_pct": None,
        "surperf_pct": None,
        "timing": timing,
    }
    if len(react_part) > drift_days:
        result["derive_pct"] = (float(react_part.iloc[drift_days]) / base_close - 1) * 100

    if index_closes is not None:
        idx = index_closes.dropna()
        if base_date in idx.index and react_date in idx.index:
            idx_pct = (float(idx[react_date]) / float(idx[base_date]) - 1) * 100
            result["cac40_pct"] = idx_pct
            result["surperf_pct"] = result["reaction_pct"] - idx_pct
    return result


def reaction_summary(reactions: pd.DataFrame) -> pd.DataFrame:
    """Statistiques par valeur : mouvement moyen absolu, % de hausses, etc."""
    if reactions.empty:
        return pd.DataFrame()
    g = reactions.groupby("ticker")["reaction_pct"]
    out = pd.DataFrame(
        {
            "nb_publications": g.count(),
            "mouvement_moyen_abs_pct": g.apply(lambda x: x.abs().mean()),
            "reaction_moyenne_pct": g.mean(),
            "part_hausses_pct": g.apply(lambda x: (x > 0).mean() * 100),
            "plus_forte_hausse_pct": g.max(),
            "plus_forte_baisse_pct": g.min(),
        }
    )
    return out.sort_values("mouvement_moyen_abs_pct", ascending=False).reset_index()
