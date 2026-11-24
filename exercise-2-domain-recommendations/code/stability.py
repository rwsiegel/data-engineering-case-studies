#!/usr/bin/env python3
"""How stable is the recommended list? Three tests on the scored candidates. Usage: python stability.py --out-dir out"""
import argparse, json
import numpy as np, pandas as pd
ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", required=True); ap.add_argument("--trials", type=int, default=2000)
a = ap.parse_args()
d = pd.read_csv(f"{a.out_dir}/scored_candidates.csv")
parts = ["part_co_occurrence", "part_one_login_per_machine", "part_rare_name_words", "part_name_meaning"]
names = ["co-occurrence", "one login per machine", "rare name words", "name meaning"]
w0 = np.array([.30, .35, .20, .15]); X = d[parts].values
base = set(d[d.score >= .75].domain); n = len(base)
out = {"base_count": n}
# Test 1: change every weight by a random factor between 0.5 and 1.5 (then rescale to sum to 1); keep the top n.
rng = np.random.default_rng(0); keep = {x: 0 for x in base}; same = []
for _ in range(a.trials):
    w = w0 * rng.uniform(.5, 1.5, 4); w /= w.sum()
    top = set(d.domain.iloc[np.argsort(-(X @ w))[:n]]); same.append(len(top & base))
    for x in top & base: keep[x] += 1
out["weight_change"] = {"trials": a.trials, "average_kept": round(float(np.mean(same)), 2), "worst_trial_kept": int(min(same)),
                        "share_of_trials_each_domain_stays": {k: round(v / a.trials, 3) for k, v in sorted(keep.items(), key=lambda kv: kv[1])}}
# Test 2: remove one clue at a time (the other three weights rescaled to sum to 1).
out["drop_one_clue"] = {}
for i, nm in enumerate(names):
    w = w0.copy(); w[i] = 0; w /= w.sum()
    top = set(d.domain.iloc[np.argsort(-(X @ w))[:n]])
    out["drop_one_clue"][nm] = {"kept_of_base": len(top & base), "dropped": sorted(base - top), "added": sorted(top - base)}
# Test 3: move the score cutoff.
out["cutoff"] = {str(c): int((d.score >= c).sum()) for c in (.65, .70, .75, .80, .85)}
json.dump(out, open(f"{a.out_dir}/stability.json", "w"), indent=2)
print(json.dumps(out, indent=2))
