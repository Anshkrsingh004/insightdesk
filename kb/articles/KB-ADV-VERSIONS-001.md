# What changed between CloudFlow 3.x and 4.x

_CloudFlow help center · Advanced features · applies to 3.x;4.x_

## Key differences
| Area | CloudFlow 3.x | CloudFlow 4.x |
|------|---------------|---------------|
| Run history export | Activity → Download runs (90 days) | Run History → Export (full) |
| Export API | `/api/v3/export/runs` (deprecated) | `/api/v4/.../runs/export` |
| Salesforce CF-503 fix | Edit API version in step | Re-authorise connector |
| Connectors UI | Integrations tab | Settings → Connectors |
| Conditional branching | Basic | Advanced (nested, sub-workflows) |

## Upgrading
Most 3.x workflows import into 4.x automatically. Review any step that hard-codes an API
version, as 4.x manages versions for you.
