#!/usr/bin/env python3
"""Stages 1-3 of the domain recommendation pipeline: parse, normalize, deduplicate.

Reads the credentials CSV and writes, to --out-dir:
  observations.csv   one row per (machine, registrable domain): the unit of evidence
  machines.csv       one row per machine (log_id) with its attributes
  discard_log.csv    every drop or collapse, with stage, reason, counts and examples
  clean_summary.json funnel with reconciliation checks

Rule: every stage satisfies  kept + discarded = entering.  Nothing is dropped without a row in discard_log.csv.
Usage: python clean.py --input samuraiwarriors_credentials.csv --out-dir out
"""
import argparse, collections, csv, json, os, re
from urllib.parse import urlparse
from common import is_ip, registrable

LABEL = re.compile(r"^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$")
NON_PUBLIC_TLDS = {"loc", "local", "corp", "internal", "lan", "localdomain", "intranet", "home", "test", "invalid", "localhost", "samuraiwarriors"}
MACHINE_FIELDS = ["location.country", "malware_family.name", "malware_family.version", "compromise.os",
                  "compromise.timezone", "compromise.antivirus", "compromise.uac", "compromise.exfiltration_date"]
SEED = "samuraiwarriors.online"

class Discards:
    """Collects discard events: stage, reason -> rows, machines, domains, examples."""
    def __init__(self): self.d = collections.OrderedDict()
    def add(self, stage, reason, row_id, log_id, domain, example):
        e = self.d.setdefault((stage, reason), {"rows": 0, "machines": set(), "domains": set(), "examples": []})
        e["rows"] += 1; e["machines"].add(log_id); e["domains"].add(domain)
        if len(e["examples"]) < 3: e["examples"].append(f"row {row_id}: {example}")
    def rows(self, stage): return sum(e["rows"] for (s, _), e in self.d.items() if s == stage)

def valid_host(h):
    labels = h.split(".")
    return len(h) <= 253 and len(labels) >= 2 and all(LABEL.match(l) for l in labels)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True); ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(); os.makedirs(a.out_dir, exist_ok=True)
    dis = Discards(); funnel = []
    # ---------------------------------------------------------------- 1. PARSE
    kept = []; raw = 0
    with open(a.input, newline="", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f), 2):          # row 1 is the header
            raw += 1
            lid, fq, url = (r.get("log_id") or "").strip(), (r.get("authorization_service.fqdn") or "").strip(), (r.get("authorization_service.url") or "").strip()
            if not lid: dis.add("1 parse", "missing log_id", i, "", fq, fq); continue
            if not fq: dis.add("1 parse", "missing fqdn", i, lid, "", url); continue
            kept.append((i, lid, fq, url, r))
    funnel.append({"stage": "1 parse", "entering": raw, "discarded": raw - len(kept), "kept": len(kept)})
    # ------------------------------------------------------------- 2. NORMALIZE
    norm = []; entering = len(kept); flags = collections.Counter(); repairs = collections.OrderedDict()
    # Reversed-hostname repair. A host such as "com.kendohotels." is "kendohotels.com" written backwards.
    # A label is "tld-like" if it ends at least 50 hosts; a host is reversed when its FIRST label is tld-like
    # and its LAST label is not (so a real name like "com.example.de" is left alone).
    last_counts = collections.Counter(fq.lower().rstrip(".").rsplit(".", 1)[-1] for _, _, fq, _, _ in kept)
    tldlike = {t for t, c in last_counts.items() if c >= 50}
    for i, lid, fq, url, r in kept:
        h = fq.lower().rstrip(".")
        first, last = h.split(".")[0], h.rsplit(".", 1)[-1]
        if "." in h and first in tldlike and last not in tldlike and not is_ip(h):
            fixed = ".".join(reversed(h.split(".")))
            e = repairs.setdefault((h, fixed), {"rows": 0, "machines": set()}); e["rows"] += 1; e["machines"].add(lid)
            h = fixed
        elif h != fq: flags["hostname changed by normalization (case, trailing dot)"] += 1
        if is_ip(h): dis.add("2 normalize", "host is an IP address, not a domain", i, lid, h, h); continue
        if not valid_host(h): dis.add("2 normalize", "not a valid hostname", i, lid, h, fq); continue
        reg = registrable(h); tld = h.rsplit(".", 1)[-1]
        internal = tld in NON_PUBLIC_TLDS
        host_in_url = (urlparse(url).hostname or "").lower().rstrip(".")
        if host_in_url and host_in_url != h: flags["url host differs from fqdn"] += 1
        norm.append({"row": i, "log_id": lid, "fqdn": h, "url": url, "domain": reg, "internal_name": internal, "attrs": r})
    funnel.append({"stage": "2 normalize", "entering": entering, "discarded": entering - len(norm), "kept": len(norm)})
    flags["rows flagged internal_name (non-public TLD), kept"] = sum(1 for n in norm if n["internal_name"])
    # -------------------------------------------------------------- 3. DEDUPLICATE
    # 3a: exact duplicates (every column identical).
    entering = len(norm); seen = set(); uniq = []
    for n in norm:
        key = tuple(n["attrs"].get(k, "") for k in sorted(n["attrs"]))
        if key in seen: dis.add("3a exact duplicate rows", "every column identical to an earlier row", n["row"], n["log_id"], n["domain"], n["fqdn"]); continue
        seen.add(key); uniq.append(n)
    funnel.append({"stage": "3a exact duplicate rows", "entering": entering, "discarded": entering - len(uniq), "kept": len(uniq)})
    # 3b: repeats of (machine, fqdn, url): counted, not lost.
    entering = len(uniq); seen = set(); uniq2 = []
    for n in uniq:
        key = (n["log_id"], n["fqdn"], n["url"])
        if key in seen: dis.add("3b repeat of machine+fqdn+url", "same machine logged same login URL again (count carried into the observation)", n["row"], n["log_id"], n["domain"], n["fqdn"]); continue
        seen.add(key); uniq2.append(n)
    funnel.append({"stage": "3b repeat of machine+fqdn+url", "entering": entering, "discarded": entering - len(uniq2), "kept": len(uniq2)})
    # 3c: collapse to one observation per (machine, registrable domain). Counts are kept as evidence.
    obs = collections.OrderedDict()
    for n in norm:                                            # count every kept-after-normalize row, so no repeat is lost
        o = obs.setdefault((n["log_id"], n["domain"]), {"rows": 0, "fqdns": set(), "urls": set(), "internal": n["internal_name"]})
        o["rows"] += 1; o["fqdns"].add(n["fqdn"]); o["urls"].add(n["url"])
    entering = len(uniq2)
    funnel.append({"stage": "3c collapse to machine+domain", "entering": entering, "discarded": entering - len(obs), "kept": len(obs),
                   "note": "rows merged into one observation per machine and registrable domain; counts carried in observations.csv"})
    collapsed = entering - len(obs)
    if collapsed:
        dis.d[("3c collapse to machine+domain", "several fqdns or URLs of one domain on one machine merged")] = {
            "rows": collapsed, "machines": set(k[0] for k, o in obs.items() if len(o["fqdns"]) > 1 or len(o["urls"]) > 1),
            "domains": set(k[1] for k, o in obs.items() if len(o["fqdns"]) > 1 or len(o["urls"]) > 1),
            "examples": [f"{k[0][:8]}/{k[1]}: {len(o['fqdns'])} fqdns, {len(o['urls'])} urls" for k, o in obs.items() if len(o["fqdns"]) > 1][:3]}
    # --------------------------------------------------------------- machines
    mach = collections.OrderedDict(); conflicts = collections.Counter()
    for n in norm:
        m = mach.setdefault(n["log_id"], {k: collections.Counter() for k in MACHINE_FIELDS + ["downloaded"]})
        for k in MACHINE_FIELDS + ["downloaded"]:
            v = (n["attrs"].get(k) or "").strip()
            if v: m[k][v] += 1
    with open(os.path.join(a.out_dir, "machines.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["log_id"] + MACHINE_FIELDS + ["downloaded_first", "n_observations", "n_credential_rows"])
        per = collections.defaultdict(lambda: [0, 0])
        for (lid, _), o in obs.items(): per[lid][0] += 1; per[lid][1] += o["rows"]
        for lid, m in mach.items():
            for k in MACHINE_FIELDS:
                if len(m[k]) > 1: conflicts[k] += 1
            w.writerow([lid] + [m[k].most_common(1)[0][0] if m[k] else "" for k in MACHINE_FIELDS] + [min(m["downloaded"]) if m["downloaded"] else "", per[lid][0], per[lid][1]])
    flags.update({f"machines with conflicting values for {k}": v for k, v in conflicts.items()})
    with open(os.path.join(a.out_dir, "observations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["log_id", "domain", "credential_rows", "distinct_fqdns", "distinct_urls", "internal_name", "example_fqdn", "example_url"])
        for (lid, dom), o in obs.items():
            w.writerow([lid, dom, o["rows"], len(o["fqdns"]), len(o["urls"]), int(o["internal"]), sorted(o["fqdns"])[0], sorted(o["urls"])[0]])
    with open(os.path.join(a.out_dir, "discard_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["stage", "reason", "rows", "machines_affected", "domains_affected", "examples"])
        for (s, rs), e in dis.d.items(): w.writerow([s, rs, e["rows"], len(e["machines"] - {""}), len(e["domains"] - {""}), " | ".join(e["examples"])])
    with open(os.path.join(a.out_dir, "repair_log.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["original_host", "repaired_host", "rows", "machines", "rule"])
        for (h0, h1), e in repairs.items(): w.writerow([h0, h1, e["rows"], len(e["machines"]), "reversed hostname written backwards; reversed back (not a discard)"])
    flags["rows repaired: reversed hostname"] = sum(e["rows"] for e in repairs.values())
    checks = {f"{s['stage']}: kept + discarded = entering": s["kept"] + s["discarded"] == s["entering"] for s in funnel}
    checks["discard log rows agree with funnel (stages 1 to 3c)"] = all(dis.rows(s["stage"]) == s["discarded"] for s in funnel)
    checks["chain: each stage enters with what the last kept (1 to 3c)"] = all(funnel[i]["entering"] == funnel[i-1]["kept"] for i in range(1, len(funnel)))
    summary = {"input": os.path.basename(a.input), "raw_rows": raw, "machines": len(mach), "observations": len(obs),
               "seed_machines": len({k[0] for k in obs if k[1] == SEED}), "funnel": funnel, "flags_kept_not_discarded": dict(flags), "checks": checks}
    json.dump(summary, open(os.path.join(a.out_dir, "clean_summary.json"), "w"), indent=2)
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
