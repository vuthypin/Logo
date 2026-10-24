"""Tableau de bord CAC 40 : palmarès des performances et agenda des résultats.

Lancement : streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from cac40_app.analytics import PARIS_TZ, PERIODS, compute_performance, period_start, reaction_summary, top_flop
from cac40_app.data import INDEX_TICKER, compute_reactions, fetch_closes, fetch_earnings_calendar, load_constituents

GREEN, RED = "#1a9850", "#d73027"
HISTORY_YEARS = 4  # profondeur d'historique pour mesurer l'impact des résultats

st.set_page_config(page_title="CAC 40 – Palmarès & Résultats", page_icon="📈", layout="wide")


@st.cache_data(ttl=15 * 60, show_spinner="Téléchargement des cours…")
def get_closes(tickers: tuple[str, ...]) -> pd.DataFrame:
    start = pd.Timestamp.today().normalize() - pd.DateOffset(years=HISTORY_YEARS)
    return fetch_closes(list(tickers), start)


@st.cache_data(ttl=6 * 60 * 60, show_spinner="Récupération de l'agenda des résultats…")
def get_calendar(tickers: tuple[str, ...]) -> pd.DataFrame:
    return fetch_earnings_calendar(list(tickers), limit=4 * HISTORY_YEARS)


JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def fmt_jour(ts: pd.Timestamp) -> str:
    return f"{JOURS[ts.weekday()]} {ts:%d/%m/%Y}"


def fmt_pct(v) -> str:
    return "–" if pd.isna(v) else f"{v:+.2f} %"


def bar_chart(df: pd.DataFrame, color: str, title: str):
    df = df.iloc[::-1]  # le premier en haut
    fig = go.Figure(
        go.Bar(
            x=df["perf_pct"],
            y=df["name"],
            orientation="h",
            marker_color=color,
            text=[fmt_pct(v) for v in df["perf_pct"]],
            textposition="inside",
            insidetextanchor="end",
            textfont_color="white",
        )
    )
    fig.update_layout(title=title, height=420, margin=dict(l=10, r=10, t=40, b=10), xaxis_ticksuffix=" %")
    return fig


constituents = load_constituents()
names = dict(zip(constituents["ticker"], constituents["name"]))
sectors = dict(zip(constituents["ticker"], constituents["sector"]))
tickers = tuple(constituents["ticker"])

closes_all = get_closes(tickers + (INDEX_TICKER,))
if closes_all.empty:
    st.error("Impossible de récupérer les cours (connexion à Yahoo Finance ?). Réessayez plus tard.")
    st.stop()
index_closes = closes_all.get(INDEX_TICKER)
closes = closes_all.drop(columns=[INDEX_TICKER], errors="ignore")
last_date = closes.dropna(how="all").index.max()
calendar = get_calendar(tickers)
now = pd.Timestamp.now(tz=PARIS_TZ)

st.title("📈 CAC 40 – Palmarès & agenda des résultats")
st.caption(f"Dernière séance disponible : {last_date:%d/%m/%Y} · Source : Yahoo Finance (cours ajustés des dividendes)")

with st.sidebar:
    st.header("Paramètres")
    period = st.radio("Période", list(PERIODS), index=2)
    n = st.slider("Taille du classement", 5, 20, 10)
    agenda_days = st.slider("Agenda : jours à venir", 7, 120, 45)
    if st.button("🔄 Rafraîchir les données"):
        st.cache_data.clear()
        st.rerun()

tab_rank, tab_agenda, tab_impact = st.tabs(["🏆 Palmarès", "🗓️ Agenda des résultats", "📊 Impact des résultats"])

# --- Palmarès -----------------------------------------------------------------
with tab_rank:
    start = period_start(last_date, period)
    perf = compute_performance(closes, start, last_date)
    perf["name"] = perf["ticker"].map(names)
    perf["sector"] = perf["ticker"].map(sectors)
    top, flop = top_flop(perf, n)

    idx_perf = compute_performance(index_closes.to_frame(INDEX_TICKER), start, last_date) if index_closes is not None else None
    c1, c2, c3 = st.columns(3)
    if idx_perf is not None and not idx_perf.empty:
        c1.metric(f"CAC 40 ({period})", f"{idx_perf['cours_fin'][0]:,.0f}".replace(",", " "), fmt_pct(idx_perf["perf_pct"][0]))
    c2.metric("Valeurs en hausse", f"{(perf['perf_pct'] > 0).sum()} / {len(perf)}")
    c3.metric("Écart meilleure / pire", f"{perf['perf_pct'].max() - perf['perf_pct'].min():.1f} pts")

    left, right = st.columns(2)
    left.plotly_chart(bar_chart(top, GREEN, f"Top {n} – meilleures performances"), use_container_width=True)
    right.plotly_chart(bar_chart(flop, RED, f"Flop {n} – moins bonnes performances"), use_container_width=True)

    # Prochaine publication de chaque valeur, pour relier palmarès et agenda.
    upcoming = calendar[calendar["date"] >= now.normalize()].groupby("ticker")["date"].min()
    perf["prochains_resultats"] = perf["ticker"].map(upcoming).dt.strftime("%d/%m/%Y")

    with st.expander("Classement complet des 40 valeurs", expanded=False):
        table = perf[["name", "ticker", "sector", "cours_fin", "perf_pct", "prochains_resultats"]].copy()
        table.index = range(1, len(table) + 1)
        st.dataframe(
            table.rename(
                columns={
                    "name": "Société",
                    "ticker": "Ticker",
                    "sector": "Secteur",
                    "cours_fin": "Cours",
                    "perf_pct": "Perf. %",
                    "prochains_resultats": "Prochains résultats",
                }
            ),
            column_config={"Cours": st.column_config.NumberColumn(format="%.2f"), "Perf. %": st.column_config.NumberColumn(format="%+.2f")},
            use_container_width=True,
            height=600,
        )

    sector_perf = perf.groupby("sector")["perf_pct"].mean().sort_values()
    fig = px.bar(
        sector_perf,
        orientation="h",
        color=sector_perf.values > 0,
        color_discrete_map={True: GREEN, False: RED},
        title="Performance moyenne par secteur",
    )
    fig.update_layout(showlegend=False, height=500, xaxis_title="%", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

# --- Agenda -------------------------------------------------------------------
reactions = compute_reactions(calendar, closes, index_closes)
if not reactions.empty:
    reactions["name"] = reactions["ticker"].map(names)

with tab_agenda:
    horizon = now + pd.Timedelta(days=agenda_days)
    fut = calendar[(calendar["date"] >= now.normalize()) & (calendar["date"] <= horizon)].copy()
    st.subheader(f"Publications à venir ({agenda_days} prochains jours)")
    if fut.empty:
        st.info("Aucune date trouvée sur cette période. Vous pouvez en ajouter dans cac40_app/agenda_manuel.csv.")
    else:
        summary = reaction_summary(reactions).set_index("ticker") if not reactions.empty else pd.DataFrame()
        fut["Société"] = fut["ticker"].map(names)
        fut["Date"] = fut["date"].map(fmt_jour)
        perf_map = perf.set_index("ticker")["perf_pct"]
        fut[f"Perf. {period} %"] = fut["ticker"].map(perf_map)
        fut["Mouvement moyen historique %"] = fut["ticker"].map(summary.get("mouvement_moyen_abs_pct", pd.Series(dtype=float)))
        cols = ["Date", "Société", "ticker", f"Perf. {period} %", "Mouvement moyen historique %"]
        if "bpa_estime" in fut:
            fut["BPA estimé"] = fut["bpa_estime"]
            cols.append("BPA estimé")
        st.dataframe(
            fut[cols + ["source"]].rename(columns={"ticker": "Ticker", "source": "Source"}),
            column_config={
                f"Perf. {period} %": st.column_config.NumberColumn(format="%+.2f"),
                "Mouvement moyen historique %": st.column_config.NumberColumn(
                    format="± %.2f", help="Variation absolue moyenne du titre le jour de ses précédentes publications"
                ),
            },
            hide_index=True,
            use_container_width=True,
        )
        fig = px.scatter(
            fut,
            x="date",
            y="Société",
            size=fut["Mouvement moyen historique %"].fillna(1).clip(lower=1),
            color=f"Perf. {period} %",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            title="Calendrier (taille = amplitude moyenne des réactions passées)",
        )
        fig.update_layout(height=max(300, 28 * fut["Société"].nunique()), yaxis_title=None, xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Publications récentes et réaction du marché")
    if reactions.empty:
        st.info("Pas encore de publications passées disponibles.")
    else:
        recent = reactions[reactions["date"] >= now - pd.Timedelta(days=60)].sort_values("date", ascending=False)
        view = pd.DataFrame(
            {
                "Date": recent["date"].dt.strftime("%d/%m/%Y"),
                "Société": recent["name"],
                "Réaction J %": recent["reaction_pct"],
                "CAC 40 J %": recent["cac40_pct"],
                "Surperf. vs CAC %": recent["surperf_pct"],
                "Dérive 5 séances %": recent["derive_pct"],
                "Surprise BPA %": recent.get("surprise_pct"),
            }
        )
        num = st.column_config.NumberColumn(format="%+.2f")
        st.dataframe(
            view,
            column_config={c: num for c in view.columns if c.endswith("%")},
            hide_index=True,
            use_container_width=True,
        )

# --- Impact -------------------------------------------------------------------
with tab_impact:
    if reactions.empty:
        st.info("Pas assez d'historique de publications pour mesurer l'impact.")
    else:
        st.subheader("Sensibilité des valeurs à leurs résultats")
        summary = reaction_summary(reactions)
        summary["Société"] = summary["ticker"].map(names)
        fig = px.bar(
            summary.sort_values("mouvement_moyen_abs_pct"),
            x="mouvement_moyen_abs_pct",
            y="Société",
            orientation="h",
            color="reaction_moyenne_pct",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            labels={"mouvement_moyen_abs_pct": "Mouvement moyen absolu le jour J (%)", "reaction_moyenne_pct": "Réaction moyenne %"},
        )
        fig.update_layout(height=900, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Zoom sur une valeur")
        choice = st.selectbox("Société", sorted(names.values()))
        ticker = next(t for t, n_ in names.items() if n_ == choice)
        ev = reactions[reactions["ticker"] == ticker].sort_values("date")
        price = closes[ticker].dropna()
        price = price[price.index >= last_date - pd.DateOffset(years=2)]

        fig = go.Figure(go.Scatter(x=price.index, y=price.values, name=choice, line=dict(color="#4575b4")))
        ev_plot = ev[ev["date_reaction"] >= price.index.min()] if not price.empty else ev
        if not ev_plot.empty:
            fig.add_trace(
                go.Scatter(
                    x=ev_plot["date_reaction"],
                    y=price.reindex(ev_plot["date_reaction"]).values,
                    mode="markers+text",
                    marker=dict(size=12, color=[GREEN if v > 0 else RED for v in ev_plot["reaction_pct"]], symbol="diamond"),
                    text=[fmt_pct(v) for v in ev_plot["reaction_pct"]],
                    textposition="top center",
                    name="Publication de résultats",
                )
            )
        for d in calendar[(calendar["ticker"] == ticker) & (calendar["date"] >= now.normalize())]["date"]:
            fig.add_vline(x=d.tz_localize(None).to_pydatetime(), line_dash="dash", line_color="gray")
        fig.update_layout(height=450, title=f"{choice} – cours et réactions aux résultats (pointillés : à venir)")
        st.plotly_chart(fig, use_container_width=True)

        if ev.empty:
            st.info("Aucune publication passée trouvée pour cette valeur.")
        else:
            row = summary[summary["ticker"] == ticker].iloc[0]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Publications analysées", int(row["nb_publications"]))
            m2.metric("Mouvement moyen J", f"± {row['mouvement_moyen_abs_pct']:.2f} %")
            m3.metric("Réactions positives", f"{row['part_hausses_pct']:.0f} %")
            m4.metric("Extrêmes", f"{row['plus_forte_hausse_pct']:+.1f} / {row['plus_forte_baisse_pct']:+.1f} %")
            hist = pd.DataFrame(
                {
                    "Date": ev["date"].dt.strftime("%d/%m/%Y"),
                    "Réaction J %": ev["reaction_pct"],
                    "Surperf. vs CAC %": ev["surperf_pct"],
                    "Dérive 5 séances %": ev["derive_pct"],
                    "BPA estimé": ev.get("bpa_estime"),
                    "BPA publié": ev.get("bpa_publie"),
                    "Surprise BPA %": ev.get("surprise_pct"),
                }
            ).iloc[::-1]
            num = st.column_config.NumberColumn(format="%+.2f")
            st.dataframe(hist, column_config={c: num for c in hist.columns if c.endswith("%")}, hide_index=True, use_container_width=True)

st.caption(
    "Réaction J = variation entre la dernière clôture avant la publication et la première clôture après. "
    "Données indicatives, sans valeur de conseil en investissement."
)
