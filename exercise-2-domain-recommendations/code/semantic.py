"""Name meaning in a word-vector space (GloVe 50d). Splits domain names into words, averages their vectors,
and measures distance to the seed's name. Usage: python semantic.py VECTORS.gz OUT_DIR"""
import sys, gzip, math, csv, re, collections
import numpy as np

def load(path, limit=400000):
    words, vecs = [], []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        next(f)                                    # header line: count and dimension
        for i, line in enumerate(f):
            if i >= limit: break
            p = line.rstrip().split(" "); words.append(p[0]); vecs.append(np.asarray(p[1:], dtype=np.float32))
    V = np.vstack(vecs); V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    return words, V

words, V = load(sys.argv[1]); idx = {w: i for i, w in enumerate(words)}      # file is ordered by frequency, so index = rank
ok = {w for w in words if w.isalpha() and w.isascii() and len(w) >= 3}
def segment(s):
    """Lowest-cost split of s into known words; cost grows with rarity and with the number of pieces."""
    n = len(s); best = [(math.inf, None)] * (n + 1); best[0] = (0, None)
    for i in range(1, n + 1):
        for j in range(max(0, i - 20), i):
            piece = s[j:i]
            if piece in ok: c = best[j][0] + math.log(idx[piece] + 10) + 4
            elif i - j <= 12 and piece.isalpha(): c = best[j][0] + 30 + 3 * (i - j)      # unknown chunk, expensive
            else: continue
            if c < best[i][0]: best[i] = (c, j)
    out, i = [], n
    while i > 0: j = best[i][1]; out.append(s[j:i]); i = j
    return out[::-1]

def tokens(domain):
    name = domain.split(".")[0]
    return [t for part in re.split(r"[-_]", name) for t in (segment(part) if part.isalpha() else [part]) if t]

def vec(tok):
    vs = [V[idx[t]] for t in tok if t in idx]
    if not vs: return None
    m = np.mean(vs, axis=0); return m / (np.linalg.norm(m) + 1e-9)

def find_generic(cand_csv, share=0.03):
    """Words that appear in at least `share` of all candidate domain names carry no brand meaning (direct, group, capital...)."""
    cnt = collections.Counter(); n = 0
    for r in csv.DictReader(open(cand_csv)):
        n += 1
        for t in set(tokens(r["domain"])): cnt[t] += 1
    return {t: c for t, c in cnt.items() if c >= share * n}, n

def brand(tok, generic):
    """Strip generic words; if every word is generic, keep them all (nothing else to compare)."""
    b = [t for t in tok if t not in generic]
    return b if b else tok

if __name__ == "__main__":
    out_dir = sys.argv[2]
    generic, n_dom = find_generic(out_dir + "/candidates.csv")
    print(f"generic words (in >= 3% of {n_dom:,} domains): {len(generic)}:", sorted(generic, key=lambda t: -generic[t]))
    with open(out_dir + "/generic_words.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["word", "domains_containing_it", "share_of_domains"])
        for t, c in sorted(generic.items(), key=lambda kv: -kv[1]): w.writerow([t, c, round(c / n_dom, 4)])
    seed = brand(tokens("samuraiwarriors.online"), generic); sv = vec(seed); print("seed brand words:", seed)
    probe = ["samuraiwarriorscircle.com","samuraiwarriorscareers.com","kendohotels.com","ginza-hotels.com","kendocareers.com","samurai.com","shogunworks-cad.com","edoinns.com","pillartomato.net","uniongoosemarketplace.co.uk","compasscounter-cyber.store","google.com","facebook.com","spotify.com"]
    print(f"\n{'domain':26s} {'all words':30s} {'brand words':22s} before -> after")
    for d in probe:
        t = tokens(d); b = brand(t, generic); old, new = vec(t), vec(b)
        print(f"{d:26s} {'+'.join(t):30s} {'+'.join(b):22s} {float(old @ sv):.2f} -> {float(new @ sv):.2f}")
    rows = []
    for r in csv.DictReader(open(out_dir + "/candidates.csv")):
        t = tokens(r["domain"]); b = brand(t, generic); v = vec(b)
        rows.append((r["domain"], "+".join(t), "+".join(b), round(float(v @ sv), 4) if v is not None else "", int(r["machines"])))
    with open(out_dir + "/name_semantics.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["domain", "name_words", "brand_words", "similarity_to_seed_brand", "machines"]); w.writerows(rows)
    sel = sorted([x for x in rows if x[3] != "" and "samuraiwarriors" not in x[0] and x[4] >= 10], key=lambda x: -x[3])
    print(f"\nTop 15 by brand-word similarity among {len(sel)} domains on >= 10 machines (no 'samuraiwarriors' in the name):")
    for d, t, b, sc, m in sel[:15]: print(f"  {sc:.2f}  {d:30s} {b:24s} machines={m}")
