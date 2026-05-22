import pandas as pd
from datetime import date

# load data
df = pd.read_csv("transactions.csv")

# convert amount to numeric (coerce errors to NaN)
df["amount_num"] = pd.to_numeric(df["amount"], errors="coerce")

# parse transaction_date to datetime (coerce errors to NaT)
df["date_parsed"] = pd.to_datetime(df["transaction_date"], errors="coerce")

# extract merchant from full_narration (format "PAYMENT/merchant/otherinfo")
df["merchant"] = df["full_narration"].str.split("/").str[1]

print("=" * 60)
print("  CATALYSK GREEN SOLUTIONS — EDA REPORT")
print("=" * 60)


# basic overview
total_rows = len(df)
unique_consumers = df["consumer_id"].nunique()

print(f"\nOVERVIEW")
print(f"  Total rows          : {total_rows:,}")
print(f"  Unique consumers    : {unique_consumers}")
print(f"  Columns             : {list(df.columns[:7])}")  


# date range analysis
valid_dates = df["date_parsed"].dropna()
# obvious sentinel dates (year >= 2026) excluded
real_dates = valid_dates[valid_dates.dt.year < 2026]

date_min = real_dates.min().date()
date_max = real_dates.max().date()

print(f"\nDATE RANGE (excluding sentinel/future dates)")
print(f"  Earliest            : {date_min}")
print(f"  Latest              : {date_max}")
print(f"  Span                : {(date_max - date_min).days} days")


# transaction mode distribution
mode_dist = df["transaction_mode"].value_counts()

print(f"\nTRANSACTION MODE DISTRIBUTION")
for mode, count in mode_dist.items():
    bar = "█" * (count // 10)
    print(f"  {mode:<10} {count:>5}  {bar}")


# debit vs credit analysis
dr = df[df["transaction_type"] == "DR"]
cr = df[df["transaction_type"] == "CR"]

dr_count = len(dr)
cr_count = len(cr)
total_txns = dr_count + cr_count

dr_amount = dr["amount_num"].sum()
cr_amount = cr["amount_num"].sum()
total_amount = df["amount_num"].sum()

print(f"\nDEBIT vs CREDIT")
print(f"  Debit  txns : {dr_count:>5} ({dr_count/total_txns*100:.1f}% of count)")
print(f"  Credit txns : {cr_count:>5} ({cr_count/total_txns*100:.1f}% of count)")
print(f"  Debit  total amount : ₹{dr_amount:>15,.2f}  ({dr_amount/total_amount*100:.1f}% of net flow)")
print(f"  Credit total amount : ₹{cr_amount:>15,.2f}  ({cr_amount/total_amount*100:.1f}% of net flow)")
print(f"  Net flow            : ₹{total_amount:>15,.2f}")


# top consumers by debit volume
top_debit = (
    dr.groupby("consumer_id")["amount_num"]
    .sum()
    .sort_values()          # most negative = highest debit
    .head(5)
    .reset_index()
)
top_debit.columns = ["consumer_id", "total_debit"]
top_debit["total_debit_abs"] = top_debit["total_debit"].abs()

print(f"\nTOP 5 CONSUMERS BY TOTAL DEBIT VOLUME")
for _, row in top_debit.iterrows():
    print(f"  {row['consumer_id']}  ₹{row['total_debit_abs']:>10,.2f}")


# top merchants by transaction count
merchant_dist = df["merchant"].value_counts().head(15)

print(f"\nTOP 15 MERCHANTS (by transaction count)")
for merchant, count in merchant_dist.items():
    print(f"  {str(merchant):<20} {count:>4}")


# monthly transaction volume 
df["month"] = df["date_parsed"].dt.to_period("M")
monthly = df[df["date_parsed"].dt.year < 2026].groupby("month").size()

print(f"\nMONTHLY TRANSACTION VOLUME (2024)")
for period, count in monthly.items():
    bar = "█" * (count // 5)
    print(f"  {period}  {count:>4}  {bar}")


# save summary to Excel for report generation
overview_data = {
    "Metric": [
        "Total Rows",
        "Unique Consumers",
        "Date Min",
        "Date Max",
        "Span (days)",
        "Debit Transactions",
        "Credit Transactions",
        "Total Debit Amount (₹)",
        "Total Credit Amount (₹)",
        "Net Flow (₹)",
    ],
    "Value": [
        total_rows,
        unique_consumers,
        str(date_min),
        str(date_max),
        (date_max - date_min).days,
        dr_count,
        cr_count,
        round(dr_amount, 2),
        round(cr_amount, 2),
        round(total_amount, 2),
    ],
}

with pd.ExcelWriter("eda_report.xlsx", engine="openpyxl") as writer:
    pd.DataFrame(overview_data).to_excel(writer, sheet_name="Overview", index=False)
    mode_dist.reset_index().to_excel(writer, sheet_name="Mode Distribution", index=False)
    top_debit.to_excel(writer, sheet_name="Top Debit Consumers", index=False)
    merchant_dist.reset_index().to_excel(writer, sheet_name="Top Merchants", index=False)
    monthly.reset_index().to_excel(writer, sheet_name="Monthly Volume", index=False)

print(f"\nEDA report saved to eda_report.xlsx")