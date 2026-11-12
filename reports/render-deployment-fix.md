# Render dependency and cloud-mode fix

13 November 2026. Repository configuration and code were changed directly. No Render service was deployed or dashboard setting changed from this workspace. The supplied Gemini key was not read from the OS vault or used for these tests.

## Cause and fix

The old Render build installed `backend/requirements.txt`, which includes the local Windows audio/desktop stack. `pygame` is used only for local speaker playback, not by the Gemini Live browser bridge. The supplied log shows its source-wheel preparation failing; it does not identify the underlying SDL/compiler/Python compatibility detail. The fix removes that unnecessary build from the cloud dependency graph, without removing pygame from Windows development.

`backend/requirements-render.txt` contains only FastAPI, base Uvicorn, explicit WebSocket support, Google GenAI, HTTPX, timezone data and optional network Edge TTS. Edge TTS generates MP3 files for browser playback and does not require pygame. Uvicorn's base install plus `websockets` avoids unnecessary development/reload and native-server extras.

| Dependency | Render treatment | Reason |
| --- | --- | --- |
| pygame | Excluded | Local speaker playback only. |
| sounddevice | Excluded | Local PortAudio microphone/speaker access. |
| NumPy / Faster-Whisper | Excluded | Local microphone transcription/resampling; browser PCM goes directly to Gemini. |
| Playwright | Excluded | Legacy local browser controller, outside the API startup graph. |
| keyring and native vault dependencies | Excluded | Cloud reads `GEMINI_API_KEY` from its environment. |
| pyautogui | Not present in the existing active project; not added | No cloud desktop GUI control is enabled. |
| pyttsx3 | Not a cloud dependency | Used by the standalone voice-listing utility, not API startup. |
| requests | Not listed directly | Active live-information code uses HTTPX; Google SDK/auth still installs requests transitively. |

The local `backend/requirements.txt` is byte-for-byte unchanged. Its SHA-256 before and after is `38f1237a241df49cf6a32ac5faa94c8b59888f0625809b4d13ddd619959332c5`.

## Import audit and runtime behavior

- `main.py` imports the Gemini brain/persona, command router, byte-stream voice bridge and network TTS class. Package initializers do not import the legacy desktop demos.
- Pygame was already imported lazily inside `InduTextToSpeech._speak`. Cloud mode now returns before generating playback audio, importing pygame, initializing its mixer or starting a playback thread. Network MP3 generation remains separate.
- `voice/stt.py` imports NumPy and optional local audio/Whisper modules, but the API imports it only inside `/api/listen`. Cloud mode rejects that route before importing STT or touching a microphone.
- Windows registry imports remain inside desktop helper functions. Cloud guards run before those functions inspect or launch Windows targets, including direct helper calls.
- Router website/application launches and WhatsApp browser opening are disabled on the cloud server. Contacts, reminder storage and read-only live information remain available.
- OS credential storage was already lazy. Cloud startup now skips vault loading entirely; browser key replacement/disconnection is rejected before any Gemini validation or vault access. The UI displays server-managed credentials while retaining browser microphone/speaker selection.
- `/ws/voice`, PCM input/output, interruption/stop handling and the multi-turn receive loop remain enabled. No cloud guard disables Gemini Live.
- `/health` reports the deployment mode and distinguishes browser audio streaming from disabled server hardware. Desktop shutdown stays disabled even if `INDU_DESKTOP=1` is accidentally inherited.
- Legacy `gemini_live.py`, `list_voices.py`, `voice/stt.py` and `tools/browser.py` remain local-only utilities outside cloud API startup; their working Windows dependencies were preserved.

The cloud smoke check blocks imports of pygame, sounddevice, pyautogui, keyring, Faster-Whisper, Playwright, winreg and pyttsx3 and verifies none are attempted through API startup or the exercised cloud operations. A fresh environment also confirms NumPy and the local packages are actually absent.

## Render settings

Leave Root Directory blank so commands run at the repository root:

```text
Build: pip install -r backend/requirements-render.txt
Start: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
Health: /health
```

`backend.main:app` is required; the original requested command omitted the FastAPI attribute. This follows Render's [FastAPI start format](https://render.com/docs/deploy-fastapi).

Set `INDU_DEPLOYMENT_MODE=cloud`, `GEMINI_API_KEY` as a dashboard secret, `INDU_ALLOWED_ORIGINS` to the exact HTTPS frontend origin(s), and `INDU_DATA_DIR=/tmp/indu`. Configure the frontend's `VITE_API_URL` with the HTTPS backend URL. Existing browser audio then uses WSS, as required by Render's [WebSocket guidance](https://render.com/docs/websocket).

`.python-version` selects the 3.13 line with its latest patch. Render supports omitting the patch in that file, while a `PYTHON_VERSION` environment override must be fully qualified and takes precedence ([Python version guide](https://render.com/docs/python-version)).

The service automatically accepts `RENDER_EXTERNAL_HOSTNAME`; custom API domains use `INDU_ALLOWED_HOSTS`. Frontend origins and API hostnames are distinct settings. The platform hostname is documented in Render's [default environment variables](https://render.com/docs/environment-variables).

`render.yaml` provides these settings for Blueprint-managed services. Existing manually configured services still need their dashboard commands/environment updated before redeploying. No credentials are embedded in the YAML.

## Tests actually run

| Check | Result | Evidence |
| --- | --- | --- |
| Fresh environment: install only Render requirements | Passed on Windows CPython 3.13.5 | `render-requirements-install.log`, `render-installed-packages.json` |
| Fresh environment dependency consistency | Passed: no broken requirements | `render-pip-check.log` |
| Absence of pygame, sounddevice, NumPy, Whisper, keyring, pyautogui and Playwright | Confirmed absent in the fresh environment | Dependency list and `render-validation.json` |
| Linux CPython 3.13 x86-64 wheel resolution/download | Passed for all resolved wheels; no source builds | `render-linux-wheels.log` |
| Cloud import/startup/health/host/CORS/hardware policy | Passed | `render-cloud-smoke.json` |
| Five cloud Gemini Live turns, same provider connection, browser PCM both directions, explicit stop | Passed with a mocked SDK provider | `render-cloud-smoke.json` |
| Real Uvicorn HTTP server and real WebSocket upgrade | Passed with the key deliberately absent; clear error follows upgrade | `render-cloud-smoke.json` |
| Existing/local Windows backend regressions plus deployment tests | 73 tests passed | `render-local-regression-tests.log` |
| Voice unit tests inside the minimal Render environment | 8 tests passed | `render-minimal-voice-tests.log` |
| Frontend tests | 18 tests passed | `render-frontend-tests.log` |
| Headless Edge: local interface plus cloud credentials display | 22 checks passed | `browser-smoke.json` |
| Production frontend build | Passed | `render-frontend-build.log` |
| Render Blueprint / Ubuntu workflow YAML parse and required settings | Passed | `render-validation.json` |

The result manifest is [render-validation.json](render-validation.json). The frontend build still has the existing lazy Three.js chunk-size advisory, and TestClient emits an upstream HTTPX adapter deprecation; neither is a failed check.

## Validation limits and remaining deployment work

- **Native Linux installation/execution has not been run in this workspace.** WSL is not installed and Docker/Podman are unavailable. Linux wheel availability is verified, but it is not represented as a native Linux import/startup result. Render's native runtime uses Debian bookworm ([runtime documentation](https://render.com/docs/native-runtimes)); the resolved native wheels target compatible manylinux tags.
- `.github/workflows/render-cloud.yml` performs the clean cloud install, `pip check`, cloud smoke check and voice tests on Ubuntu/Python 3.13 after a push, PR or manual dispatch. The workflow was added and parsed, but no GitHub Actions run is claimed.
- No Render deployment or remote Gemini authentication check was performed. Multi-turn provider messages are mocked; this isolates the regression from keys, quotas and hardware.
- Windows launch/audio paths are covered by existing regression tests with actions/devices mocked. This run did not physically record a microphone, play speaker audio or launch Office.
- `/tmp/indu` is ephemeral. Persistent cloud contacts/reminders require a configured Render disk and matching data-directory setting. Current shared SQLite/in-memory state is intended for one worker/instance and does not add account isolation/authentication.

## All source/configuration files added or modified

| File | Change |
| --- | --- |
| `backend/requirements-render.txt` | New cloud dependency list. |
| `backend/deployment.py` | New explicit mode, origin and host policy. |
| `backend/main.py` | Cloud guards, environment-only credentials, Render hosts, capability health data; voice remains enabled. |
| `backend/credentials.py` | Refuse OS credential access in cloud mode. |
| `backend/tools/router.py` | Reject server-side desktop/website launches in cloud mode. |
| `backend/tools/desktop.py` | Guard direct Windows helper calls. |
| `backend/tools/whatsapp.py` | Disable cloud-side browser linking/draft opening with truthful status. |
| `backend/tools/contacts.py` | Avoid migrating a local desktop database into a cloud instance. |
| `backend/voice/tts.py` | Disable only local speaker playback/thread creation in cloud mode. |
| `frontend/src/components/SettingsPanel.jsx` | Show server-managed cloud credentials while retaining browser device controls. |
| `render.yaml` | New Render service build/start/health/environment configuration. |
| `.python-version` | Select Python 3.13 for Render. |
| `.env.example` | Document deployment mode and optional custom hosts. |
| `README.md` | Complete Render setup and validation instructions. |
| `.gitignore` | Ignore the isolated verification environment and downloaded wheels. |
| `backend/tests/test_deployment.py` | Mode/configuration and isolated cloud regression tests. |
| `benchmarks/cloud_smoke.py` | Minimal-dependency cloud/HTTP/WebSocket integration checks. |
| `benchmarks/browser_smoke.py` | Explicit local-mode regression environment and cloud credentials UI check. |
| `.github/workflows/render-cloud.yml` | New Linux install/startup/voice CI workflow. |
| `reports/render-deployment-fix.md` | This import audit, setup instructions, file list and test report. |

Generated evidence includes `reports/render-validation.json`, `render-cloud-smoke.json`, `render-installed-packages.json`, the `render-*.log` files above, and refreshed browser JSON/screenshots. No dependency changes were made to `backend/requirements.txt` or `backend/requirements-dev.txt`; no Windows installer rebuild was required.
