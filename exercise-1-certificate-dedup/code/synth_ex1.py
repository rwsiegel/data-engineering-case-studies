#!/usr/bin/env python3
"""Generate a synthetic Certificate Transparency record file shaped like the real input:
same record layout, same duplicate-set size mix, same precertificate/final split, same log mix and log pairs, same
precert/final pairing rate. Certificates are random bytes (not real certificates) and names are generated.
Usage: python synth_ex1.py OUT.jsonlines [--records 50000] [--seed 7]"""
import argparse, base64, hashlib, json, math, random, os
ap = argparse.ArgumentParser(); ap.add_argument("out"); ap.add_argument("--records", type=int, default=50000); ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--logs", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "log_urls.json"))
a = ap.parse_args(); rnd = random.Random(a.seed)
URLS = json.load(open(a.logs))
# ---- shape taken from the audit of the real run (counts per 4,000,000 records)
REAL = 4_000_000
SETS_P = {2: 386807, 3: 142553, 4: 22404, 5: 1933, 6: 195, 7: 28, 8: 2}          # all-precert duplicate sets by size
SETS_X = {2: 304625, 3: 615, 4: 29, 5: 8, 6: 5, 7: 1}                               # all-final duplicate sets by size
SINGLE_P, SINGLE_X = 815773, 1271003                                                 # singleton fingerprints
PAIRS, P_GROUPS, X_GROUPS = 807944, 1369695, 1576286
ROWS_BY_LOG = {"Google 'Argon2019' log": 1108619, "Let's Encrypt 'Oak2019' log": 976071, "Google 'Pilot' log": 455656, "Google 'Rocketeer' log": 453250,
 "Google 'Icarus' log": 413453, "Cloudflare 'Nimbus2019' Log": 164250, "Sectigo 'Mammoth' CT log": 98016, "Google 'Skydiver' log": 78533,
 "DigiCert Yeti2019 Log": 74202, "Google 'Testtube' log": 55049, "Google 'Argon2020' log": 39326, "Cloudflare 'Nimbus2020' Log": 27013,
 "Sectigo 'Sabre' CT log": 19330, "DigiCert Log Server 2": 12296, "Google 'Xenon2020' log": 4713, "Google 'Submariner' log": 4040,
 "DigiCert Yeti2020 Log": 3895, "DigiCert Log Server": 3168, "Cloudflare 'Nimbus2021' Log": 2853, "Google 'Argon2021' log": 2010,
 "DigiCert Nessie2020 Log": 1100, "Google 'Xenon2021' log": 991, "Google 'Xenon2019' log": 699, "DigiCert Yeti2021 Log": 531,
 "Let's Encrypt 'Oak2020' log": 241, "Let's Encrypt 'Oak2021' log": 229}
DUP_BY_LOG = {"Google 'Argon2019' log": 500629, "Let's Encrypt 'Oak2019' log": 436400, "Google 'Icarus' log": 293887, "Google 'Rocketeer' log": 188217,
 "Google 'Pilot' log": 181027, "Cloudflare 'Nimbus2019' Log": 96417, "Sectigo 'Mammoth' CT log": 66287, "Google 'Skydiver' log": 61113,
 "DigiCert Yeti2019 Log": 34660, "Cloudflare 'Nimbus2020' Log": 14274, "Sectigo 'Sabre' CT log": 13176, "Google 'Argon2020' log": 7697,
 "DigiCert Log Server 2": 4216, "Google 'Xenon2020' log": 3817, "DigiCert Yeti2020 Log": 2522, "Google 'Submariner' log": 1732,
 "DigiCert Log Server": 1667, "Cloudflare 'Nimbus2021' Log": 1563, "Google 'Argon2021' log": 1169, "Google 'Xenon2021' log": 822,
 "DigiCert Nessie2020 Log": 750, "Google 'Xenon2019' log": 571, "DigiCert Yeti2021 Log": 307, "DigiCert Nessie2021 Log": 96}
TOP_PAIRS = [(("Google 'Argon2019' log", "Let's Encrypt 'Oak2019' log"), 239370), (("Google 'Pilot' log", "Google 'Rocketeer' log"), 128955),
 (("Google 'Argon2019' log", "Google 'Icarus' log"), 106520), (("Google 'Icarus' log", "Let's Encrypt 'Oak2019' log"), 61199),
 (("Cloudflare 'Nimbus2019' Log", "Google 'Argon2019' log"), 32110), (("Cloudflare 'Nimbus2019' Log", "Let's Encrypt 'Oak2019' log"), 19378),
 (("Let's Encrypt 'Oak2019' log", "Sectigo 'Mammoth' CT log"), 14004), (("Google 'Rocketeer' log", "Google 'Skydiver' log"), 11332),
 (("Google 'Pilot' log", "Google 'Skydiver' log"), 9061), (("DigiCert Yeti2019 Log", "Let's Encrypt 'Oak2019' log"), 8793)]
OTHER_PAIR_SHARE = 1 - sum(w for _, w in TOP_PAIRS) / 691432
URLS.setdefault('DigiCert Nessie2021 Log', 'nessie2021.ct.digicert.com/log/'); URLS.setdefault('DigiCert Nessie2019 Log', 'nessie2019.ct.digicert.com/log/')
scale = a.records / REAL
def rr(x): f = math.floor(x); return f + (1 if rnd.random() < x - f else 0)             # stochastic rounding keeps the mix without bias
def wchoice(weights, k=1, exclude=()):
    items = [(n, w) for n, w in weights.items() if n not in exclude]; out = []
    for _ in range(k):
        t = rnd.random() * sum(w for _, w in items); c = 0
        for i, (n, w) in enumerate(items):
            c += w
            if t <= c: out.append(n); items.pop(i); break
    return out
def log_group(size, mixed_same=False):
    if size == 2:
        if rnd.random() > OTHER_PAIR_SHARE:
            t = rnd.random() * sum(w for _, w in TOP_PAIRS); c = 0
            for p, w in TOP_PAIRS:
                c += w
                if t <= c: return list(p)
        return wchoice(DUP_BY_LOG, 2)
    return wchoice(DUP_BY_LOG, size)
singles_log = {k: max(1, ROWS_BY_LOG[k] - DUP_BY_LOG.get(k, 0)) for k in ROWS_BY_LOG}
WORDS = [w for w in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool_words.txt")).read().split() if len(w) >= 4]
SUFFIX = ["group", "works", "supply", "digital", "labs", "online", "shop", "media", "partners", "systems", "studio", "health", "tech", "trust"]
TLDS = ["com"] * 8 + ["net", "org", "io", "de", "co.uk", "fr", "nl", "info", "app", "store"]
def domain():
    return rnd.choice(WORDS) + rnd.choice(WORDS) + ("" if rnd.random() < .6 else rnd.choice(SUFFIX)) + "." + rnd.choice(TLDS)
CA = [{"as_der": base64.b64encode(hashlib.sha256(b"synthetic-ca-%d" % i).digest() * 14).decode(), "extensions": {"basicConstraints": "CA:TRUE", "keyUsage": "Digital Signature, Key Cert Sign, C R L Sign"},
       "subject": {"C": "ZZ", "CN": n, "L": None, "O": "Synthetic Test Authority", "OU": None, "ST": None, "aggregated": f"/C=ZZ/CN={n}/O=Synthetic Test Authority"},
       "not_before": 1458232846, "not_after": 1615999246, "serial_number": "%X" % (1000 + i)} for i, n in enumerate(["Synthetic Intermediate CA 1", "Synthetic Root CA"])]
for c in CA: c["fingerprint"] = ":".join("%02X" % b for b in hashlib.sha1(base64.b64decode(c["as_der"])).digest())
def make_cert(kind, serial, dom, nb, na):
    der = (hashlib.sha256(f"{kind}|{serial}|{dom}".encode()).digest() * 9)[:280]
    b64 = base64.b64encode(der).decode()
    ext = {"authorityKeyIdentifier": "keyid:00:11:22:33", "basicConstraints": "CA:FALSE", "keyUsage": "Digital Signature, Key Encipherment",
           "subjectAltName": f"DNS:{dom}, DNS:www.{dom}"}
    if kind == "pre": ext["ctlPoisonByte"] = True
    return {"all_domains": [dom, "www." + dom], "as_der": b64, "extensions": ext,
            "fingerprint": ":".join("%02X" % b for b in hashlib.sha1(der).digest()), "not_after": na, "not_before": nb, "serial_number": serial,
            "subject": {"C": None, "CN": dom, "L": None, "O": None, "OU": None, "ST": None, "aggregated": "/CN=" + dom}}
# ---- certificate groups: (kind, size) with kind in pre/final
groups = []
for size, n in SETS_P.items(): groups += [("pre", size)] * rr(n * scale)
for size, n in SETS_X.items(): groups += [("fin", size)] * rr(n * scale)
for (kind, size) in [("pre", s) for s in SETS_P] + [("fin", s) for s in SETS_X]:     # keep every size present at small scale
    if (kind, size) not in groups: groups.append((kind, size))
groups += [("pre", 1)] * rr(SINGLE_P * scale) + [("fin", 1)] * rr(SINGLE_X * scale)
pre = [g for g in groups if g[0] == "pre"]; fin = [g for g in groups if g[0] == "fin"]
rnd.shuffle(pre); rnd.shuffle(fin)
n_pairs = min(len(pre), len(fin), rr(PAIRS * scale))
records = []; cert_i = 0
def emit(kind, serial, dom, nb, na, size, forced_same_log=False):
    global cert_i
    leaf = make_cert(kind, serial, dom, nb, na)
    logs = log_group(size) if size > 1 else wchoice(singles_log, 1)
    for lg in logs:
        idx = rnd.randrange(10_000, 900_000_000); seen = 1565500000 + rnd.random() * 400000
        records.append({"data": {"cert_index": idx, "cert_link": f"http://{URLS[lg]}ct/v1/get-entries?start={idx}&end={idx}", "chain": CA, "leaf_cert": leaf,
                                 "seen": seen, "source": {"name": lg, "url": URLS[lg]}, "update_type": "PrecertLogEntry" if kind == "pre" else "X509LogEntry"}, "message_type": "certificate_update"})
    return leaf
def attrs():
    nb = rnd.randrange(1_560_000_000, 1_566_000_000); return "%X" % rnd.getrandbits(120), domain(), nb, nb + 7_776_000
# pairs: a precert group and a final group share serial, domains and validity
for i in range(len(pre)):
    serial, dom, nb, na = attrs()
    emit("pre", serial, dom, nb, na, pre[i][1])
    if i < n_pairs: emit("fin", serial, dom, nb, na, fin[i][1])
for g in fin[n_pairs:]:
    serial, dom, nb, na = attrs(); emit("fin", serial, dom, nb, na, g[1])
# one set whose two copies come from the same log, as in the real file
serial, dom, nb, na = attrs(); leaf = make_cert("fin", serial, dom, nb, na); lg = "Google 'Argon2019' log"
for _ in range(2):
    idx = rnd.randrange(10_000, 900_000_000)
    records.append({"data": {"cert_index": idx, "cert_link": f"http://{URLS[lg]}ct/v1/get-entries?start={idx}&end={idx}", "chain": CA, "leaf_cert": leaf, "seen": 1565500000 + rnd.random() * 400000,
                             "source": {"name": lg, "url": URLS[lg]}, "update_type": "X509LogEntry"}, "message_type": "certificate_update"})
rnd.shuffle(records)
with open(a.out, "w", encoding="utf-8", newline="\n") as f:
    for r in records: f.write(json.dumps(r) + "\n")
print(len(records), "records written to", a.out)
