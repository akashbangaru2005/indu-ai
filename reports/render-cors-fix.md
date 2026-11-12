# Production CORS configuration and verification

The source changes are tested locally. They have not been pushed or deployed by this task.

## Diagnosis

`backend/main.py` already reads `INDU_ALLOWED_ORIGINS` through `backend.deployment.allowed_origins()` at import time. Before this change, cloud mode defaulted to no external frontend origins and `render.yaml` left this setting for manual entry. If the setting omitted the Vercel origin, the HTTP origin guard returned 403 before CORSMiddleware could add `Access-Control-Allow-Origin`. An explicit empty setting also suppressed defaults. Frontend requests include `Content-Type: application/json`, including GET requests, so the browser uses an OPTIONS preflight.

The screenshot's failure was **not reproducible during this task's public checks**: before applying the changes, Render returned 200 and `Access-Control-Allow-Origin: https://indu-ai.vercel.app` for OPTIONS and GET on both `/` and `/health`. The deployed health response reported `deployment_mode: local`. These observations do not establish which environment settings or revision were active when the screenshot was taken. Full HTTP evidence is in [render-cors-live-before.json](render-cors-live-before.json).

## Changes

- Cloud mode defaults to the explicit origin `https://indu-ai.vercel.app` when the setting is missing or blank. Non-empty comma-separated settings override mode defaults; whitespace, trailing slashes and duplicates are removed. Wildcard origins are rejected.
- Local mode retains localhost and 127.0.0.1 on ports 5173 and 4173. The hosted frontend is not implicitly trusted to control the local desktop application.
- `render.yaml` explicitly sets the Vercel origin. Existing manual services still need their Render environment settings updated.
- CORSMiddleware allows all methods and headers for approved origins. `allow_credentials=False` remains appropriate for the current client: no cookie session or cross-origin credential fetch is used. The Gemini key stays server-side.
- TrustedHostMiddleware runs before CORS, so even preflight requests must pass backend host validation. The existing HTTP origin guard remains outermost among user middleware; allowed requests reach CORS, rejected origins remain blocked before routes execute. Route validation errors and handled HTTP exceptions retain CORS headers for approved origins. The normal server error handler is unchanged.
- HTTP CORS and WebSocket origin validation share the configured origin list. The health and Gemini Live routes are unchanged. No security middleware was disabled and no proxy-header trust was expanded.

FastAPI documents explicit origin allowlists and the handling of OPTIONS by CORSMiddleware in its [CORS guide](https://fastapi.tiangolo.com/tutorial/cors/).

## Actual test results

Tests ran on Windows, Python 3.13.5. Native Linux execution and deployment of this revision were not performed. Tests used temporary databases, disabled credential loading, and no real Gemini requests or microphone/audio hardware.

| Check | Result |
| --- | --- |
| Full backend regression suite | 80 tests passed, 0 failures/errors, 10.271 seconds |
| Cloud smoke check in the existing Render-only virtual environment | 11 checks passed |
| Backend import and actual Uvicorn startup | Passed with local hardware/GUI imports blocked |
| Vercel OPTIONS `/` and `/health` | 200; exact `Access-Control-Allow-Origin: https://indu-ai.vercel.app` |
| Requested methods/headers | All seven standard methods accepted; content-type and x-request-id accepted |
| Vercel GET `/` and `/health` | 200 JSON with the exact Vercel CORS header |
| Local development | OPTIONS/GET passed on both routes for all four localhost/127.0.0.1 development origins |
| Forbidden/lookalike/null origins | 403 without an allow-origin header |
| Untrusted Host on preflight | 400; TrustedHostMiddleware remains enforced |
| Handled 404, 422 and 409 errors | Correct statuses with Vercel CORS headers |
| Voice WebSocket | Actual local Uvicorn upgrade passed with production Host and Vercel Origin; five mocked PCM audio turns passed on one session |
| Source whitespace check | `git diff --check` passed |

Evidence: [test log](render-cors-tests.log), [cloud smoke result](render-cors-cloud-smoke.json). The test client emitted a Starlette httpx deprecation warning; it did not fail tests.

## Apply to Render

Set these values in the existing Render service's Environment settings, then deploy the changed source:

```text
INDU_DEPLOYMENT_MODE=cloud
INDU_ALLOWED_ORIGINS=https://indu-ai.vercel.app
```

Keep the existing exact `INDU_ALLOWED_HOSTS` configuration and server-side Gemini key. Environment settings are read when the backend process starts. Merely editing the example file or a Blueprint file does not update a manually configured running service.

After deployment, verify `/health` reports `deployment_mode: cloud`, then check preflight and GET again. For example in PowerShell:

```powershell
curl.exe -i -X OPTIONS https://indu-ai.onrender.com/ -H "Origin: https://indu-ai.vercel.app" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: content-type"
curl.exe -i https://indu-ai.onrender.com/health -H "Origin: https://indu-ai.vercel.app"
```

Both should return 200 with `Access-Control-Allow-Origin: https://indu-ai.vercel.app`. The public pre-change results already passed these CORS requests; they are not evidence that the new source has been deployed.

## Modified files

- `backend/deployment.py`
- `backend/main.py`
- `render.yaml`
- `.env.example`
- `README.md`
- `backend/tests/test_deployment.py`
- `backend/tests/test_api.py`
- `benchmarks/cloud_smoke.py`

Added evidence files: `reports/render-cors-fix.md`, `reports/render-cors-tests.log`, `reports/render-cors-cloud-smoke.json`, `reports/render-cors-live-before.json`.
