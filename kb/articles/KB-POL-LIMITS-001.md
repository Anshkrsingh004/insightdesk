# Plan limits policy

_CloudFlow help center · Policy · applies to all_

## Authoritative plan limits
| Plan | API req/min | Monthly runs | Seats | Support tier | Price (USD/mo) |
|------|-------------|--------------|-------|--------------|----------------|
| Free | 10 | 100 | 1 | community | 0 |
| Pro | 60 | 10,000 | 5 | standard | 49 |
| Business | 300 | 100,000 | 25 | priority | 199 |
| Enterprise | 1,000 | 1,000,000 | 100 | priority | 999 |

These values are the source of truth for the `plan_limits` table and the
`api_rate_limit_per_min` / `monthly_workflow_runs` registry rules. Support does not
raise limits outside the plan (see KB-API-RATE-001).
