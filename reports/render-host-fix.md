# Render production hostname fix

13 November 2026. The source/configuration change is tested locally. It has not been pushed or deployed from this workspace, and the live deployment is not claimed to be fixed.

## Observed failure and cause

Read-only HTTPS requests to `https://indu-ai.onrender.com/` and `/health` both returned HTTP 400 with `Invalid host header`. The pre-deployment evidence is in [render-host-live-before.json](render-host-live-before.json).

`backend/main.py` installs Starlette `TrustedHostMiddleware` using `backend.deployment.allowed_hosts()`. Before this fix, the explicit defaults contained only loopback/development hosts. A production hostname depended on `INDU_ALLOWED_HOSTS` or Render metadata that was used only when cloud mode was set. Therefore a deployment with the older/local allowlist rejects the public Host header before either endpoint executes. The live response does not reveal which exact environment setting or deployed revision was missing.

## Small source/configuration change

- The exact hostname `indu-ai.onrender.com` is now in the default allowlist alongside `localhost`, `127.0.0.1` and the existing test host.
- Additional explicit names still come from `INDU_ALLOWED_HOSTS`. Render's `RENDER_EXTERNAL_HOSTNAME` is accepted independently of the deployment-mode flag.
- Wildcard host configurations are rejected in cloud mode or a detected Render environment. The middleware remains enabled.
- `render.yaml` explicitly sets `INDU_ALLOWED_HOSTS=indu-ai.onrender.com,localhost,127.0.0.1`; `.env.example` and README document hostname-only syntax.
- CORS configuration is unchanged by this host fix. Allowed frontend origins do not authorize backend Host headers.

The checked installed Starlette middleware validates `scope['headers']['host']`, ignoring the port. Uvicorn's proxy middleware handles forwarded scheme/client-address headers and does not rewrite the Host header using `X-Forwarded-Host`. No proxy-header workaround, arbitrary host rewriting, middleware removal or blanket forwarded-IP trust was added.

The existing `/health` endpoint remains unchanged: successful HTTP 200 JSON includes component/configuration information. With no Gemini test key configured it truthfully reports degraded configuration while confirming the API is running.

## Tests actually run

- Backend import and full local regression suite: **76 passed** ([render-host-tests.log](render-host-tests.log)).
- Root and health returned **200 JSON** for `indu-ai.onrender.com`, `indu-ai.onrender.com:443`, `localhost` and `127.0.0.1`.
- Root and health rejected unknown and lookalike hosts with **400**. An untrusted Host plus a trusted-looking `X-Forwarded-Host` still returned 400; a trusted Host remained valid regardless of that forwarded header.
- The exact production domain is accepted without cloud-mode/platform metadata; other Render hostnames and explicit custom environment hosts remain supported. Production wildcard configurations fail clearly.
- In the clean environment containing only Render dependencies, a real Uvicorn process served root/health requests using the production Host header. A real WebSocket connection using that same Host completed its upgrade; the absent key produced the expected configuration error afterward.
- Five browser PCM input/provider PCM output turns ran through the cloud Gemini Live bridge on one mocked provider session using the production Host header, followed by explicit-stop cleanup. No real Gemini key or provider request was used.

Cloud/import/HTTP/WebSocket evidence is [render-host-cloud-smoke.json](render-host-cloud-smoke.json); the summarized result is [render-host-validation.json](render-host-validation.json). Execution was on Windows CPython 3.13.5. Native Linux/Render execution remains pending; the Linux CI workflow from the dependency fix is available but has not been run here.

## Files changed for this host fix

| File | Change |
| --- | --- |
| `backend/deployment.py` | Exact production hostname, unconditional Render metadata support, production wildcard rejection. |
| `render.yaml` | Explicit production/local host environment configuration. |
| `.env.example` | Hostname-only environment example. |
| `README.md` | Host/CORS distinction, Render setting and post-deployment checks. |
| `backend/tests/test_deployment.py` | Default production host, Render metadata without mode, and wildcard regression tests. |
| `benchmarks/cloud_smoke.py` | Root/health/proxy-header tests and production-host WebSocket checks. |
| `reports/render-host-fix.md` | This report. |

Generated evidence additionally includes `reports/render-host-live-before.json`, `render-host-cloud-smoke.json`, `render-host-tests.log` and `render-host-validation.json`. `backend/main.py` was inspected; its existing middleware/health/WebSocket wiring required no additional changes for this targeted host fix. The preceding dependency/cloud-mode changes remain documented separately in [render-deployment-fix.md](render-deployment-fix.md).

## Apply and verify

Push the current project changes and deploy that revision on Render. Set these values on an existing manually configured service:

```text
INDU_DEPLOYMENT_MODE=cloud
INDU_ALLOWED_HOSTS=indu-ai.onrender.com,localhost,127.0.0.1
```

Keep the service start command `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` and health-check path `/health`. Keep `INDU_ALLOWED_ORIGINS` separately configured for the frontend's HTTPS origin(s).

After the deployment succeeds, request `https://indu-ai.onrender.com/` and `https://indu-ai.onrender.com/health` and require 200 JSON from both. Until that revision is pushed, deployed and checked, only the local source fix is verified.
