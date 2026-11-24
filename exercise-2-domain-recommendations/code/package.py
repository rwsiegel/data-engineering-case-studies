#!/usr/bin/env python3
"""Stage 8: package the final deliverables from the stage outputs in out/.
Writes to --final-dir: recommendations.csv, review_leads.csv, related_not_owned.csv, evidence_machines.csv,
discard_log_all.csv, funnel.md.   Usage: python package.py --out-dir out --final-dir final [--cutoff 0.75]"""
import argparse, collections, csv, json, os

def read(p): return list(csv.DictReader(open(p, newline="", encoding="utf-8")))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out-dir", required=True); ap.add_argument("--final-dir", required=True)
    ap.add_argument("--cutoff", type=float, default=0.75, help="score at or above this is recommended")
    ap.add_argument("--lead-floor", type=float, default=0.70, help="review leads: score in [floor, cutoff) with one login per machine")
    a = ap.parse_args(); o, fd = a.out_dir, a.final_dir; os.makedirs(fd, exist_ok=True)
    scored = read(f"{o}/scored_candidates.csv"); ev = {r["domain"]: r for r in read(f"{o}/ranked_recommendations.csv")}
    rec = [r for r in scored if float(r["score"]) >= a.cutoff]
    leads = [r for r in scored if a.lead_floor <= float(r["score"]) < a.cutoff and float(r["logins_per_machine"]) <= 1.0]
    keep = {r["domain"] for r in rec + leads}
    # evidence rows were written for the top N; extend to leads if needed
    missing = [d for d in keep if d not in ev]
    assert not missing, f"re-run evidence.py with a larger --top: {missing}"
    rank = {r["domain"]: i for i, r in enumerate(scored, 1)}
    cols = ["rank", "domain", "score", "machines", "machine_share", "logins_per_machine", "name_words", "name_similarity_to_seed", "levenshtein_to_seed_brand",
            "rare_word_share", "seed_stem_in_domain", "distance_to_public_profile", "why", "example_hosts", "example_urls"]
    for name, group, tag in (("recommendations.csv", rec, "recommended"), ("review_leads.csv", leads, "review lead: below the cutoff, one login per machine, needs a human look")):
        with open(f"{fd}/{name}", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(cols + ["evidence_tier", "status"])
            for r in group:
                e = ev[r["domain"]]; tier = "A" if e["seed_stem_in_domain"] == "1" else "B"      # A: carries the seed name; B: behavior and theme only, confirm with the client
                w.writerow([rank[r["domain"]]] + [e[c] for c in cols[1:]] + [tier, tag])
    # all supporting machines and URLs
    mach = collections.defaultdict(list)
    for r in read(f"{o}/observations.csv"):
        if r["domain"] in keep: mach[r["domain"]].append(r)
    with open(f"{fd}/evidence_machines.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["domain", "log_id", "credential_rows", "distinct_fqdns", "distinct_urls", "example_fqdn", "example_url"])
        for d in [r["domain"] for r in rec + leads]:
            for r in mach[d]: w.writerow([d, r["log_id"], r["credential_rows"], r["distinct_fqdns"], r["distinct_urls"], r["example_fqdn"], r["example_url"]])
    with open(f"{fd}/related_not_owned.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["domain", "machines", "reason"])
        for r in read(f"{o}/review_set_aside.csv"):
            if "third-party" in r["reason"]: w.writerow([r["domain"], r["machines"], r["reason"]])
    # ---- combined discard log: record-level stages, then domain-level stages
    cs = json.load(open(f"{o}/clean_summary.json")); fs = json.load(open(f"{o}/filter_summary.json")); es = json.load(open(f"{o}/evidence_summary.json"))
    with open(f"{fd}/discard_log_all.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["unit", "stage", "reason", "count", "machines_affected", "domains_affected", "examples"])
        for r in read(f"{o}/discard_log.csv"): w.writerow(["credential rows", r["stage"], r["reason"], r["rows"], r["machines_affected"], r["domains_affected"], r["examples"]])
        for r in read(f"{o}/filter_log.csv"): w.writerow(["domains", r["stage"], r["reason"], 1, r["machines"], r["domain"], f"{r['domain']} on {r['machines']} machines ({float(r['machine_share']):.0%})"])
        tenants = [r for r in read(f"{o}/review_set_aside.csv") if "third-party" in r["reason"]]
        for r in tenants: w.writerow(["domains", "6a third-party tenants", r["reason"], 1, r["machines"], r["domain"], f"{r['domain']} on {r['machines']} machines"])
        gate = [s for s in es["funnel"] if s["stage"].startswith("6b")][0]
        w.writerow(["domains", gate["stage"], f"seen on fewer than {es['min_machines']} machines: too little co-occurrence evidence to rank (name-matching ones are in review_set_aside.csv)", gate["removed"], "", gate["removed"], f"see scored_candidates.csv for the {len(scored)} that passed"])
        below = len(scored) - len(rec) - len(leads)
        w.writerow(["domains", "7 cutoff", f"scored below {a.cutoff} and not a review lead", below, "", below, "scored_candidates.csv lists every one with its score"])
    # ---- funnel
    L = ["# Funnel: from credential rows to recommended domains\n", "## Credential rows (clean.py)\n", "| Stage | Entering | Discarded | Kept |", "|---|---:|---:|---:|"]
    for s in cs["funnel"]: L.append(f"| {s['stage']} | {s['entering']:,} | {s['discarded']:,} | {s['kept']:,} |")
    rp = os.path.join(a.out_dir, "repair_log.csv")
    if os.path.exists(rp):
        L += ["", "Repairs (not discards): hostnames written backwards were reversed before counting.", "", "| Original | Repaired | Rows | Machines |", "|---|---|---:|---:|"]
        for r in read(rp): L.append(f"| {r['original_host']} | {r['repaired_host']} | {r['rows']} | {r['machines']} |")
    L += ["", f"Result: {cs['observations']:,} observations (machine and domain) over {cs['machines']} machines.\n", "## Domains (candidates.py, evidence.py, package.py)\n", "| Stage | Entering | Removed | Kept |", "|---|---:|---:|---:|"]
    L.append(f"| 4 candidates (every domain on a seed machine) | {fs['funnel'][0]['entering']:,} | 0 | {fs['funnel'][0]['kept']:,} |")
    for s in fs["funnel"][1:]: L.append(f"| {s['stage']} | {s['entering']:,} | {s['removed']:,} | {s['kept']:,} |")
    for s in es["funnel"][1:]: L.append(f"| {s['stage']} | {s['entering']:,} | {s['removed']:,} | {s['kept']:,} |")
    L.append(f"| 7 cutoff: score >= {a.cutoff} | {len(scored):,} | {len(scored) - len(rec):,} | {len(rec):,} |")
    L += ["", f"Recommended: {len(rec)} domains. Review leads: {len(leads)} ({', '.join(r['domain'] for r in leads)}). Set aside as related, not owned: {len(tenants)} third-party tenants.",
          "Checks: " + ("all pass" if all(cs["checks"].values()) and all(fs["checks"].values()) and all(es["checks"].values()) else "FAILURE, see summaries")]
    open(f"{fd}/funnel.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L)); print(f"\nrecommended {len(rec)}, leads {len(leads)}")

if __name__ == "__main__":
    main()
