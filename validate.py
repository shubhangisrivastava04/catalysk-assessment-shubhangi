import pandas as pd
import json
from datetime import date

# load data
df = pd.read_csv("transactions.csv")

# preprocessing for validation checks
df["amount_num"]  = pd.to_numeric(df["amount"], errors="coerce")
df["date_parsed"] = pd.to_datetime(df["transaction_date"], errors="coerce")

report = []

def make_result(check_id, name, failed_ids):
    """Build a single check result dict."""
    affected = len(failed_ids)
    status   = "FAIL" if affected > 0 else "PASS"
    sample   = list(failed_ids[:3])
    result   = {
        "check_id":     check_id,
        "name":         name,
        "status":       status,
        "affected_rows": affected,
        "sample_ids":   sample,
    }
    flag = "FAIL" if status == "FAIL" else "PASS"
    print(f"  {flag}  {check_id}  {name:<35}  affected: {affected}")
    return result


print("=" * 60)
print("     VALIDATION REPORT")
print("=" * 60)
print()

# V-01 : duplicate transaction IDs
dupes = df[df.duplicated("transaction_id", keep=False)]["transaction_id"]
report.append(make_result("V-01", "Duplicate transaction IDs", dupes.tolist()))

# V-02 : date parseability
bad_dates = df[df["date_parsed"].isna()]["transaction_id"]
report.append(make_result("V-02", "Date parseability", bad_dates.tolist()))

# V-03 : amount numeric 
bad_amount = df[df["amount_num"].isna()]["transaction_id"]
report.append(make_result("V-03", "Amount numeric", bad_amount.tolist()))

# V-04 : sign-type consistency 
# DR must be negative, CR must be positive
# only check rows where amount is actually numeric
valid_amt = df[df["amount_num"].notna()]
mismatch  = valid_amt[
    ((valid_amt["transaction_type"] == "DR") & (valid_amt["amount_num"] > 0)) |
    ((valid_amt["transaction_type"] == "CR") & (valid_amt["amount_num"] < 0))
]["transaction_id"]
report.append(make_result("V-04", "Sign-type consistency", mismatch.tolist()))

# V-05 : future dates 
today       = pd.Timestamp(date.today())
valid_dates = df[df["date_parsed"].notna()]
future      = valid_dates[valid_dates["date_parsed"] > today]["transaction_id"]
report.append(make_result("V-05", "Future dates", future.tolist()))

# V-06 : empty narration
empty_narr = df[
    df["full_narration"].isna() |
    df["full_narration"].astype(str).str.strip().eq("")
]["transaction_id"]
report.append(make_result("V-06", "Empty narration", empty_narr.tolist()))

# V-07 : null-like tokens in any column
# check every column for placeholder values
NULL_TOKENS = {"nan", "null", "n/a", "missing", "-", "?", "na", "none"}
 
def has_null_token(val):
    if pd.isna(val):
        return False          # real NaN is not a null-like token, it's a true null
    s = str(val)
    if s.strip() == "":       # whitespace-only string
        return True
    return s.strip().lower() in NULL_TOKENS
 
null_token_mask = df.apply(lambda col: col.map(has_null_token)).any(axis=1)
null_token_ids  = df[null_token_mask]["transaction_id"]
report.append(make_result("V-07", "Null-like tokens", null_token_ids.tolist()))


# summary
print()
passed = sum(1 for r in report if r["status"] == "PASS")
failed = sum(1 for r in report if r["status"] == "FAIL")
print(f"Summary : {passed} passed, {failed} failed out of {len(report)} checks")

# json output for report generation
with open("validation_report.json", "w") as f:
    json.dump(report, f, indent=2)

print(f"\nvalidation_report.json written successfully.\n")
