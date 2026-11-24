"""Profile a CT JSON Lines file: field presence, fingerprint formats, update types, duplicates, precert/final pairs."""
import argparse, base64, collections, hashlib, json, re, os

PATHS = [
    "message_type", "data.update_type", "data.cert_index", "data.cert_link", "data.seen",
    "data.source.name", "data.chain", "data.leaf_cert.fingerprint", "data.leaf_cert.serial_number",
    "data.leaf_cert.all_domains", "data.leaf_cert.not_before", "data.leaf_cert.not_after",
    "data.leaf_cert.as_der", "data.leaf_cert.subject.CN", "data.leaf_cert.subject.aggregated",
    "data.leaf_cert.extensions", "data.leaf_cert.extensions.authorityKeyIdentifier",
]

def get(o, path):
    for k in path.split("."):
        if not isinstance(o, dict) or k not in o:
            return False, None
        o = o[k]
    return True, o

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    size = os.path.getsize(a.input)

    n = bad = 0
    present = collections.Counter(); empty = collections.Counter()
    fp_formats = collections.Counter()
    sha_ok = sha_bad = sha_err = 0; sha_examples = []
    update = collections.Counter(); poison_x = collections.Counter(); source = collections.Counter()
    leaf = []                      # (line_no, key, update_type, source, serial, aki, domains, nb, na)
    for line_no, line in enumerate(open(a.input, encoding="utf-8", errors="replace"), 1):
        n += 1
        try: o = json.loads(line)
        except Exception: bad += 1; continue
        for p in PATHS:
            ok, v = get(o, p)
            if ok:
                present[p] += 1
                if v is None or v == "" or v == [] or v == {}: empty[p] += 1
        _, fp = get(o, "data.leaf_cert.fingerprint")
        _, ut = get(o, "data.update_type")
        update[ut] += 1
        _, ext = get(o, "data.leaf_cert.extensions")
        ext = ext if isinstance(ext, dict) else {}
        poison_x[(ut, "poison" if ext.get("ctlPoisonByte") else "no-poison", "sct" if "ctlSignedCertificateTimestamp" in ext else "no-sct")] += 1
        _, sn = get(o, "data.source.name"); source[sn] += 1
        if not isinstance(fp, str):
            continue
        key = re.sub(r"[:\s]", "", fp).lower()
        fp_formats[(len(fp), "colons" if ":" in fp else "no-colons",
                    "upper" if fp == fp.upper() and fp != fp.lower() else "lower" if fp == fp.lower() and fp != fp.upper() else "mixed/none")] += 1
        _, der = get(o, "data.leaf_cert.as_der")
        try:
            raw = base64.b64decode(der)
            h = (hashlib.sha1(raw) if len(key) == 40 else hashlib.sha256(raw)).hexdigest()
            if h == key: sha_ok += 1
            else:
                sha_bad += 1
                if len(sha_examples) < 5: sha_examples.append(line_no)
        except Exception:
            sha_err += 1
        _, serial = get(o, "data.leaf_cert.serial_number")
        _, aki = get(o, "data.leaf_cert.extensions.authorityKeyIdentifier")
        _, doms = get(o, "data.leaf_cert.all_domains")
        _, nb = get(o, "data.leaf_cert.not_before"); _, na = get(o, "data.leaf_cert.not_after")
        leaf.append((line_no, key, ut, sn, serial, aki, tuple(sorted(doms)) if isinstance(doms, list) else None, nb, na))

    # duplicates by exact (cleaned) fingerprint
    by_key = collections.defaultdict(list)
    for r in leaf: by_key[r[1]].append(r)
    sets = {k: v for k, v in by_key.items() if len(v) >= 2}
    set_sizes = collections.Counter(len(v) for v in sets.values())
    set_types = collections.Counter(tuple(sorted(x[2] for x in v)) for v in sets.values())
    same_log = sum(1 for v in sets.values() if len({x[3] for x in v}) < len(v))
    log_pairs = collections.Counter(tuple(sorted({x[3] for x in v})) for v in sets.values())

    # precert/final pairs: same serial + domains + validity, but different fingerprints
    def pairs(keyfn):
        g = collections.defaultdict(lambda: {"pre": set(), "fin": set()})
        for r in leaf:
            side = "pre" if r[2] == "PrecertLogEntry" else "fin"
            g[keyfn(r)][side].add(r[1])
        return sum(1 for v in g.values() if v["pre"] and v["fin"])
    serial_groups = collections.defaultdict(set)
    for r in leaf: serial_groups[r[4]].add((r[6], r[7], r[8]))
    serial_conflicts = sum(1 for v in serial_groups.values() if len(v) > 1)
    prof = {
        "rows": n, "unparseable": bad, "bytes": size, "avg_bytes_per_row": round(size / max(n, 1)),
        "estimated_rows_if_full_file_31831736095_bytes": round(31831736095 / (size / max(n, 1))),
        "field_present": dict(present),
        "field_present_but_null_or_empty": {k: v for k, v in empty.items() if v},
        "fingerprint_formats": {str(k): v for k, v in fp_formats.items()},
        "fingerprint_matches_hash_of_as_der": {"match": sha_ok, "mismatch": sha_bad, "error": sha_err, "mismatch_example_lines": sha_examples},
        "update_type": dict(update),
        "update_type_vs_extension": {str(k): v for k, v in poison_x.items()},
        "distinct_logs": len(source), "top_logs": source.most_common(12),
        "distinct_fingerprints": len(by_key),
        "duplicate_sets": len(sets), "duplicate_rows": sum(len(v) for v in sets.values()),
        "set_size_distribution": dict(set_sizes),
        "set_update_type_combinations": {str(k): v for k, v in set_types.items()},
        "sets_where_two_members_come_from_the_same_log": same_log,
        "top_log_pairs_in_duplicate_sets": [(list(k), v) for k, v in log_pairs.most_common(8)],
        "precert_final_pairs": {
            "serial_only": pairs(lambda r: r[4]),
            "serial_domains_validity": pairs(lambda r: (r[4], r[6], r[7], r[8])),
            "serial_domains_validity_aki": pairs(lambda r: (r[4], r[6], r[7], r[8], r[5])),
            "serials_with_conflicting_domains_or_validity": serial_conflicts,
            "distinct_serials": len(serial_groups),
        },
    }
    json.dump(prof, open(a.out, "w"), indent=2, default=str)
    print(json.dumps(prof, indent=2, default=str))

if __name__ == "__main__":
    main()
