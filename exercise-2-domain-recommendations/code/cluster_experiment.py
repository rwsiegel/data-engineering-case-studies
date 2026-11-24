#!/usr/bin/env python3
"""Time-boxed clustering experiment. Groups domains by how they behave and read, without using the score.
Usage: python cluster_experiment.py --out-dir out
Uses HDBSCAN (a method that finds dense groups and labels everything else as 'noise')."""
import argparse, json
import numpy as np, pandas as pd
from scipy.sparse import csr_matrix
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import StandardScaler
ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", required=True); ap.add_argument("--min-machines", type=int, default=5)
a = ap.parse_args()
o = pd.read_csv(f"{a.out_dir}/observations.csv"); sem = pd.read_csv(f"{a.out_dir}/name_semantics.csv").set_index("domain")
fs = json.load(open(f"{a.out_dir}/filter_summary.json")); n_m = fs["machines"]
g = o.groupby("domain").agg(machines=("log_id", "nunique"), rows=("credential_rows", "sum"))
g = g[(g.machines >= a.min_machines) & (g.machines < fs["cutoff_machines"]) & (~g.index.isin(["samuraiwarriors.online"]))]
g["lpm"] = g.rows / g.machines
sc = pd.read_csv(f"{a.out_dir}/scored_candidates.csv").set_index("domain")
g["rare"] = sc.rare_word_share.reindex(g.index)            # only exists for domains passing the 10-machine gate
g["name_sim"] = sem.similarity_to_seed_brand.reindex(g.index).fillna(0)
# who-appears-with-whom: binary matrix domain x machine, reduced to 5 numbers per domain
dm = o[o.domain.isin(g.index)]
di = {d: i for i, d in enumerate(g.index)}; mi = {m: i for i, m in enumerate(dm.log_id.unique())}
M = csr_matrix((np.ones(len(dm)), (dm.domain.map(di), dm.log_id.map(mi))), shape=(len(di), len(mi)))
svd = TruncatedSVD(5, random_state=0).fit_transform(M)
F = pd.DataFrame({"log_machines": np.log10(g.machines), "lpm": np.minimum(g.lpm, 4), "name_sim": g.name_sim}, index=g.index)
for i in range(5): F[f"svd{i}"] = svd[:, i]
X = StandardScaler().fit_transform(F)
lab = HDBSCAN(min_cluster_size=8).fit_predict(X)
g["cluster"] = lab
rec = set(pd.read_csv(f"{a.out_dir}/../final/recommendations.csv").domain) if False else set(sc[sc.score >= .75].index)
g["recommended"] = g.index.isin(rec)
res = []
for c in sorted(set(lab)):
    s = g[g.cluster == c]
    res.append({"cluster": int(c), "domains": len(s), "recommended_in_cluster": int(s.recommended.sum()), "median_machines": float(s.machines.median()),
                "median_logins_per_machine": round(float(s.lpm.median()), 2), "examples": list(s.sort_values("machines", ascending=False).index[:6])})
g.to_csv(f"{a.out_dir}/cluster_experiment.csv")
json.dump(res, open(f"{a.out_dir}/cluster_experiment.json", "w"), indent=2)
print(len(g), "domains clustered"); print(json.dumps(res, indent=1)[:3500])
