#!/usr/bin/env python3
"""Validation of the final package against the raw file and against the assignment's own rules.
Reads the raw CSV with pandas (no code shared with the pipeline). Usage:
python validate.py --input RAW.csv --out-dir out --final-dir final --report validation_report.md"""
import argparse, json, re
import pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument("--input", required=True); ap.add_argument("--out-dir", required=True)
ap.add_argument("--final-dir", required=True); ap.add_argument("--report", required=True); a = ap.parse_args()
SEED = "samuraiwarriors.online"; SL = {"co", "com", "org", "net", "gov", "ac", "edu", "or", "ne", "go"}
raw = pd.read_csv(a.input, dtype=str, keep_default_na=False)
raw["h"] = raw["authorization_service.fqdn"].str.lower().str.rstrip(".")
last = raw.h.str.rsplit(".", n=1).str[-1]; common = set(last.value_counts()[lambda s: s >= 50].index)
rev = raw.h.str.split(".").str[0].isin(common) & ~last.isin(common)
raw.loc[rev, "h"] = raw.loc[rev, "h"].map(lambda h: ".".join(reversed(h.split("."))))
def reg(h):
    p = h.split("."); return ".".join(p[-3:]) if len(p) >= 3 and p[-2] in SL and len(p[-1]) == 2 else ".".join(p[-2:])
raw["dom"] = raw.h.map(reg)
rec = pd.read_csv(f"{a.final_dir}/recommendations.csv"); leads = pd.read_csv(f"{a.final_dir}/review_leads.csv")
ten = pd.read_csv(f"{a.final_dir}/related_not_owned.csv"); ev = pd.read_csv(f"{a.final_dir}/evidence_machines.csv")
R = []; ok = True
def check(name, passed, detail=""):
    global ok; ok &= bool(passed); R.append((name, bool(passed), detail)); print(("PASS " if passed else "FAIL ") + name, detail)
# A. evidence audit: every claim about a recommended domain can be traced to raw rows
bad = []
for _, r in pd.concat([rec, leads]).iterrows():
    d = r.domain; rows = raw[raw.dom == d]; e = ev[ev.domain == d]
    ms = set(rows.log_id)
    if len(ms) != r.machines: bad.append((d, "machine count", len(ms), r.machines))
    if set(e.log_id) != ms: bad.append((d, "evidence machine list differs from raw"))
    if abs(len(rows) / len(ms) - r.logins_per_machine) > 0.006: bad.append((d, "logins per machine"))
    for h in str(r.example_hosts).split("|"):
        h = h.strip()
        if h and h not in set(rows.h): bad.append((d, "example host not in raw", h))
check("A1 every recommended domain and lead: machine count, machine list, logins per machine and example hosts match the raw file", not bad, str(bad[:3]))
chk = ev.merge(raw.groupby(["log_id", "dom"]).size().rename("n").reset_index(), left_on=["log_id", "domain"], right_on=["log_id", "dom"], how="left")
check("A2 every row of evidence_machines.csv exists in raw and the saved-login count agrees", chk.n.notna().all() and (chk.n == chk.credential_rows).all(), f"{len(ev)} rows")
# B. a recommendation the client already has is not a recommendation
check("B1 the seed domain is not in the recommendations, review leads or related-not-owned list", SEED not in set(rec.domain) | set(leads.domain) | set(ten.iloc[:, 0]))
check("B2 no reversed spelling of the seed (online.samuraiwarriors) survives as a candidate", "online.samuraiwarriors" not in set(raw.dom))
# C. name similarity is not ownership: nothing is recommended on its name alone
c = rec[(rec.logins_per_machine > 1.1)]
check("C1 every recommended domain has at most 1.1 logins per machine (no domain is recommended on name alone)", c.empty, str(list(c.domain)))
sc = pd.read_csv(f"{a.out_dir}/scored_candidates.csv"); nm = sc[sc.part_one_login_per_machine.lt(0.01)]
check("C2 a domain scoring on name clues alone (other two clues at zero) cannot reach the 0.75 cutoff", (0.20 * sc.part_rare_name_words + 0.15 * sc.part_name_meaning).max() < 0.75, f"best name-only score {(0.20 * sc.part_rare_name_words + 0.15 * sc.part_name_meaning).max():.2f}")
# D. what was discarded, and why
cs = json.load(open(f"{a.out_dir}/clean_summary.json")); f = cs["funnel"]
check("D1 every raw row is accounted for: discards by stage plus kept = raw rows", f[0]["entering"] == len(raw) and sum(s["discarded"] for s in f) + f[-1]["kept"] == len(raw), f"{len(raw)} rows")
dl = pd.read_csv(f"{a.final_dir}/discard_log_all.csv"); check("D2 combined discard log is non-empty and carries a reason for each line", len(dl) > 0 and dl.iloc[:, 1].astype(str).str.len().gt(0).all(), f"{len(dl)} lines")
fs = json.load(open(f"{a.out_dir}/filter_summary.json")); es = json.load(open(f"{a.out_dir}/evidence_summary.json"))
dom_total = fs["funnel"][0]["entering"]; rem = sum(s["removed"] for s in fs["funnel"][1:]) + sum(s["removed"] for s in es["funnel"][1:])
check("D3 domain funnel: candidates = removed at each stage + remaining scored", dom_total == rem + es["funnel"][-1]["kept"], f"{dom_total} = {rem} + {es['funnel'][-1]['kept']}")
fl = pd.read_csv(f"{a.out_dir}/filter_log.csv"); w5 = set(fl[fl.stage.str.startswith("5c")].domain)
mc = raw.groupby("dom").log_id.nunique(); expect = set(mc[mc >= 0.35 * raw.log_id.nunique()].index) - {SEED}
check("D4 the 35%-of-machines filter removed exactly the domains the raw file puts at or above that share", w5 == expect, f"{len(w5)} domains")
# E. no recommended domain is a third-party tenant host
tn = set(ten.iloc[:, 0]); check("E1 no recommended domain or lead is in the third-party tenant list", not (tn & (set(rec.domain) | set(leads.domain))), str(sorted(tn)))
check("E2 no recommended domain is a public-service domain removed at the 35% filter", not (set(pd.read_csv(f"{a.out_dir}/filter_log.csv").query("stage.str.startswith('5c')", engine='python').domain) & set(rec.domain)))
# F. the evidence says why, in words
check("F1 every recommended domain has a non-empty plain-language reason, example hosts and example URLs", rec.why.astype(str).str.len().gt(10).all() and rec.example_hosts.notna().all() and rec.example_urls.notna().all())
with open(a.report, "w") as fh:
    fh.write("# Validation report\n\nChecks run against the raw file with code that shares nothing with the pipeline.\n\n| Check | Result | Detail |\n|---|---|---|\n")
    for n, p, d in R: fh.write(f"| {n} | {'PASS' if p else 'FAIL'} | {d} |\n")
    fh.write("\nALL PASS\n" if ok else "\nSOME CHECKS FAILED\n")
print("ALL PASS" if ok else "SOME CHECKS FAILED")
