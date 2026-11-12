# Indu AI project audit and repairs

This is the historical 0.6.1 audit. See [phase-1-review.md](phase-1-review.md) for the current architecture, confirmation safeguards, 3D interface, and implementation plan following the expanded specification.

Audited on 12 November 2026. This folder was not a Git repository. Original application source was preserved in `original-source.zip` before edits; the archive excludes installed environments and generated files.

The core app is a desktop-assistant prototype with working orchestration code, rather than a trained AI model of its own. Reproducible startup, command-routing, voice-lifecycle, audio, and dependency issues have been fixed. End-to-end AI responses still require the external services described below.

## Existing code and implementation status

| Location | Existing implementation |
| --- | --- |
| `frontend/src/main.jsx` | React entry point; renders `InduApp.jsx` under Strict Mode. |
| `frontend/src/InduApp.jsx` | Active voice UI: browser wake recognition, manual start/exit, WebSocket connection, microphone capture, streamed playback, and transcripts. |
| `frontend/public/mic-processor.js` | AudioWorklet converting native-rate mono audio into 640-sample, 40 ms PCM16 frames at 16 kHz. |
| `frontend/src/App.jsx` | Earlier unused UI with ScriptProcessor-based recording. It is not imported by the active entry point. |
| `frontend/src/components/InduCore.*` | Unused alternative visual component and styles. |
| `backend/main.py` | FastAPI API for chat, speech generation, local recording, memory clearing, health, and the Gemini WebSocket bridge. |
| `backend/brain/llm.py` | Ollama HTTP client with an in-process conversation history. Default model: `qwen3:8b`. No local training or fine-tuning code. |
| `backend/tools/router.py` | Fixed list of websites and Windows apps, plus prefilled WhatsApp drafts. It does not automatically send messages. |
| `backend/tools/browser.py` | Separate Playwright browser controller; not used by the active router. |
| `backend/voice/stt.py` | Faster-Whisper CPU/int8 transcription, microphone recording, and resampling. |
| `backend/voice/tts.py` | Edge TTS generation and optional pygame playback, including English, Hindi and Telugu voices. |
| `backend/voice/wake_word.py`, `assistant_loop.py` | Standalone local Whisper → Ollama → Edge TTS assistant loop. |
| `backend/gemini_live.py`, `gemini_voice_test.py` | Standalone Gemini microphone demo and manual test entry point. |
| `backend/test_voice.py`, `test_tts.py`, `list_voices.py` | Manual diagnostics, rather than automated regression tests. |
| `backend/brain/memory.py`, `planner.py` | Empty placeholders. Persistent memory and planning are not implemented. |
| `backend/tools/computer.py`, `files.py`, `whatsapp.py` | Empty placeholders. There is no general computer-control, file-management, or separate WhatsApp integration here. |
| `backend/database/indu.db` | Zero-byte file; a read-only schema inspection found no tables. The active chat code does not use SQLite. |
| `config/settings.json` | Previously empty; now valid `{}`. Reserved and not loaded by the app. Runtime configuration uses environment variables. |

The original project contained 21 Python source files, many of which were empty or manual diagnostics. It also contained several virtual environments and installed frontend dependencies. Those installed directories are not application source. The original README was empty, and there were no automated regression suites or benchmark scripts.

## Reproduced errors and fixes

| Severity | Location | Reproduced issue and repair |
| --- | --- | --- |
| Critical | `backend/main.py` | Import failed because `google-genai` was missing. Added dependency manifests, installed the SDK in `backend/venv`, and made Gemini optional at startup. Core API import is now tested with optional voice packages disabled. |
| High | `backend/tools/router.py` | Imported unused, missing `pyautogui`, which would cause another startup failure. Removed that dependency. |
| High | Router | Questions such as `What is YouTube?` opened websites. Broad substring checks also accepted negated or extended commands. Replaced them with complete, explicit command parsing and a fixed target list. |
| High | Router and API | Failed launch attempts were reported as successful. Router results now include actual success flags, propagated to chat and voice clients. Windows launches use fixed executables without a command shell. |
| High | `backend/voice/live.py` (new) | Commands were executed from partial transcription chunks and lowercased, potentially opening incomplete targets or altering message content. Commands now wait for completed input or a complete-turn fallback, preserve case, and execute once per utterance. |
| High | Voice bridge | A raw WebSocket disconnect event was not handled, the reset handler did not update the shared transcript variable, and completed task errors could be hidden. The new bridge handles disconnect/reset, propagates failures, and cancels and awaits both tasks. |
| High | Voice bridge and standalone demo | SDK `receive()` ends at a turn boundary; the original one-pass iteration could close the bridge after a single turn. Both receivers now re-enter it for later turns. |
| High | Frontend voice startup | Resolved startup at WebSocket upgrade before Gemini was ready. A connection could close before readiness, and a late microphone permission grant could leave audio running after cancellation. Added a tested connection helper, ready handshake, pending-socket registration, stale-session checks, and microphone-track cleanup. |
| High | Browser origins | Wildcard CORS and no WebSocket origin checks allowed untrusted browser origins to reach local desktop-control routes. Added configurable origin restrictions before HTTP route execution and WebSocket acceptance. This is still a localhost, single-user app, not an authenticated hosting service. |
| High | Frontend dependencies | `npm audit` reported two high-severity affected packages: Vite and source-map-js. Applied compatible updates to Vite 7.3.8 and source-map-js 1.2.2. Final audit reports zero known vulnerabilities. |
| Medium | Local STT startup | Whisper was initialized during API import, potentially querying audio hardware, loading a large model, or downloading files before the server could start. It is now loaded only on `/api/listen`, with microphone access serialized. |
| Medium | Brain and API | Connection failures and invalid model responses were returned as successful chat text. Errors now map to HTTP 503, 504, or 502 and do not enter conversation history. |
| Medium | Brain history | `max_history=0` retained unlimited history due to `[-0:]`; odd limits could leave unmatched turns. Zero disables history, odd limits keep complete pairs, and a lock preserves ordering across concurrent requests and memory clearing. |
| Medium | TTS and STT files | Shared output filenames could mix concurrent recordings/responses. Unique files are now used. Generated API MP3 files are removed after the response; failed TTS generation removes partial files. Local playback is serialized. |
| Medium | Local audio | Microphone index 9 was hardcoded, and Whisper always used English. Default device selection is now used, and language detection is automatic. The local assistant reuses one Whisper instance for wake and question recognition. |
| Medium | AudioWorklet | Floating-point phase accumulation lost a sample at 44.1 kHz, producing only 24 complete frames from one second of input. Integer sample counting now produces 25 frames at 16, 44.1 and 48 kHz, verified by tests. |
| Medium | Frontend commands/transcripts | A question containing `exit` or `quit` could end the session. Exit commands now require completed input matching an explicit phrase. Raw transcription fragments are joined without inserted spaces, command results display, and backend errors are visible. |
| Medium | Standalone Gemini demo | PortAudio callbacks touched asyncio queues from another thread; repeated `sd.play` calls replaced audio playback. Queue access now uses the event loop, input buffering is bounded, and output uses a persistent stream with ordered chunks. |
| Medium | Legacy browser controller | `asyncio.to_thread` could move Playwright objects between threads. A dedicated executor now keeps browser work and cleanup on one thread; legacy commands use exact matching. |
| Medium | Layout | Fixed viewport height and hidden overflow allowed the growing conversation panel to become cropped and internally scrolled off center. The page now grows vertically, remains centered, wraps long text, and passes desktop/mobile browser layout checks. |
| Low | Setup and documentation | Added a README, environment-variable examples, Python dependency manifests, ignore rules, automated tests, benchmark scripts, and saved reports. Package-mode backend and manual-demo imports now work from the project root. |

## Benchmarks and validation

Environment: Windows 11, Python 3.13.5, Node 24.19.0, FastAPI 0.141.1, Google GenAI 2.34.0. Exact runtime metadata and measurements are in [benchmark-results.json](benchmark-results.json).

| Check | Before repairs | After repairs |
| --- | --- | --- |
| Backend import | Failed on missing Gemini SDK | Passes, including with optional voice dependencies disabled |
| Targeted command-routing corpus | 21/40 correct (52.5%) | 40/40 correct (100%) |
| Unintended actions on chat inputs in that corpus | 17 | 0 |
| Automated backend tests | None found | 34 passed |
| Automated frontend tests | None found | 14 passed |
| Browser smoke scenarios | None found | 6 checks passed in installed headless Edge |
| Frontend production build | Passed, about 1.01 s | Passed, about 0.78–1.00 s in measured runs |
| Known npm dependency vulnerabilities | 2 high | 0 reported after compatible fixes |
| Python dependency consistency | Not previously documented | `pip check` passes |

Local timing measurements, in milliseconds:

| Operation | Samples | Median / p50 | p95 |
| --- | --- | --- | --- |
| Router with mocked desktop/browser launchers | 1,000 | 0.1682 | 0.2499 |
| FastAPI root through in-process TestClient | 100 | 0.9301 | 1.3553 |
| Chat API with mocked model response | 100 | 1.3698 | 2.0337 |

The routing corpus is a small, deliberately targeted regression set created during this audit. Its 100% result is not a general natural-language accuracy score. Launchers were mocked in both routing runs; the original unused `pyautogui` import was stubbed to evaluate the baseline logic safely. No browser apps were actually opened or messages sent during the routing benchmark.

HTTP timings measure local API overhead with mocked inference, not AI response speed, network latency, or desktop launch time. Final assets are approximately 231.31 kB JavaScript (72.64 kB gzip) and 6.76 kB CSS (2.12 kB gzip). Build timings vary with machine load and cache state.

Browser checks used synthetic microphone audio, the real local API error path without a key, and simulated live-session messages. They verified manual startup, visible missing-key errors, late-permission/cancellation cleanup, transcript handling, command-result display, completed-turn cleanup, no uncaught runtime errors, and desktop/mobile layout. See [browser-smoke.json](browser-smoke.json) and [frontend-smoke.png](frontend-smoke.png).

The current Starlette TestClient emits an upstream deprecation warning about its `httpx` adapter. All tests pass; this warning is not an application runtime failure.

## Measurements that remain unavailable

- **Ollama response speed and generation throughput:** a real request was attempted with loopback access outside the sandbox. `127.0.0.1:11434` refused the connection (WinError 10061). Model tokens/second, quality, and first-token latency cannot be reported from this run.
- **Gemini voice latency and answer quality:** no `GEMINI_API_KEY` was configured. The installed SDK accepts the session configuration, but no authenticated Gemini session was measured.
- **Speech recognition word error rate and wake-word accuracy:** there is no labeled audio dataset. Synthetic sample/frame tests do not establish recognition accuracy, multilingual accuracy, or noise robustness.
- **Physical microphone/speaker quality:** headless checks used fake audio. Real hardware playback, echo cancellation, and recognition require a manual test.
- **Standard AI benchmarks:** no MMLU, HumanEval, SWE-bench, or similar harness/dataset is present. There is no evidence supporting a project-level score on these benchmarks.

The app retains shared in-process chat history only. SQLite persistence, planning, general file operations, arbitrary computer control, user authentication, and production hosting remain unimplemented product capabilities. No fabricated implementation was added to the empty placeholders. The unused earlier UI and alternative orb component remain as historical code.

## Reproduce the checks

From `C:\Users\akash\OneDrive\Desktop\INDU` in PowerShell:

```powershell
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
.\backend\venv\Scripts\python.exe benchmarks/run.py --ollama
.\backend\venv\Scripts\python.exe benchmarks/browser_smoke.py
npm.cmd --prefix frontend audit
```

Use the [README](../README.md) for startup commands. Real inference needs Ollama running with the configured model; real Gemini voice needs a backend API key. Dependency manifests describe a supported range; npm uses its lockfile for exact frontend versions. The audited backend environment's exact versions are recorded with the benchmark metadata.

Additional evidence: [baseline-routing.json](baseline-routing.json), [validation-results.json](validation-results.json), [backend-tests.txt](backend-tests.txt), [frontend-tests.txt](frontend-tests.txt), [npm-audit.json](npm-audit.json).

SDK behavior and configuration were checked against Google's [Live API reference](https://ai.google.dev/api/live), [capabilities guide](https://ai.google.dev/gemini-api/docs/live-api/capabilities), and [Python SDK implementation](https://github.com/googleapis/python-genai/blob/main/google/genai/live.py). Provider access and live performance still depend on the user's account and network.
