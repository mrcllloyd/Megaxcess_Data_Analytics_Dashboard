... # previous code remains unchanged

# Fuzzy Matching
st.subheader("🧠 Fuzzy Matching: Possible Duplicate Accounts")
expected_columns = ['firstname', 'lastname', 'email', 'username', 'mobileno', 'city', 'region', 'zipcode']
identity_columns = [col for col in expected_columns if col in player_info.columns]

st.write("✅ Available identity columns:", identity_columns)
missing_columns = [col for col in expected_columns if col not in identity_columns]
if missing_columns:
    st.warning(f"⚠️ Missing identity columns: {missing_columns}")

if len(identity_columns) < 2:
    st.warning("Not enough identity columns available for fuzzy matching.")
    fuzzy_df = pd.DataFrame()
else:
    cleaned_info = player_info.dropna(subset=identity_columns).copy()
    cleaned_info['identity_string'] = cleaned_info[identity_columns].astype(str).apply(lambda row: ' '.join(row.str.lower().str.strip()), axis=1)

    subset = cleaned_info[['player_id', 'identity_string']].head(300)
    fuzzy_results = []
    for i in range(len(subset)):
        for j in range(i + 1, len(subset)):
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
