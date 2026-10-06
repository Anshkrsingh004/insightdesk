# CloudFlow error-code reference

_CloudFlow help center · Troubleshooting · applies to all_

## Error codes
| Code | Category | Meaning | First action |
|------|----------|---------|--------------|
| CF-401 | Auth | API token invalid/expired | Rotate token (KB-SEC-TOKENS-001) |
| CF-403 | Auth | Insufficient permission | Check the connector's scopes |
| CF-422 | Validation | Step config invalid | Fix the highlighted field |
| CF-429 | Limits | Rate limit exceeded | Backoff / upgrade (KB-API-RATE-001) |
| CF-500 | Server | Internal error | Retry; if persistent, contact support |
| CF-503 | Connector | Dependency unavailable | Re-authorise connector (KB-TRB-503-001) |
| CF-410 | Deprecation | Endpoint removed | Migrate (see release notes) |

Always cite the specific code article for the fix rather than guessing.
