# Catalysk Green Solutions: a data quality pipeline for fintech transaction data

---

## Setup & Running

**Requirements:** Python >= 3.9

```bash
# 1. Clone the repo
git clone https://github.com/shubhangisrivastava04/catalysk-assessment-shubhangi.git
cd catalysk-assessment-shubhangi

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run each script in order
python explore.py      # → prints EDA to terminal, saves eda_report.xlsx
python validate.py     # → prints validation results, saves validation_report.json
python analysis.py     # → prints segmentation + outlier + carbon findings, saves rfm_segments.csv and carbon_scores.csv
```

All scripts expect `transactions.csv` to be in the same directory.

---

## Findings Summary

### Data Quality Issues (Task 2)

All seven validation checks failed:

| Check | Status | Affected Rows | Issue |
|-------|--------|---------------|-------|
| V-01 | FAIL | 116 | Duplicate `transaction_id` values |
| V-02 | FAIL | 21 | Unparseable dates (e.g. `"not_a_date"`) |
| V-03 | FAIL | 19 | Non-numeric amounts (string `"INVALID"` in amount column) |
| V-04 | FAIL | 68 | Sign-type mismatch — DR rows with positive amount or CR rows with negative amount |
| V-05 | FAIL | 20 | Sentinel future dates (`2099-12-31`) — placeholder values, not real transactions |
| V-06 | FAIL | 105 | Null `full_narration` values |
| V-07 | FAIL | 11 | Placeholder strings (`"MISSING"`, `"-"`, whitespace-only) across columns |

The most impactful issue is V-04 (68 rows) — sign-type mismatches would cause incorrect debit/credit accounting if the data were fed into any downstream aggregation.

### EDA Findings (Task 1)

- 2,060 rows across 51 unique consumers, spanning January – December 2024
- Transaction modes are roughly evenly distributed across CARD, RTGS, IMPS, NEFT, ATM, and UPI (~315–360 each), with 2 junk mode values (`MISSING`, `-`) caught by V-07
- 75.9% of transactions are debits; credit amount (₹1.95 crore) is dramatically larger than debit total (₹35.7 lakh) — the net positive flow is unusual for a consumer dataset and may reflect salary/EMI data where large credits dominate
- March and August are peak transaction months — possible salary cycle alignment or seasonal spending
- Top 5 debit consumers by volume: USER_10048, USER_10009, USER_10021, USER_10017, USER_10004

### Merchant Seasonality

SALARY_CR (161 txns) and EMI_CR (159 txns) are the top two "merchants" by count — consistent with a salaried consumer base making regular EMI repayments. Retail merchants like PORTRONICS, DMART, and AIRTEL show stable monthly distribution with a mild uptick in March and August, aligning with the broader volume peaks.

---

## 3C — Sustainability Insight

Across the cleaned dataset of 50 consumers, total spending at fuel merchants (BPCL and INDIAN_OIL) is ₹2.83 lakh versus ₹1.54 lakh at BLR Metro — a 1.8x fuel-to-public-transport ratio. When merchants are weighted by estimated carbon intensity and each consumer is assigned a Carbon Proxy Index (normalised by their total spend), 45 out of 50 consumers fall into the "High Emission" category, and not a single consumer qualifies as "Green." This was found by tagging merchants into carbon tiers (fuel = high, metro/local grocery = low, delivery platforms = mid) and computing a weighted spend score per consumer. For a product team at Catalysk Green Solutions, this is an immediately actionable signal: the consumer base skews heavily carbon-positive, which makes it a strong candidate for green nudge features — for example, flagging consumers with a high BPCL-to-Metro ratio and surfacing a "switch 2 fuel trips to Metro this month" prompt, or pricing ESG-linked credit rewards for consumers who improve their Carbon Index over time.

---

## Assumptions Documented

- **V-04 zero amounts:** Transactions with `amount = 0` are flagged as sign-type violations. A zero-amount transaction is neither a valid debit nor credit, regardless of the `transaction_type` field.
- **V-07 scope:** V-07 checks all columns independently of V-06. A whitespace-only string in `full_narration` is caught by V-07 even though V-06 also covers that column — they are distinct checks (null vs placeholder string).
- **Sentinel dates:** `2099-12-31` rows are treated as sentinel/placeholder values (a common banking system pattern when the real date is unknown). They are excluded from date range calculations in EDA but flagged by V-05 and retained in the dataset for downstream handling.
- **Clean dataset for analysis:** analysis.py drops rows with invalid amounts, unparseable/sentinel dates, duplicate transaction IDs (keeping first occurrence), and a junk consumer ID (`?`) - 1,944 rows remain for the 50 valid consumers.
- **Carbon weights:** Merchant carbon tiers are proxy classifications based on general category logic (fuel > delivery > public transport), not verified emissions data. They are clearly labelled as estimates in the code.

---

## If I Had Another Hour

I'd focus on two things. First, the V-01 duplicate handling is currently conservative, we keep the first occurrence and discard the rest. With more time I'd investigate whether duplicates are exact duplicates (same amount, date, narration) or near-duplicates with different amounts, which would change how they should be resolved. Second, the RFM segmentation uses fixed quartile thresholds which work well for this dataset but don't generalise. I'd add a silhouette score check on K-Means clustering to see whether the data actually supports 4 natural segments or a different number, and compare that against the RFM buckets to validate the segment boundaries.