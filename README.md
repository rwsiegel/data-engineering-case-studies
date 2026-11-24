# Data-engineering case studies: duplicate certificates and domain recommendations

Two exercises originally set as take-home technical assessments by a security-intelligence company (name redacted).
Both are rebuilt here on **synthetic data** with the same structure as the originals, so everything runs and nothing confidential is published.

| | Exercise 1 | Exercise 2 |
|---|---|---|
| Question | Which certificates are recorded more than once across Certificate Transparency logs? | Which other domains does a client probably own, given stolen-credential logs and one known domain? |
| Approach | Streaming index in 256 buckets, one bucket in memory at a time, original records copied byte for byte | Evidence per infected machine, filters, a transparent four-clue score |
| Scale lesson | Peak memory stayed flat on a 31.8 GB input | No labels: explain and test stability instead of claiming accuracy |
| Checks | Independent recount, byte-for-byte verification | Independent recount, 13-check evidence audit, stability tests |
| Start here | [exercise-1-certificate-dedup](exercise-1-certificate-dedup/README.md) | [exercise-2-domain-recommendations](exercise-2-domain-recommendations/README.md) |

**For a quick read:** `executive_summary.pdf` in each exercise folder (one page each).
**To try the knobs:** the [Score Clue Explorer](https://YOUR-USERNAME.github.io/YOUR-REPO/) (see below).

## What this shows

- Treating the **unit of evidence** carefully (an infected machine, not a row) and refusing to rank on name similarity alone.
- **Auditability**: every stage logs what it removed and why, and kept + removed = entering at each step.
- **Validation with a second method** that shares no code with the pipeline.
- **Honest limits**: no ground truth, judgment-based weights, and stability tests that show which clues carry the result.
- **Memory-bounded engineering** for data larger than memory.

## Publishing the explorer

`docs/index.html` is a single self-contained page (the Score Clue Explorer). To host it free:

1. Push this repository to GitHub.
2. In the repository, open **Settings, Pages**. Under **Build and deployment**, choose **Deploy from a branch**, branch `main`, folder `/docs`, and save.
3. After a minute the page is live at `https://YOUR-USERNAME.github.io/YOUR-REPO/`. Replace the two placeholder links in the READMEs with that address.

## Layout

```
exercise-1-certificate-dedup/        code, synthetic data, results, visuals, decisions, one-page summary
exercise-2-domain-recommendations/   code, synthetic data, results, visuals, commentary, worked example, one-page summary
docs/                                the hosted explorer (GitHub Pages)
```

## Data note

All data is generated. Certificates are random bytes with generated names. Credentials data uses invented company names; a small number of well-known public
services appear as ordinary examples of consumer sites and no claim is made about any real organization or account.

## License

MIT, see `LICENSE`.
