import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from fpdf import FPDF
from rapidfuzz import fuzz
import tempfile

@st.cache_data
def load_data():
    player_info = pd.read_csv("player_info.csv")
    usage = pd.read_csv("sp1_dw_aggr.csv")

    usage['playerid'] = usage['playerid'].astype(str)
    usage['reportdate'] = pd.to_datetime(usage['date_time'])
    usage['wageramount'] = usage['total_bet']
    usage['holdamount'] = usage['total_bet'] - usage['total_win']
    usage['wagernum'] = usage['txn_count']

    player_info['player_id'] = player_info['player_id'].astype(str)
    merged = usage.merge(player_info, left_on='playerid', right_on='player_id', how='left')
    merged['occupation'] = merged['nature_of_work']

    def classify_risk(row):
        if row['wageramount'] < 5000:
            return "GO (Normal)"
        elif row['wageramount'] < 25000:
            return "LOOK (At Risk)"
        elif row['wageramount'] < 100000:
            return "ACT (Pathological)"
        else:
            return "STOP (Exclude)"
    merged['risk_level'] = merged.apply(classify_risk, axis=1)
    return merged, player_info

merged_df, player_info = load_data()

# Sidebar
st.sidebar.title("Filters")
date_range = st.sidebar.date_input("Date Range", [merged_df['reportdate'].min(), merged_df['reportdate'].max()])
sp_options = ['All'] + sorted(merged_df['SP_NAME'].dropna().unique().tolist())
selected_sp = st.sidebar.selectbox("Select SP_NAME", sp_options)

start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
filtered = merged_df[(merged_df['reportdate'] >= start_date) & (merged_df['reportdate'] <= end_date)]
if selected_sp != 'All':
    filtered = filtered[filtered['SP_NAME'] == selected_sp]

# Granularity
days_range = (end_date - start_date).days
if days_range <= 7:
    granularity = 'Daily'
    filtered['period'] = filtered['reportdate'].dt.date
elif days_range <= 60:
    granularity = 'Weekly'
    filtered['period'] = filtered['reportdate'].dt.to_period("W").dt.start_time
elif days_range <= 365:
    granularity = 'Monthly'
    filtered['period'] = filtered['reportdate'].dt.to_period("M").dt.start_time
else:
    granularity = 'Yearly'
    filtered['period'] = filtered['reportdate'].dt.to_period("Y").dt.start_time

# Header
st.title("🎯 Player Risk Dashboard")
st.write(f"📅 Date Range: {start_date.date()} to {end_date.date()}  |  SP_NAME: {selected_sp}  |  Granularity: {granularity}")

# Summary
summary = filtered.groupby('period').agg(
    total_players=('playerid', 'nunique'),
    total_wager=('wageramount', 'sum'),
    total_hold=('holdamount', 'sum')
).reset_index()
st.subheader(f"📈 Wager Trend Over Time for {selected_sp}")
st.line_chart(summary.set_index('period')['total_wager'])

# Risk Flags
player_metrics = filtered.groupby(['playerid', 'occupation']).agg(
    total_sessions=('wagernum', 'sum'),
    total_wager=('wageramount', 'sum'),
    avg_bet=('wageramount', 'mean'),
    max_single_bet=('wageramount', 'max'),
    wager_days=('reportdate', 'nunique')
).reset_index()
player_metrics['avg_wager_per_day'] = player_metrics['total_wager'] / player_metrics['wager_days']
player_metrics['big_bet_flag'] = player_metrics['max_single_bet'] >= 100000
player_metrics['high_freq_flag'] = player_metrics['total_sessions'] >= 50
player_metrics['daily_spike_flag'] = player_metrics['avg_wager_per_day'] >= 20000

flag_summary = player_metrics.groupby('occupation')[['big_bet_flag', 'high_freq_flag', 'daily_spike_flag']].sum()
st.subheader("🚩 Risk Flags by Occupation")
if not flag_summary.empty:
    st.bar_chart(flag_summary)
else:
    st.info("No risk flags detected.")

# Risk Level Summary
risk_summary = filtered.groupby('risk_level').agg(
    unique_players=('playerid', 'nunique'),
    total_wager=('wageramount', 'sum'),
    total_hold=('holdamount', 'sum')
).reset_index()
st.subheader("📊 Risk Level Distribution")
st.dataframe(risk_summary)
st.bar_chart(filtered['risk_level'].value_counts())

# Top Players
st.subheader(f"🏅 Top 10 Players by Wager for {selected_sp}")
top_players = filtered.sort_values(by='wageramount', ascending=False).head(10)[[
    'playerid', 'gamename', 'wageramount', 'holdamount', 'risk_level', 'occupation'
]]
st.dataframe(top_players)

# KYC Analysis
player_info['registered_date'] = pd.to_datetime(player_info['registered_date'], errors='coerce')
player_info['verify_date'] = pd.to_datetime(player_info['verify_date'], errors='coerce')
player_info['ts'] = pd.to_datetime(player_info['ts'], errors='coerce')
verified_players = player_info[(player_info['kyc_status'].str.lower() == 'verified') & (player_info['verify_date'].notna())]
today = player_info['ts'].max()
unverified_players = player_info[
    (player_info['kyc_status'].str.lower() != 'verified') &
    ((today - player_info['registered_date']) >= pd.Timedelta(days=3))
]
kyc_summary = pd.DataFrame({
    "Status": ["Verified", "Unverified (3+ days)"],
    "Player Count": [len(verified_players), len(unverified_players)]
})
st.subheader("📌 KYC Status Analysis")
fig_kyc, ax = plt.subplots()
ax.bar(kyc_summary['Status'], kyc_summary['Player Count'], color=['green', 'red'])
ax.set_title("KYC Verification Summary")
ax.set_ylabel("Number of Players")
plt.tight_layout()
st.pyplot(fig_kyc)

# Fuzzy Matching
st.subheader("🧠 Fuzzy Matching: Possible Duplicate Accounts")
identity_columns = ['firstname', 'lastname', 'email', 'username', 'mobileno', 'city', 'region', 'zipcode']
cleaned_info = player_info.dropna(subset=identity_columns).copy()
cleaned_info['identity_string'] = (
    cleaned_info['firstname'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['lastname'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['email'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['username'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['mobileno'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['city'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['region'].astype(str).str.lower().str.strip() + ' ' +
    cleaned_info['zipcode'].astype(str).str.lower().str.strip()
)
subset = cleaned_info[['player_id', 'identity_string']].head(300)
fuzzy_results = []
for i in range(len(subset)):
    for j in range(i+1, len(subset)):
        score = fuzz.token_sort_ratio(subset.iloc[i]['identity_string'], subset.iloc[j]['identity_string'])
        if score >= 90:
            fuzzy_results.append({
                'player1': subset.iloc[i]['player_id'],
                'player2': subset.iloc[j]['player_id'],
                'similarity_score': score
            })
fuzzy_df = pd.DataFrame(fuzzy_results)
if not fuzzy_df.empty:
    st.dataframe(fuzzy_df.sort_values(by='similarity_score', ascending=False).head(20))
else:
    st.info("No highly similar player profiles detected.")

# PDF Export Button
st.markdown("---")
if st.button("📄 Download Full Dashboard as PDF"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Player Risk Dashboard Summary", ln=True)
    pdf.cell(0, 10, f"Date Range: {start_date.date()} to {end_date.date()} | SP_NAME: {selected_sp}", ln=True)

    # KYC Chart
    kyc_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    fig_kyc.savefig(kyc_img.name, dpi=300, bbox_inches='tight')
    pdf.add_page()
    pdf.image(kyc_img.name, x=10, y=30, w=190)

    # Fuzzy Logic Table
    if not fuzzy_df.empty:
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, "Fuzzy Matched Players (Sample)", ln=True)
        pdf.set_font("Arial", '', 10)
        for _, row in fuzzy_df.sort_values(by='similarity_score', ascending=False).head(10).iterrows():
            txt = f"{row['player1']} ↔ {row['player2']} | Score: {row['similarity_score']}"
            pdf.cell(0, 8, txt.encode('latin-1', 'replace').decode('latin-1'), ln=True)

    pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
    pdf.output(pdf_path)
    with open(pdf_path, "rb") as f:
        st.download_button("Download PDF", f.read(), file_name="dashboard_summary.pdf", mime="application/pdf")
