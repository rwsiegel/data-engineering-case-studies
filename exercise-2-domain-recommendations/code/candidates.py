#!/usr/bin/env python3
"""Stages 4-5: candidate generation and filters (domain level).

Reads out/observations.csv (from clean.py). Writes to --out-dir:
  candidates.csv   domains that survive the filters, with the facts used for scoring
  filter_log.csv   every removed or set-aside domain, with stage, reason, machines and share
  filter_summary.json  domain funnel and reconciliation checks
Every stage satisfies kept + removed = entering (counted in domains).
Usage: python candidates.py --out-dir out [--seed samuraiwarriors.online] [--public-share 0.35]
"""
import argparse, collections, csv, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True); ap.add_argument("--seed", default="samuraiwarriors.online")
    ap.add_argument("--public-share", type=float, default=0.35, help="remove domains seen on at least this share of machines")
    a = ap.parse_args()
    stem = a.seed.split(".")[0]
    mach = set(); dom = collections.OrderedDict()
    with open(os.path.join(a.out_dir, "observations.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            mach.add(r["log_id"]); d = dom.setdefault(r["domain"], {"machines": set(), "rows": 0, "fqdns": 0, "urls": 0, "internal": False, "stem_in_host": False})
            d["machines"].add(r["log_id"]); d["rows"] += int(r["credential_rows"]); d["fqdns"] += int(r["distinct_fqdns"]); d["urls"] += int(r["distinct_urls"])
            d["internal"] |= r["internal_name"] == "1"; d["stem_in_host"] |= stem in r["example_fqdn"]
    n_m = len(mach); cut = a.public_share * n_m
    funnel = []; log = []; cur = dict(dom)
    def stage(name, rule):
        nonlocal cur
        out = {k: v for k, v in cur.items() if rule(k, v) is None}
        for k, v in cur.items():
            why = rule(k, v)
            if why: log.append([name, why, k, len(v["machines"]), round(len(v["machines"]) / n_m, 4), int(v["internal"]), int(stem in k)])
        funnel.append({"stage": name, "entering": len(cur), "removed": len(cur) - len(out), "kept": len(out)}); cur = out
    funnel.append({"stage": "4 candidate generation (every domain seen on a seed machine)", "entering": len(dom), "removed": 0, "kept": len(dom)})
    stage("5a seed domain", lambda k, v: "the client already has this domain" if k == a.seed else None)
    stage("5b internal or non-public name (set aside, not discarded)", lambda k, v: "non-public top-level domain, internal naming; set aside for the related-not-owned list" if v["internal"] else None)
    stage(f"5c widespread domain (seen on >= {a.public_share:.0%} of machines)", lambda k, v: f"seen on {len(v['machines'])} of {n_m} machines; too common to indicate ownership" if len(v["machines"]) >= cut else None)
    with open(os.path.join(a.out_dir, "candidates.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["domain", "machines", "machine_share", "credential_rows", "fqdns_and_urls_seen", "seed_stem_in_domain", "seed_stem_in_a_host"])
        for k, v in sorted(cur.items(), key=lambda kv: -len(kv[1]["machines"])):
            w.writerow([k, len(v["machines"]), round(len(v["machines"]) / n_m, 4), v["rows"], f"{v['fqdns']}/{v['urls']}", int(stem in k), int(v["stem_in_host"] and stem not in k)])
    with open(os.path.join(a.out_dir, "filter_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["stage", "reason", "domain", "machines", "machine_share", "internal_name", "seed_stem_in_domain"]); w.writerows(log)
    checks = {f"{s['stage']}: kept + removed = entering": s["kept"] + s["removed"] == s["entering"] for s in funnel}
    checks["each stage enters with what the last kept"] = all(funnel[i]["entering"] == funnel[i - 1]["kept"] for i in range(1, len(funnel)))
    checks["filter log rows = total removed"] = len(log) == sum(s["removed"] for s in funnel)
    json.dump({"machines": n_m, "public_share": a.public_share, "cutoff_machines": cut, "funnel": funnel, "checks": checks}, open(os.path.join(a.out_dir, "filter_summary.json"), "w"), indent=2)
    for s in funnel: print(f"{s['stage']}: {s['entering']:,} - {s['removed']:,} = {s['kept']:,}")
    print("checks:", all(checks.values()))

if __name__ == "__main__":
    main()
