# Backend mismatch and Gemini-only configuration

12 November 2026. The process answering on `localhost:8000` reported version **0.6.1**. Its OpenAPI schema did not contain `/api/contacts`, `/api/whatsapp/status`, or `/api/whatsapp/messages`. This reproduces the screenshot's 404s: the process still had the earlier application loaded.

The current source is **0.7.1** and includes those routes. Root metadata now advertises a versioned API contract and feature list. The frontend verifies them before requesting contacts/WhatsApp data or activating voice. With an older backend it displays a restart instruction and avoids requests to absent routes.

Following the user's clarification, text chat now uses Gemini through the Google GenAI SDK; live voice continues to use Gemini Live. There is no active Ollama client, model-list request, daemon requirement or Ollama interface card. Gemini text defaults to configurable `GEMINI_TEXT_MODEL=gemini-3.8-flash`. Both paths share the persona instructions and keep API credentials on the local backend.

The text integration follows Google's [generate-content API](https://ai.google.dev/api/generate-content) and [Python SDK](https://googleapis.github.io/python-genai/). Its contents/configuration payloads were validated against the installed SDK. Authenticated response generation was not tested because the agent environment has no Gemini key; the user's separate backend terminal retains its own environment.

The 3D scene now uses the installed Three.js `Timer` API, including visibility handling and disposal, instead of deprecated `Clock`.

Validation: **52 backend tests, 17 frontend tests, nine browser checks, production build and `pip check` passed.** The browser regression explicitly simulates backend 0.6.1, verifies the restart banner, verifies that missing routes are not requested, renders the WebGL scene, and checks that no `THREE.Clock` warning appears. The current browser checks use fake audio and an isolated database and do not make real Gemini or WhatsApp transmissions.

To replace the old running process without losing its shell's Gemini key, press Ctrl+C in the **backend terminal**, then run from the project root:

```powershell
.\backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

Refresh the frontend with Ctrl+Shift+R. No reinstall or Ollama setup is needed. The existing process was not replaced from a different shell, which would not inherit the user's Gemini key.
