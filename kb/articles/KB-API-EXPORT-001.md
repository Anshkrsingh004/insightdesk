# Export runs via the API

_CloudFlow help center · API & integrations · applies to 3.x;4.x_

## Overview
You can export workflow runs programmatically.

## CloudFlow 4.x — current endpoint
`GET /api/v4/workflows/{id}/runs/export?format=csv&from=YYYY-MM-DD&to=YYYY-MM-DD`
Authenticated with a Bearer API token (see KB-API-TOKENS-001).

## CloudFlow 3.x — legacy endpoint (being deprecated)
`GET /api/v3/export/runs?workflow={id}` still works today but is **deprecated** and will
be removed — see release note **RN-2026-09-01**. Migrate to the v4 endpoint above.

## Related
- RN-2026-09-01 Deprecation of the legacy v3 export API
- KB-HOW-EXPORT-001 Export your workflow run history (UI)
