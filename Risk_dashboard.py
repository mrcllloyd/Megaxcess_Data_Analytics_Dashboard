import streamlit as st
import pandas as pd

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="MegaXcess Risk Dashboard",
    layout="wide"
)

st.title("MegaXcess Risk Analytics Dashboard")


# =========================================================
# LOAD DATA
# =========================================================
@st.cache_data
def load_data():
    wager = pd.read_csv("sp1_dw_aggr.csv")
    players = pd.read_csv("player_info.csv")

    return wager, players


wager, players = load_data()


# =========================================================
# CLEAN / PREPARE DATA
# =========================================================

wager["date_time"] = pd.to_datetime(
    wager["date_time"],
    errors="coerce"
)

players = players.rename(
    columns={
        "player_id": "playerid",
        "nature_of_work": "occupation"
    }
)

player_cols = [
    "playerid",
    "occupation",
    "kyc_status",
    "current_account_status"
]

players_small = players[player_cols].drop_duplicates(
    subset=["playerid"]
)

df = wager.merge(
    players_small,
    on="playerid",
    how="left"
)

df["occupation"] = df["occupation"].fillna("Unknown")

df["reportdate"] = df["date_time"]

df["wageramount"] = pd.to_numeric(
    df["total_bet"],
    errors="coerce"
).fillna(0)

df["wagernum"] = pd.to_numeric(
    df["txn_count"],
    errors="coerce"
).fillna(0)

df["holdamount"] = (
    pd.to_numeric(df["total_bet"], errors="coerce").fillna(0)
    -
    pd.to_numeric(df["total_win"], errors="coerce").fillna(0)
)

df["period"] = df["date_time"].dt.to_period("M").astype(str)


# =========================================================
# SIDEBAR FILTERS
# =========================================================

st.sidebar.header("Filters")

sp_options = sorted(df["SP_NAME"].dropna().unique())

selected_sp = st.sidebar.selectbox(
    "Service Provider",
    sp_options
)

filtered = df[
    df["SP_NAME"] == selected_sp
].copy()


valid_dates = filtered["date_time"].dropna()

if not valid_dates.empty:

    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    selected_dates = st.sidebar.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if len(selected_dates) == 2:
        start_date, end_date = selected_dates

        filtered = filtered[
            (
                filtered["date_time"].dt.date >= start_date
            )
            &
            (
                filtered["date_time"].dt.date <= end_date
            )
        ]


# =========================================================
# PLAYER-LEVEL RISK METRICS
# =========================================================

player_risk = filtered.groupby("playerid").agg(
    total_wager=("wageramount", "sum"),
    total_win=("total_win", "sum"),
    total_transactions=("wagernum", "sum"),
    max_single_bet=("wageramount", "max"),
    active_days=("reportdate", "nunique")
).reset_index()


player_risk["avg_wager_per_day"] = (
    player_risk["total_wager"]
    /
    player_risk["active_days"].replace(0, 1)
)


# =========================================================
# RISK SCORING
# =========================================================

player_risk["risk_score"] = 0

player_risk.loc[
    player_risk["max_single_bet"] >= 100000,
    "risk_score"
] += 1

player_risk.loc[
    player_risk["total_transactions"] >= 50,
    "risk_score"
] += 1

player_risk.loc[
    player_risk["avg_wager_per_day"] >= 20000,
    "risk_score"
] += 1

player_risk.loc[
    player_risk["total_wager"] >= 500000,
    "risk_score"
] += 1


def classify_risk(score):
    if score >= 3:
        return "High"
    elif score >= 1:
        return "Medium"
    return "Low"


player_risk["risk_level"] = (
    player_risk["risk_score"]
    .apply(classify_risk)
)


filtered = filtered.merge(
    player_risk[["playerid", "risk_level", "risk_score"]],
    on="playerid",
    how="left"
)


# =========================================================
# KPI CARDS
# =========================================================

total_players = filtered["playerid"].nunique()
total_wager = filtered["wageramount"].sum()
total_transactions = filtered["wagernum"].sum()
high_risk_players = player_risk[
    player_risk["risk_level"] == "High"
]["playerid"].nunique()


col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Unique Players",
    f"{total_players:,}"
)

col2.metric(
    "Total Wager",
    f"{total_wager:,.2f}"
)

col3.metric(
    "Transactions",
    f"{total_transactions:,.0f}"
)

col4.metric(
    "High Risk Players",
    f"{high_risk_players:,}"
)


st.divider()


# =========================================================
# WAGER SUMMARY
# =========================================================

summary = filtered.groupby("period").agg(
    total_players=("playerid", "nunique"),
    total_wager=("wageramount", "sum"),
    total_hold=("holdamount", "sum")
).reset_index()


st.subheader(
    f"Wager Trend Over Time for {selected_sp}"
)

if not summary.empty:

    st.line_chart(
        summary.set_index("period")["total_wager"]
    )

    st.dataframe(
        summary,
        use_container_width=True
    )

else:
    st.info("No wagering data available.")


# =========================================================
# RISK FLAGS BY OCCUPATION
# =========================================================

player_metrics = filtered.groupby(
    ["playerid", "occupation"]
).agg(
    total_sessions=("wagernum", "sum"),
    total_wager=("wageramount", "sum"),
    avg_bet=("wageramount", "mean"),
    max_single_bet=("wageramount", "max"),
    wager_days=("reportdate", "nunique")
).reset_index()


player_metrics["avg_wager_per_day"] = (
    player_metrics["total_wager"]
    /
    player_metrics["wager_days"].replace(0, 1)
)


player_metrics["big_bet_flag"] = (
    player_metrics["max_single_bet"] >= 100000
)

player_metrics["high_freq_flag"] = (
    player_metrics["total_sessions"] >= 50
)

player_metrics["daily_spike_flag"] = (
    player_metrics["avg_wager_per_day"] >= 20000
)


flag_summary = (
    player_metrics
    .groupby("occupation")[
        [
            "big_bet_flag",
            "high_freq_flag",
            "daily_spike_flag"
        ]
    ]
    .sum()
)


st.subheader("Risk Flags by Occupation")

if not flag_summary.empty:

    st.bar_chart(flag_summary)

    st.dataframe(
        flag_summary,
        use_container_width=True
    )

else:
    st.info("No risk flags detected.")


# =========================================================
# RISK LEVEL DISTRIBUTION
# =========================================================

risk_summary = filtered.groupby(
    "risk_level"
).agg(
    unique_players=("playerid", "nunique"),
    total_wager=("wageramount", "sum"),
    total_hold=("holdamount", "sum")
).reset_index()


st.subheader("Risk Level Distribution")

st.dataframe(
    risk_summary,
    use_container_width=True
)


if not filtered.empty:
    st.bar_chart(
        filtered["risk_level"].value_counts()
    )


# =========================================================
# TOP PLAYERS
# =========================================================

st.subheader(
    f"Top 10 Players by Wager for {selected_sp}"
)


top_players = filtered.groupby(
    [
        "playerid",
        "gamename",
        "occupation",
        "risk_level"
    ],
    dropna=False
).agg(
    total_wager=("wageramount", "sum"),
    total_hold=("holdamount", "sum"),
    transactions=("wagernum", "sum")
).reset_index()


top_players = (
    top_players
    .sort_values(
        by="total_wager",
        ascending=False
    )
    .head(10)
)


st.dataframe(
    top_players,
    use_container_width=True
)


# =========================================================
# PLAYER RISK TABLE
# =========================================================

st.subheader("Player Risk Details")

risk_details = player_risk.sort_values(
    ["risk_score", "total_wager"],
    ascending=[False, False]
)

st.dataframe(
    risk_details,
    use_container_width=True
)
