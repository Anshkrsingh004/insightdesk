# API rate limits and CF-429 / HTTP 429 errors

_CloudFlow help center · API & integrations · applies to 3.x;4.x_

## Overview
CloudFlow enforces a **per-minute API rate limit** that depends on your plan. Exceeding
it returns **HTTP 429** (CloudFlow code **CF-429**).

## Per-plan limits
| Plan | API requests / minute | Monthly workflow runs |
|------|-----------------------|-----------------------|
| Free | 10 | 100 |
| Pro | 60 | 10,000 |
| Business | 300 | 100,000 |
| Enterprise | 1,000 | 1,000,000 |

These are the authoritative limits (see policy KB-POL-LIMITS-001).

## What to do about 429s — current guidance
1. **Add exponential backoff** with jitter and honour the `Retry-After` header.
2. **Batch** requests where possible instead of polling tightly.
3. If you are legitimately at capacity, **upgrade your plan** for a higher limit.

> Support does **not** permanently raise an account's rate limit outside of its plan.
> Any temporary increase recorded in an old ticket (e.g. TKT-2025-0590) was a one-off
> incident mitigation and is not a supported configuration.

## Related
- KB-POL-LIMITS-001 Plan limits policy
- KB-ACC-USAGE-001 Check your usage against plan limits
