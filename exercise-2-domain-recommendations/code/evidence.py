#!/usr/bin/env python3
"""Stage 6-7: evidence, scoring and ranking of candidate domains.
Reads out/ files from clean.py, candidates.py and semantic.py. Writes:
  scored_candidates.csv       every domain that passes the gate, with all features and score parts
  ranked_recommendations.csv  top N with the evidence a reviewer needs to dispute each one
  review_set_aside.csv        domains that pass the filters but fail the gate (little or no machine evidence)
  evidence_summary.json       funnel and checks
Score = weighted sum of named parts, each 0..1 (weights below). Name features are flags with a small weight; the gate means
no domain is ranked on name alone. Usage: python evidence.py --out-dir out [--min-machines 10] [--top 25]
"""
import argparse, collections, csv, json, math, os

W = {"co_occurrence": 0.30, "one_login_per_machine": 0.35, "rare_name_words": 0.20, "name_meaning": 0.15}   # name parts total 0.35, so name alone cannot top the ranking
SEED_BRAND = "samuraiwarriors"

def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1): cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def read(p): return list(csv.DictReader(open(p, newline="", encoding="utf-8")))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", required=True)
    ap.add_argument("--min-machines", type=int, default=10); ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--login-count", choices=["rows", "urls"], default="rows", help="rows: every saved-login row (default). urls: distinct login URLs per machine, so repeated rows count once")
    a = ap.parse_args(); o = a.out_dir
    cand = {r["domain"]: r for r in read(f"{o}/candidates.csv")}
    if a.login_count == "urls":                                  # variant: repeated rows count once per distinct login URL
        us = collections.Counter()
        for r in read(f"{o}/observations.csv"): us[r["domain"]] += int(r["distinct_urls"])
        for d, r in cand.items(): r["credential_rows"] = str(us[d])
    sem = {r["domain"]: r for r in read(f"{o}/name_semantics.csv")}
    public = [r["domain"] for r in read(f"{o}/filter_log.csv") if r["stage"].startswith("5c")]
    pub_rows = {r["domain"]: r for r in read(f"{o}/filter_log.csv") if r["stage"].startswith("5c")}
    wc = collections.Counter(w for r in sem.values() for w in set(r["name_words"].split("+")))
    n_m = json.load(open(f"{o}/filter_summary.json"))["machines"]          # total machines in the data
    # ---- gate
    tenants = {d: r for d, r in cand.items() if int(r["seed_stem_in_a_host"])}          # seed name appears in a host under another registrable domain
    cand2 = {d: r for d, r in cand.items() if d not in tenants}
    passed = {d: r for d, r in cand2.items() if int(r["machines"]) >= a.min_machines}
    aside = {d: r for d, r in cand2.items() if d not in passed}
    funnel = [{"stage": "candidates after filters 5a-5c", "entering": len(cand), "removed": 0, "kept": len(cand)},
              {"stage": "6a third-party tenants (set aside: related, not owned)", "entering": len(cand), "removed": len(tenants), "kept": len(cand2)},
              {"stage": f"6b gate: seen on >= {a.min_machines} machines", "entering": len(cand2), "removed": len(aside), "kept": len(passed)}]
    # ---- features
    def feats(d, r):
        m = int(r["machines"]); rows = int(r["credential_rows"]); lpm = rows / m
        words = sem[d]["name_words"].split("+"); brand = sem[d]["brand_words"].replace("+", "")
        sim = float(sem[d]["similarity_to_seed_brand"]) if sem[d]["similarity_to_seed_brand"] else 0.0
        rare = sum(1 for w in words if wc[w] <= 15) / len(words)
        L = lev(brand, SEED_BRAND)
        return {"domain": d, "machines": m, "machine_share": float(r["machine_share"]), "login_rows": rows, "logins_per_machine": round(lpm, 2),
                "name_words": sem[d]["name_words"], "brand_words": sem[d]["brand_words"], "name_similarity_to_seed": round(sim, 3),
                "rare_word_share": round(rare, 2), "levenshtein_to_seed_brand": L, "levenshtein_normalized": round(L / max(len(brand), len(SEED_BRAND)), 2),
                "seed_stem_in_domain": int(r["seed_stem_in_domain"]), "seed_stem_in_a_host": int(r["seed_stem_in_a_host"])}
    F = {d: feats(d, r) for d, r in passed.items()}
    P = {d: {"machines": int(pub_rows[d]["machines"]), "lpm": None} for d in public}
    # reference profiles on non-name behaviour: machine count and logins per machine (log scale), standardized
    def bx(m, lpm): return (math.log10(m), math.log10(max(lpm, 1)))
    allx = [bx(f["machines"], f["logins_per_machine"]) for f in F.values()]
    mu = [sum(x[i] for x in allx) / len(allx) for i in (0, 1)]; sd = [max((sum((x[i] - mu[i]) ** 2 for x in allx) / len(allx)) ** .5, 1e-9) for i in (0, 1)]
    z = lambda x: tuple((x[i] - mu[i]) / sd[i] for i in (0, 1))
    # the public services removed at 5c have no logins-per-machine in candidates.csv; read them from observations
    obs_rows = collections.Counter(); obs_m = collections.defaultdict(set)
    for r in read(f"{o}/observations.csv"):
        if r["domain"] in P: obs_rows[r["domain"]] += int(r["credential_rows"]); obs_m[r["domain"]].add(r["log_id"])
    pub_z = [z(bx(len(obs_m[d]), obs_rows[d] / len(obs_m[d]))) for d in public if obs_m[d]]
    c_pub = tuple(sum(v[i] for v in pub_z) / len(pub_z) for i in (0, 1))
    dist = lambda u, v: math.hypot(u[0] - v[0], u[1] - v[1])
    cut = max(int(r["machines"]) for r in pub_rows.values()) if pub_rows else n_m
    cut = min(pub_rows[d]["machines"] and int(pub_rows[d]["machines"]) for d in pub_rows) if pub_rows else n_m     # smallest machine count removed as widespread
    for f in F.values():
        f["distance_to_public_profile"] = round(dist(z(bx(f["machines"], f["logins_per_machine"])), c_pub), 2)      # reported, not scored
        parts = {"co_occurrence": min(1.0, math.log10(f["machines"]) / math.log10(cut)), "one_login_per_machine": min(1.0, 1 / f["logins_per_machine"]),
                 "rare_name_words": f["rare_word_share"], "name_meaning": max(0.0, f["name_similarity_to_seed"])}
        f.update({f"part_{k}": round(v, 3) for k, v in parts.items()}); f["score"] = round(sum(W[k] * v for k, v in parts.items()), 4)
    ranked = sorted(F.values(), key=lambda f: -f["score"])
    with open(f"{o}/scored_candidates.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ranked[0])); w.writeheader(); w.writerows(ranked)
    # ---- evidence for the top N
    hosts = collections.defaultdict(set); urls = collections.defaultdict(set); mach = collections.defaultdict(list)
    top = {f["domain"] for f in ranked[:a.top]}
    for r in read(f"{o}/observations.csv"):
        d = r["domain"]
        if d in top:
            hosts[d].add(r["example_fqdn"]); urls[d].add(r["example_url"])
            if len(mach[d]) < 5: mach[d].append(r["log_id"][:8])
    with open(f"{o}/ranked_recommendations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["rank", "domain", "score", "machines", "machine_share", "logins_per_machine", "name_words", "name_similarity_to_seed",
                                        "levenshtein_to_seed_brand", "rare_word_share", "seed_stem_in_domain", "distance_to_public_profile",
                                        "why", "example_hosts", "example_urls", "example_machines"])
        for i, f in enumerate(ranked[:a.top], 1):
            d = f["domain"]; why = []
            why.append(f"on {f['machines']} of {n_m} machines ({f['machine_share']:.0%}), {f['logins_per_machine']} logins per machine")
            if f["seed_stem_in_domain"]: why.append("name contains the seed stem (a flag, not proof)")
            if f["rare_word_share"] >= 0.5: why.append("name words are rare in this dataset")
            if f["name_similarity_to_seed"] >= 0.3: why.append(f"name meaning close to the seed ({f['name_similarity_to_seed']})")
            if f["logins_per_machine"] <= 1.1: why.append("one login per machine, unlike widespread public services (2 to 6)")
            w.writerow([i, d, f["score"], f["machines"], f["machine_share"], f["logins_per_machine"], f["name_words"], f["name_similarity_to_seed"], f["levenshtein_to_seed_brand"],
                        f["rare_word_share"], f["seed_stem_in_domain"], f["distance_to_public_profile"], "; ".join(why),
                        " | ".join(sorted(hosts[d])[:5]), " | ".join(sorted(urls[d])[:3]), " ".join(mach[d])])
    with open(f"{o}/review_set_aside.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["domain", "machines", "reason"])
        for d, r in sorted(tenants.items(), key=lambda kv: -int(kv[1]["machines"])): w.writerow([d, r["machines"], "third-party provider: a host under it carries the seed name (a tenant of the client). Shows the client uses it; the client does not own it"])
        for d, r in sorted(aside.items(), key=lambda kv: -int(kv[1]["machines"])):
            if int(r["seed_stem_in_domain"]) or int(r["seed_stem_in_a_host"]): w.writerow([d, r["machines"], "carries the seed name but is on too few machines to rank; review manually"])
    checks = {f"{x['stage']}: kept + removed = entering": x["kept"] + x["removed"] == x["entering"] for x in funnel[1:]}
    checks.update({"every gated domain is scored": len(F) == funnel[-1]["kept"],
              "weights sum to 1": abs(sum(W.values()) - 1) < 1e-9})
    json.dump({"weights": W, "min_machines": a.min_machines, "funnel": funnel, "public_reference_n": len(pub_z), "co_occurrence_full_credit_at_machines": cut, "checks": checks}, open(f"{o}/evidence_summary.json", "w"), indent=2)
    print("funnel:", [(s["stage"], s["entering"], s["removed"], s["kept"]) for s in funnel], "| checks", all(checks.values()))
    print(f"\n{'#':>2} {'domain':30s} {'score':>5} {'mach':>4} {'lpm':>5} {'sim':>5} {'rare':>4} {'dPub':>5}")
    for i, f in enumerate(ranked[:30], 1): print(f"{i:2d} {f['domain']:30s} {f['score']:.3f} {f['machines']:4d} {f['logins_per_machine']:5.1f} {f['name_similarity_to_seed']:5.2f} {f['rare_word_share']:4.1f} {f['distance_to_public_profile']:5.2f}")

if __name__ == "__main__":
    main()
