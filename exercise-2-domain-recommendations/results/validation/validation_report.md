# Validation report

Checks run against the raw file with code that shares nothing with the pipeline.

| Check | Result | Detail |
|---|---|---|
| A1 every recommended domain and lead: machine count, machine list, logins per machine and example hosts match the raw file | PASS | [] |
| A2 every row of evidence_machines.csv exists in raw and the saved-login count agrees | PASS | 1068 rows |
| B1 the seed domain is not in the recommendations, review leads or related-not-owned list | PASS |  |
| B2 no reversed spelling of the seed (online.samuraiwarriors) survives as a candidate | PASS |  |
| C1 every recommended domain has at most 1.1 logins per machine (no domain is recommended on name alone) | PASS | [] |
| C2 a domain scoring on name clues alone (other two clues at zero) cannot reach the 0.75 cutoff | PASS | best name-only score 0.35 |
| D1 every raw row is accounted for: discards by stage plus kept = raw rows | PASS | 131319 rows |
| D2 combined discard log is non-empty and carries a reason for each line | PASS | 27 lines |
| D3 domain funnel: candidates = removed at each stage + remaining scored | PASS | 33131 = 32693 + 438 |
| D4 the 35%-of-machines filter removed exactly the domains the raw file puts at or above that share | PASS | 9 domains |
| E1 no recommended domain or lead is in the third-party tenant list | PASS | ['avature.net', 'icims.com', 'myworkdayjobs.com', 'okta.com', 'service-now.com', 'taleo.net', 'zendesk.com'] |
| E2 no recommended domain is a public-service domain removed at the 35% filter | PASS |  |
| F1 every recommended domain has a non-empty plain-language reason, example hosts and example URLs | PASS |  |

ALL PASS
