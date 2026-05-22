import pandas as pd
import json

# load + clean data
df = pd.read_csv("transactions.csv")
df["amount_num"]  = pd.to_numeric(df["amount"], errors="coerce")
df["date_parsed"] = pd.to_datetime(df["transaction_date"], errors="coerce")
df["merchant"]    = df["full_narration"].str.split("/").str[1]

# apply the same cleaning logic as validate.py findings:
# dropping bad amounts, bad dates, sentinel dates, duplicate IDs, and junk consumer IDs
clean = df[
    df["amount_num"].notna() &
    df["date_parsed"].notna() &
    (df["date_parsed"].dt.year < 2050) &
    (~df.duplicated("transaction_id", keep="first")) &
    (df["consumer_id"].str.startswith("USER_"))
].copy()

print("=" * 65)
print("  ANALYSIS REPORT")
print("=" * 65)
print(f"\n  Working dataset : {len(clean):,} rows | {clean['consumer_id'].nunique()} consumers")


# 3A : RFM CONSUMER BEHAVIOUR SEGMENTATION
print("\n" + "=" * 65)
print("  3A - Consumer Behaviour Segmentation (RFM)")
print("=" * 65)

print("""
  WHAT  : Each consumer is scored using RFM analysis:
            Recency   -> days since last transaction
            Frequency -> total number of transactions
            Monetary  -> total debit spend

          Each metric is divided into quartiles (1 - 4),
          where a higher score indicates better engagement.
          The three values are combined to form an overall
          RFM score, which is then used for customer segmentation.

  HOW   : pd.qcut is used to assign quartile-based scores.
          Recency is inversed because lower recency means
          the customer was active more recently.

          The final segment is assigned using the average
          of the R, F, and M scores.

  WHY   : RFM is widely used in fintech and customer analytics
          to identify high-value and low-engagement consumers.

          For example:
            Champions   -> active and high-value users
            At Risk     -> previously active but declining
            Hibernating -> low activity and possible churn

          Merchant Diversity is added as an extra feature to
          capture spending behaviour across different merchants,
          not just total spend.
""")

snapshot = pd.Timestamp("2024-12-31")

# build base RFM table
rfm = clean.groupby("consumer_id").agg(
    last_txn          = ("date_parsed", "max"),
    frequency         = ("transaction_id", "count"),
    merchant_diversity= ("merchant", "nunique"),
).reset_index()

dr = clean[clean["transaction_type"] == "DR"]
monetary = dr.groupby("consumer_id")["amount_num"].sum().abs().reset_index()
monetary.columns = ["consumer_id", "monetary"]

rfm = rfm.merge(monetary, on="consumer_id", how="left").fillna(0)
rfm["recency"] = (snapshot - rfm["last_txn"]).dt.days

# quartile scoring (1 - 4)
rfm["R"] = pd.qcut(rfm["recency"],   q=4, labels=[4, 3, 2, 1]).astype(int)  # lower recency = better
rfm["F"] = pd.qcut(rfm["frequency"], q=4, labels=[1, 2, 3, 4], duplicates="drop").astype(int)
rfm["M"] = pd.qcut(rfm["monetary"],  q=4, labels=[1, 2, 3, 4]).astype(int)
rfm["D"] = pd.qcut(rfm["merchant_diversity"], q=4, labels=[1, 2, 3, 4], duplicates="drop").astype(int)

rfm["rfm_score"] = (rfm["R"] + rfm["F"] + rfm["M"] + rfm["D"]) / 4

def assign_segment(score):
    if score >= 3.5:
        return "Champion"
    elif score >= 2.5:
        return "Loyal"
    elif score >= 1.5:
        return "At Risk"
    else:
        return "Hibernating"

rfm["segment"] = rfm["rfm_score"].apply(assign_segment)

# segment summary
seg_summary = rfm.groupby("segment").agg(
    consumers  = ("consumer_id", "count"),
    avg_spend  = ("monetary", "mean"),
    avg_freq   = ("frequency", "mean"),
    avg_recency= ("recency", "mean"),
).round(1)

print(f"  {'Segment':<14} {'Consumers':>10} {'Avg Spend (Rs.)':>16} {'Avg Freq':>10} {'Avg Recency':>13}")
print(f"  {'─'*14} {'─'*10} {'─'*16} {'─'*10} {'─'*13}")
for seg, row in seg_summary.iterrows():
    print(f"  {seg:<14} {int(row['consumers']):>10} {row['avg_spend']:>16,.0f} {row['avg_freq']:>10.1f} {row['avg_recency']:>13.1f}")

print(f"\n  Top 5 Champions:")
champions = rfm[rfm["segment"] == "Champion"].sort_values("rfm_score", ascending=False)
for _, row in champions.head(5).iterrows():
    print(f"    {row['consumer_id']}  score={row['rfm_score']:.2f}  spend=Rs.{row['monetary']:,.0f}  freq={row['frequency']}")


# 3B : OUTLIER DETECTION
print("\n" + "=" * 65)
print("  3B - Outlier Detection (IQR)")
print("=" * 65)

print("""
  WHAT  : Flag consumers whose total debit spend or transaction
          frequency falls outside 1.5x the interquartile range
          (IQR), the standard statistical definition of an outlier.
          Two separate checks — spend outliers and frequency outliers.

  HOW   : For each metric, compute Q1, Q3, and IQR = Q3 - Q1.
          Lower fence = Q1 - 1.5*IQR, upper fence = Q3 + 1.5*IQR.
          Any consumer outside either fence is flagged.
          IQR is robust to extreme values, unlike z-score which
          can be skewed by the very outliers we're looking for.

  WHY   : The spec specifically flags "very few or extremely high
          transactions overall will look suspicious by default."
          IQR handles both ends - unusually low AND unusually high -
          without assuming a normal distribution. A consumer with
          1 transaction is as suspicious as one with 3x the average.
""")

def iqr_outliers(series, label):
    Q1, Q3 = series.quantile(0.25), series.quantile(0.75)
    IQR    = Q3 - Q1
    low    = Q1 - 1.5 * IQR
    high   = Q3 + 1.5 * IQR
    out    = rfm[(series < low) | (series > high)][["consumer_id", label]]
    print(f"\n  {label.upper()} outliers  (fence: {low:.0f} - {high:.0f})")
    if out.empty:
        print("    None found.")
    else:
        for _, row in out.iterrows():
            direction = "LOW" if row[label] < low else "HIGH"
            print(f"    {row['consumer_id']}  {label}={row[label]:,.1f}  [{direction}]")
    return out

spend_out = iqr_outliers(rfm["monetary"],  "monetary")
freq_out  = iqr_outliers(rfm["frequency"], "frequency")

all_outlier_ids = set(spend_out["consumer_id"]) | set(freq_out["consumer_id"])
print(f"\n  Total flagged consumers : {len(all_outlier_ids)}")


# 3C : CARBON FOOTPRINT PROXY SCORE
print("\n" + "=" * 65)
print("  3C - Carbon Footprint Proxy Score (Sustainability Insight)")
print("=" * 65)

print("""
  WHAT  : A simple per-consumer carbon proxy score derived from
          merchant spending patterns - classifying merchants into
          high-carbon, mid-carbon, and low-carbon categories, then
          computing a weighted net score per consumer.

  HOW   : Merchants are tagged by carbon impact using domain logic:
            HIGH (+2) : BPCL, INDIAN_OIL (fuel/petrol)
            HIGH (+1) : MCD, DOMINOS (meat-heavy fast food)
            MID  (+0.5): SWIGGY, ZOMATO, AMAZON, FLIPKART (delivery)
            LOW  (-1) : BLR_METRO (public transport)
            LOW  (-0.5): BIGBASKET, TATA_POWER (local/green utility)
          Score = sum of (spend * weight) per consumer, normalised
          by total spend so high earners aren't unfairly penalised.

  WHY   : Catalysk Green Solutions focuses on sustainability.
          Transaction data is an underutilised signal for carbon
          behaviour. This score could power a 'Green Index' feature,
          flag high-emission consumers for carbon offset nudges,
          or feed into ESG-linked credit pricing.
""")

# these are proxy weights based on general carbon intensity of the merchant category
CARBON_WEIGHTS = {
    "BPCL":        2.0,
    "INDIAN_OIL":  2.0,
    "MCD":         1.0,
    "DOMINOS":     1.0,
    "SWIGGY":      0.5,
    "ZOMATO":      0.5,
    "AMAZON":      0.5,
    "FLIPKART":    0.5,
    "BLR_METRO":  -1.0,
    "OLA":        -0.3,   # ride-share - lower than private fuel
    "UBER":       -0.3,
    "BIGBASKET":  -0.5,
    "TATA_POWER": -0.5,
}

carbon_txns = clean[clean["merchant"].isin(CARBON_WEIGHTS)].copy()
carbon_txns["carbon_weight"] = carbon_txns["merchant"].map(CARBON_WEIGHTS)
carbon_txns["weighted_spend"] = carbon_txns["amount_num"].abs() * carbon_txns["carbon_weight"]

carbon_score = carbon_txns.groupby("consumer_id").agg(
    raw_score    = ("weighted_spend", "sum"),
    carbon_spend = ("amount_num",     lambda x: x.abs().sum()),
).reset_index()

# normalise by total spend so it's a relative score not an absolute one
total_spend = clean.groupby("consumer_id")["amount_num"].apply(
    lambda x: x.abs().sum()
).reset_index()
total_spend.columns = ["consumer_id", "total_spend"]

carbon_score = carbon_score.merge(total_spend, on="consumer_id")
carbon_score["carbon_index"] = (
    carbon_score["raw_score"] / carbon_score["total_spend"] * 100
).round(2)

def carbon_label(score):
    if score > 1.5:   return "High Emission"
    elif score > 0.3: return "Moderate"
    elif score > -0.3:return "Neutral"
    else:             return "Green"

carbon_score["carbon_label"] = carbon_score["carbon_index"].apply(carbon_label)
carbon_score = carbon_score.sort_values("carbon_index", ascending=False)

print(f"  {'Consumer':<14} {'Carbon Index':>14} {'Label'}")
print(f"  {'─'*14} {'─'*14} {'─'*20}")
for _, row in carbon_score.iterrows():
    print(f"  {row['consumer_id']:<14} {row['carbon_index']:>14.2f}   {row['carbon_label']}")

# key numbers 
green_consumers  = (carbon_score["carbon_label"] == "Green").sum()
high_consumers   = (carbon_score["carbon_label"] == "High Emission").sum()
avg_index        = carbon_score["carbon_index"].mean()
top_emitter      = carbon_score.iloc[0]
greenest         = carbon_score.iloc[-1]

total_bpcl_spend    = clean[clean["merchant"].isin(["BPCL","INDIAN_OIL"])]["amount_num"].abs().sum()
total_metro_spend   = clean[clean["merchant"] == "BLR_METRO"]["amount_num"].abs().sum()

print(f"""
  ── Key Numbers ──────────────────────────────────────────────
  Green consumers      : {green_consumers} / {len(carbon_score)}
  High-emission        : {high_consumers} / {len(carbon_score)}
  Average carbon index : {avg_index:.2f}
  Top emitter          : {top_emitter['consumer_id']} (index: {top_emitter['carbon_index']:.2f})
  Greenest consumer    : {greenest['consumer_id']} (index: {greenest['carbon_index']:.2f})
  Total fuel spend     : Rs. {total_bpcl_spend:,.0f}  (BPCL + INDIAN_OIL)
  Total metro spend    : Rs. {total_metro_spend:,.0f}  (BLR_METRO)
  Fuel : Metro ratio   : {total_bpcl_spend/total_metro_spend:.1f}x
""")


# save outputs for report generation
rfm_out = rfm[["consumer_id","recency","frequency","monetary",
               "merchant_diversity","R","F","M","D","rfm_score","segment"]]
rfm_out.to_csv("rfm_segments.csv", index=False)

carbon_score.to_csv("carbon_scores.csv", index=False)

print("  rfm_segments.csv   saved")
print("  carbon_scores.csv  saved")
print("=" * 65)