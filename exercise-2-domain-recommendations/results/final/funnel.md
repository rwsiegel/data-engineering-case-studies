# Funnel: from credential rows to recommended domains

## Credential rows (clean.py)

| Stage | Entering | Discarded | Kept |
|---|---:|---:|---:|
| 1 parse | 131,319 | 0 | 131,319 |
| 2 normalize | 131,319 | 5,080 | 126,239 |
| 3a exact duplicate rows | 126,239 | 10,358 | 115,881 |
| 3b repeat of machine+fqdn+url | 115,881 | 43,354 | 72,527 |
| 3c collapse to machine+domain | 72,527 | 13,821 | 58,706 |

Repairs (not discards): hostnames written backwards were reversed before counting.

| Original | Repaired | Rows | Machines |
|---|---|---:|---:|
| com.kendohotels | kendohotels.com | 11 | 11 |
| online.samuraiwarriors | samuraiwarriors.online | 25 | 25 |

Result: 58,706 observations (machine and domain) over 560 machines.

## Domains (candidates.py, evidence.py, package.py)

| Stage | Entering | Removed | Kept |
|---|---:|---:|---:|
| 4 candidates (every domain on a seed machine) | 33,131 | 0 | 33,131 |
| 5a seed domain | 33,131 | 1 | 33,130 |
| 5b internal or non-public name (set aside, not discarded) | 33,130 | 4 | 33,126 |
| 5c widespread domain (seen on >= 35% of machines) | 33,126 | 9 | 33,117 |
| 6a third-party tenants (set aside: related, not owned) | 33,117 | 7 | 33,110 |
| 6b gate: seen on >= 10 machines | 33,110 | 32,672 | 438 |
| 7 cutoff: score >= 0.75 | 438 | 417 | 21 |

Recommended: 21 domains. Review leads: 2 (parkwayhotels.com, naganoresorts.com). Set aside as related, not owned: 7 third-party tenants.
Checks: all pass
