# Indu AI

Indu is a local desktop-assistant prototype with a React voice interface and a FastAPI backend. Both text chat and live voice use Google Gemini through the local backend. Ollama is not required. Local microphone diagnostics use Faster-Whisper, and optional speech generation uses Edge TTS.

The continuous-conversation fix and measured results are in [reports/continuous-voice-0.8.md](reports/continuous-voice-0.8.md). Setup, desktop actions, reminders, live information and Windows packaging are described in [reports/upgrade-0.8.md](reports/upgrade-0.8.md). Historical assessments remain in `reports/phase-1-review.md` and `reports/analysis.md`.

## Run on Windows

Use Python 3.11+ and a Node version supported by the locked Vite release (the audited environment uses Python 3.13 and Node 24). Run commands from the project root unless shown otherwise.

```powershell
# The existing project environment is backend/venv.
# For a fresh checkout, create it first:
python -m venv backend/venv
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
```

Start the backend. The welcome screen lets each user validate and save their own Gemini key in the OS credential store; a shell key is optional:

```powershell
.\backend\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir backend
```

In another terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`. Allow microphone access. Wake listening depends on browser speech-recognition support; **Hey Indu** also starts the session. INDU 0.8 keeps the same Gemini Live conversation, microphone and WebSocket active across successive questions. After each complete response finishes playing, it returns to **Listening** without another activation.

Use **Stop speaking** to stop the current response while keeping the conversation active. **Exit Indu** or an exact voice command (`Exit Indu`, `Bye Indu`, `Goodbye Indu`, `Stop Indu`, or `Quit Indu`) closes voice resources and displays **Indu is sleeping**. Exit preserves visible history and does not restart background wake recognition. Click Hey Indu to activate again. Network/configuration failures show an explicit Error state with **Retry voice**; they do not silently become Sleeping. Retry establishes a new provider connection, so provider-side context continuity after a failed connection is not guaranteed.

The API starts even if optional voice dependencies or credentials are unavailable. `GET /health` reports local Gemini configuration; it does not validate remote authentication or model access. Text defaults to `gemini-3.8-flash` (`GEMINI_TEXT_MODEL`), while voice uses `GEMINI_LIVE_MODEL`. Whisper is loaded only on the first `POST /api/listen`, which may download its model and records the backend computer's microphone. The browser voice interface sends its own microphone audio over `/ws/voice`.

If the interface reports that the backend needs restarting, stop the old backend with **Ctrl+C in its terminal**, then run the backend command above from the project root. Use the same terminal to preserve its Gemini key environment variable. Refresh the browser with **Ctrl+Shift+R**. Backend 0.8.0 advertises the continuous-voice capability; earlier backends must be restarted to load it. `--reload` watches backend source changes during development.

This app is intended for one user on localhost. Conversation history is shared in process and is cleared on restart. Browser origins are restricted; configure `INDU_ALLOWED_ORIGINS` when changing frontend ports. There is no user authentication for network hosting.

## One-time key storage without a test request

The optional command below asks for a key in a hidden console prompt and stores it only in the OS vault. It makes no Gemini request. Later backend launches load the saved key automatically, including the packaged application. The Settings validation flow remains available when you choose to test a key yourself.

```powershell
.\backend\venv\Scripts\python.exe -m backend.setup_key
```

## Personalization

A configured creator phrase selects the personal affection reply; a plain `I love you` uses the guest reply. Text replies run locally and the voice persona has the same rule. The phrase is not advertised in the interface. It changes this reply only and does not verify identity or grant action permissions.

## Configuration and endpoints

[.env.example](.env.example) lists backend environment variables. Set them in the shell; `.env` files are not automatically loaded. `frontend/.env.example` documents the optional `VITE_API_URL` override; Vite loads a copied `frontend/.env.local` after restart. Keep API keys on the backend.

Supported commands include `open youtube`, `launch calculator`, `open Microsoft Word`, `open Excel`, `open PowerPoint`, `open Visual Studio Code`, `open Downloads`, `open Bluetooth settings`, `open Wi-Fi settings`, and `please open gmail`. Launch targets are allowlisted; unavailable apps report failure. Unknown text stays in chat.

**Settings** provides Gemini key validation/replacement/disconnection and microphone/speaker selection. Keys are sent only to the local backend, validated with Gemini, then saved through a trusted native OS credential backend. No plaintext fallback or browser key storage is used. Exit voice before changing the key or devices. A saved OS key takes precedence over the optional `GEMINI_API_KEY` environment variable. Disconnecting removes the saved key; a key still set in the launching terminal can configure Gemini after a process restart.

**Reminders** saves timed reminders, alarms and timers locally. Try `Set a timer for 10 minutes`, `Remind me at 7 PM to call Deva`, `Remind me tomorrow at 9 AM to call Deva`, or `Show my reminders`. An ambiguous cancellation asks you to choose the exact reminder. The backend checks due items every second; the UI polls every two seconds and shows overdue alerts until dismissed. Enable browser desktop notifications in Reminders. Indu must be running for timely alerts; missed reminders appear after restart. It does not wake a sleeping or powered-off computer.

Live requests include `What is the Bitcoin price right now?`, `What is Ethereum's price?`, `What is the weather in Hyderabad?`, `What is the current time in Paris?`, and `What is the latest technology news?`. Prices use Coinbase Exchange last trades in USD, weather uses Open-Meteo/GeoNames, news uses BBC Technology RSS, and time uses the system clock plus IANA zone data. Responses include sources and check/update times. Missing locations prompt clarification, and failed providers return an error instead of an invented answer.

The dashboard includes an interactive Three.js core, a text conversation panel and WhatsApp contact/message controls. Open **WhatsApp and contacts** from the sidebar. Use **Open WhatsApp Web to link** and scan the QR code in the official website using WhatsApp → Linked devices → Link a device. Indu cannot verify that browser account's login status.

Add a contact's name, international number and optional aliases in **Contacts**. Say or type `Send a WhatsApp message to Deva saying I will be there at six.` Indu shows the complete recipient and message. After **Confirm and open WhatsApp**, review the draft and press **Send** in WhatsApp. There is no silent automatic sending, and an opened draft is never reported as sent or delivered. Cancelled or expired previews cannot proceed; repeated confirmations do not open the draft twice.

Contacts, reminders and minimal draft metadata persist in `%LOCALAPPDATA%/InduAI/indu.db` on Windows. `INDU_DATA_DIR` overrides the user data directory; `INDU_DATABASE` overrides the database path. An existing `backend/database/indu.db` is copied using SQLite backup when first migrating to the new default; the legacy copy is retained. The database is ordinary unencrypted SQLite. Full message bodies are not retained in draft metadata. Never distribute user data, `.env` files, source backups, browser profiles or private reports. See [PRIVACY.md](PRIVACY.md) and [SECURITY.md](SECURITY.md).

| Endpoint | Purpose |
| --- | --- |
| `GET /` | API liveness |
| `GET /health` | Component and Gemini configuration status |
| `POST /api/chat` | `{ "message": "..." }`; controlled local command or Gemini response |
| `POST /api/speak` | `{ "text": "..." }`; generated MP3 |
| `POST /api/listen` | Record 5 seconds on the backend microphone and transcribe |
| `POST /api/memory/clear` | Clear in-process Gemini text conversation history |
| `WS /ws/voice` | Mono PCM16 at 16 kHz in; PCM16 at 24 kHz and transcript events out |
| `GET/POST /api/contacts` | List/add locally stored contacts |
| `PUT/DELETE /api/contacts/{id}` | Edit/delete a contact |
| `POST /api/whatsapp/connect` | Open official WhatsApp Web for user-controlled linking |
| `POST /api/whatsapp/send` | Prepare a preview only; requires recipient, message and request ID |
| `POST /api/whatsapp/preview/{id}/confirm` | Explicitly confirm opening the prepared draft |
| `POST /api/whatsapp/preview/{id}/cancel` | Cancel a pending preview |
| `GET /api/whatsapp/status` | Local Web-opening state, not verified account login |
| `GET /api/whatsapp/messages` | Minimal draft status metadata; no message bodies |
| `GET/PUT/DELETE /api/settings/gemini` | Key status, validated secure storage, disconnect; never returns the key |
| `GET/POST /api/reminders` | List/create persistent reminders with a timezone-aware deadline |
| `POST /api/reminders/{id}/cancel` or `/dismiss` | Cancel or acknowledge a due reminder |
| `POST /api/app/exit` | Clean shutdown when run by the standalone desktop launcher |

## Windows installation and packaging

The `release/` directory contains the Windows application and installer generated from this source. Run `InduAI-0.8.0-Setup.exe`, then open **Indu AI** from Start. The fallback is `install.ps1` beside `InduAI-0.8.0-windows.zip` and `uninstall.ps1`. Installation is per user and requires no Python or Node installation on the recipient's computer. The installer is currently unsigned.

The launcher automatically starts a loopback-only backend, serves the bundled React interface and opens it in your default browser. **Close Indu app** stops the backend and active sessions; **Exit Indu** stops voice while leaving the application and reminders running. Closing the browser tab alone leaves the backend running. Windows Installed Apps can invoke the supplied uninstaller. User data and saved credentials are retained on uninstall; disconnect Gemini in Settings beforehand if desired.

To rebuild on Windows:

```powershell
.\backend\venv\Scripts\python.exe -m pip install -r packaging/requirements-build.txt
.\packaging\build.ps1
```

The current bundle uses PyInstaller and the system browser; a native webview shell is not required. Tauri and Electron were evaluated in the upgrade report. Optional offline Whisper diagnostics and the legacy Playwright controller are excluded from the bundle; Gemini Live works through the browser microphone. Code signing, automated updates and validation on other Windows machines remain release work.

## Validate and benchmark

```powershell
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\backend\venv\Scripts\python.exe benchmarks/run.py
```

The benchmark saves `reports/benchmark-results.json`. Routing and in-process HTTP measurements mock external actions and model responses. An optional `--gemini` flag runs three real Gemini text prompts with the backend environment key and may incur API usage charges. These results do not measure voice latency or speech-recognition accuracy.

Optional browser checks use Playwright and the installed Microsoft Edge browser:

```powershell
.\backend\venv\Scripts\python.exe benchmarks/browser_smoke.py
```

The browser check launches temporary localhost servers and an isolated contacts database. It uses fake microphone input and native WebAudio playback of synthetic PCM to test five consecutive answers on one socket, microphone capture between answers, interruption, Stop speaking, Exit during playback, voice Exit, error/retry, contact previews and the favicon. It cancels message previews without linking an account or sending a message. It saves screenshots and a JSON result under `reports/`.

An optional real-provider check uses the already running local backend and its key without reading or exposing the key:

```powershell
.\backend\venv\Scripts\python.exe benchmarks/live_voice_check.py
```

This sends five predefined synthesized speech questions to Gemini Live and checks response audio, a shared connection, a simple follow-up context test and explicit stop. It can incur Gemini API usage. It tries the existing TTS endpoint and falls back to the installed Windows speech synthesizer for test input. Physical microphone/speaker quality still requires a manual test. The result is saved as `reports/live-voice-check.json` and is marked unavailable if prerequisites fail.

There is no application-imposed question count limit. Gemini service limits, quotas and network failures still apply. Context compression is enabled for longer sessions; automatic provider-session resumption is not implemented. The display retains the latest 100 completed voice turns plus the current turn to bound rendering cost; this does not terminate the Gemini conversation.

Manual microphone demos remain available as `python -m backend.test_voice`, `python -m backend.test_tts`, `python -m backend.gemini_live`, and `python -m backend.voice.assistant_loop`. Use the project virtual environment. The legacy Playwright browser controller additionally requires `python -m playwright install chromium`; the active command router uses the system browser and does not require Chromium installation.
