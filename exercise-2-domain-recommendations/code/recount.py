#!/usr/bin/env python3
"""Independent recount for Exercise 2. Shares NO code with clean.py / candidates.py / evidence.py.
It reads the raw CSV with pandas, rebuilds the counts a different way, and compares them with the
pipeline outputs. Usage: python recount.py --input RAW.csv --out-dir out --final-dir final
"""
import argparse, json, re
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True); ap.add_argument("--out-dir", required=True); ap.add_argument("--final-dir", required=True)
a = ap.parse_args()

raw = pd.read_csv(a.input, dtype=str, keep_default_na=False)
res = {}
res["raw_rows"] = len(raw)
raw["h"] = raw["authorization_service.fqdn"].str.strip().str.lower().str.rstrip(".")
df = raw[(raw.log_id.str.strip() != "") & (raw.h != "")].copy()
res["after_parse"] = len(df)
ip = df.h.str.fullmatch(r"\d{1,3}(\.\d{1,3}){3}")
df = df[~ip]
valid = df.h.map(lambda h: len(h) <= 253 and len(h.split(".")) >= 2 and all(re.fullmatch(r"[a-z0-9]([a-z0-9_-]*[a-z0-9])?", l) for l in h.split(".")))
df = df[valid].copy()
res["after_normalize"] = len(df)

# reversed hostnames: first label is a common top-level label and the last label is rare
last = df.h.str.rsplit(".", n=1).str[-1]
common = set(last.value_counts()[lambda s: s >= 50].index)
first = df.h.str.split(".").str[0]
rev = first.isin(common) & ~last.isin(common)
res["reversed_rows_repaired"] = int(rev.sum())
df.loc[rev, "h"] = df.loc[rev, "h"].map(lambda h: ".".join(reversed(h.split("."))))

# exact duplicate rows (all original columns)
cols = [c for c in raw.columns if c != "h"]
n0 = len(df); dup = df.duplicated(subset=cols, keep="first")
res["exact_duplicate_rows"] = int(dup.sum())
uniq = df[~dup]
res["after_exact_dups"] = len(uniq)
k3b = uniq.duplicated(subset=["log_id", "h", "authorization_service.url"], keep="first")
res["repeat_machine_fqdn_url"] = int(k3b.sum())
res["after_repeats"] = int((~k3b).sum())

SL = {"co", "com", "org", "net", "gov", "ac", "edu", "or", "ne", "go"}
def reg(h):
    p = h.split(".")
    return ".".join(p[-3:]) if len(p) >= 3 and p[-2] in SL and len(p[-1]) == 2 else ".".join(p[-2:])
df["dom"] = df.h.map(reg)
obs = df.groupby(["log_id", "dom"]).size().reset_index(name="rows")
res["observations"] = len(obs)
res["machines"] = obs.log_id.nunique()
per_dom = obs.groupby("dom").agg(machines=("log_id", "nunique"), rows=("rows", "sum"))

# compare with the pipeline
o = pd.read_csv(f"{a.out_dir}/observations.csv")
summary = json.load(open(f"{a.out_dir}/clean_summary.json"))
checks = {
    "raw rows match": res["raw_rows"] == summary["raw_rows"],
    "rows after normalize match": res["after_normalize"] == summary["funnel"][1]["kept"],
    "exact duplicates match": res["exact_duplicate_rows"] == summary["funnel"][2]["discarded"],
    "repeat rows match": res["repeat_machine_fqdn_url"] == summary["funnel"][3]["discarded"],
    "observations match": res["observations"] == summary["observations"],
    "machines match": res["machines"] == summary["machines"],
    "per-domain machine counts match for every domain": per_dom.machines.sort_index().equals(o.groupby("domain").log_id.nunique().sort_index()),
    "per-domain credential rows match for every domain": per_dom.rows.sort_index().equals(o.groupby("domain").credential_rows.sum().sort_index()),
}
rec = pd.read_csv(f"{a.final_dir}/recommendations.csv")
rec_ok = True; diffs = []
for _, r in rec.iterrows():
    m, rows = int(per_dom.loc[r.domain, "machines"]), int(per_dom.loc[r.domain, "rows"])
    if m != r.machines or abs(rows / m - r.logins_per_machine) > 0.006: rec_ok = False; diffs.append(r.domain)
checks["machines and logins per machine match the raw file for all recommended domains"] = rec_ok
# the funnel: widespread domains
cut = 0.35 * res["machines"]
res["widespread_domains_at_35pct"] = int((per_dom.machines >= cut).sum())
fs = json.load(open(f"{a.out_dir}/filter_summary.json"))
# the count includes the seed, which stage 5a removes first
checks["widespread-domain count matches the filter stage (seed excluded)"] = res["widespread_domains_at_35pct"] - 1 == fs["funnel"][3]["removed"]
res["checks"] = checks; res["recommended_mismatches"] = diffs
print(json.dumps(res, indent=2))
print("ALL PASS" if all(checks.values()) else "SOME CHECKS FAILED")
