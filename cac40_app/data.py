"""Récupération des données de marché (Yahoo Finance via yfinance)."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from .analytics import PARIS_TZ, earnings_reaction

INDEX_TICKER = "^FCHI"
DATA_DIR = Path(__file__).parent
CONSTITUENTS_FILE = DATA_DIR / "constituents.csv"
MANUAL_AGENDA_FILE = DATA_DIR / "agenda_manuel.csv"

log = logging.getLogger(__name__)


def load_constituents(path: Path = CONSTITUENTS_FILE) -> pd.DataFrame:
    """Composition du CAC 40 (modifiable dans constituents.csv)."""
    return pd.read_csv(path)


def fetch_closes(tickers: list[str], start: pd.Timestamp, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Clôtures ajustées (dividendes/splits), une colonne par ticker."""
    import yfinance as yf

    raw = yf.download(
        tickers,
        start=pd.Timestamp(start).strftime("%Y-%m-%d"),
        end=(pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") if end is not None else None,
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    closes = raw["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(tickers[0])
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    return closes.sort_index()


def _past_and_future_earnings(ticker: str, limit: int) -> pd.DataFrame:
    import yfinance as yf

    t = yf.Ticker(ticker)
    frames = []
    try:
        df = t.get_earnings_dates(limit=limit)
        if df is not None and not df.empty:
            df = df.reset_index().rename(
                columns={
                    "Earnings Date": "date",
                    "EPS Estimate": "bpa_estime",
                    "Reported EPS": "bpa_publie",
                    "Surprise(%)": "surprise_pct",
                }
            )
            frames.append(df[[c for c in ("date", "bpa_estime", "bpa_publie", "surprise_pct") if c in df]])
    except Exception as exc:  # Yahoo change souvent de format : on ne bloque pas l'appli
        log.warning("Dates de résultats indisponibles pour %s : %s", ticker, exc)

    try:
        cal = t.calendar or {}
        for d in cal.get("Earnings Date", []) or []:
            frames.append(pd.DataFrame({"date": [pd.Timestamp(d).tz_localize(PARIS_TZ)]}))
    except Exception as exc:
        log.warning("Calendrier indisponible pour %s : %s", ticker, exc)

    if not frames:
        return pd.DataFrame(columns=["date"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.tz_convert(PARIS_TZ)
    out["jour"] = out["date"].dt.normalize()
    # Le calendrier et la page des résultats peuvent donner le même jour : on garde la ligne la plus riche.
    out = out.sort_values("bpa_estime" if "bpa_estime" in out else "date", na_position="last")
    out = out.drop_duplicates("jour").drop(columns="jour")
    out["ticker"] = ticker
    out["source"] = "Yahoo Finance"
    return out


def load_manual_agenda(path: Path = MANUAL_AGENDA_FILE) -> pd.DataFrame:
    """Dates saisies à la main (prioritaires sur Yahoo pour le même jour)."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "date", "timing", "label"])
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(PARIS_TZ)
    df["source"] = "Saisie manuelle"
    return df


def fetch_earnings_calendar(tickers: list[str], limit: int = 12, workers: int = 8) -> pd.DataFrame:
    """Agenda des résultats (passés et à venir) pour toutes les valeurs."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        frames = list(pool.map(lambda t: _past_and_future_earnings(t, limit), tickers))
    frames.append(load_manual_agenda())
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "source"])
    cal = pd.concat(frames, ignore_index=True)
    cal["jour"] = cal["date"].dt.normalize()
    cal["priorite"] = (cal["source"] == "Saisie manuelle").astype(int)
    cal = cal.sort_values("priorite", ascending=False).drop_duplicates(["ticker", "jour"])
    return cal.drop(columns=["jour", "priorite"]).sort_values("date").reset_index(drop=True)


def compute_reactions(
    calendar: pd.DataFrame,
    closes: pd.DataFrame,
    index_closes: pd.Series | None,
) -> pd.DataFrame:
    """Réaction de chaque valeur à chacune de ses publications passées."""
    rows = []
    now = pd.Timestamp.now(tz=PARIS_TZ)
    for _, ev in calendar[calendar["date"] <= now].iterrows():
        if ev["ticker"] not in closes:
            continue
        timing = ev.get("timing") if isinstance(ev.get("timing"), str) else None
        r = earnings_reaction(closes[ev["ticker"]], ev["date"], index_closes, timing=timing)
        if r is None:
            continue
        rows.append({**ev.to_dict(), **r})
    return pd.DataFrame(rows)
