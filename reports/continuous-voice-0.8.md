# INDU 0.8 — continuous conversation and explicit Exit

12 November 2026. The conversation lifecycle, cleanup, and missing favicon were fixed first. Subsequent requested setup, scheduling and packaging work is described in [upgrade-0.8.md](upgrade-0.8.md).

## Root cause

1. `frontend/src/InduApp.jsx` called `finishOneQuestion()` after `turn_complete` and after queued playback drained. That function intentionally called session teardown, closed the WebSocket/microphone and restarted wake recognition. It imposed one question per activation.
2. `backend/voice/live.py` returned from the Gemini receiver after a completed local command. This caused the bridge's `FIRST_COMPLETED` wait to cancel the other task and close the provider context.
3. There was no explicit favicon link or icon asset in the frontend, so the browser requested a missing `/favicon.ico`.

## Changes

- Replaced question-level shutdown with `finishResponse()`. It waits for both provider turn completion and actual WebAudio playback completion, then returns to Listening while keeping the same WebSocket, microphone and AudioContext.
- The backend re-enters the SDK's per-turn `receive()` iterator on the same Gemini Live session. Normal answers and local commands do not end the bridge.
- Added explicit user-turn boundaries and retained the latest 100 completed voice turns plus the current turn in the interface. Gemini context remains on the active provider session and context compression remains enabled.
- Explicit Exit invalidates old callbacks, sends the stop event, closes the socket, stops/disconnects scheduled audio, closes the AudioWorklet port and AudioContext, stops every microphone track and aborts wake recognition. It preserves displayed history and shows **Indu is sleeping**. Wake recognition does not restart after Exit.
- Only exact normalized commands `Exit Indu`, `Bye Indu`, `Goodbye Indu`, `Stop Indu`, and `Quit Indu` perform voice Exit. Unrelated uses of exit, quit or stop do not.
- **Stop speaking** flushes current playback and suppresses remaining response audio without ending microphone capture or the Live connection.
- Provider/configuration failures show a visible Error state, release failed transport resources and expose **Retry voice**. Retry is an explicit new connection; it is not an automatic per-answer reconnect.
- Added Sleeping, Executing and Reconnecting states and accurate microphone captions. A pending message preview does not override the Sleeping state after Exit.
- Added `/favicon.svg` and an explicit SVG icon link.
- Backend/frontend version is 0.8.0, and the compatibility check requires `continuous_voice`, preventing the new client from accidentally using the old one-question backend.

The SDK iterator behavior and long-session configuration were checked against the installed SDK and Google's [Live SDK implementation](https://github.com/googleapis/python-genai/blob/main/google/genai/live.py) and [session management guidance](https://ai.google.dev/gemini-api/docs/live-api/session-management).

## Tests actually run

### Real authenticated Gemini Live

The running local backend advertised version 0.8.0 with continuous voice and had Gemini configured. The test connected through that backend without reading its key. Later feature inspection showed that process still had the earlier lifecycle build, so these real results validate the continuous-conversation baseline rather than subsequent setup/native-tool changes. Five predefined questions were synthesized using the installed Windows voice and streamed as 16 kHz PCM. Gemini returned audio and transcripts for all five turns on one WebSocket:

| Turn | Question | Response audio bytes | End-to-end wall time |
| --- | --- | --- | --- |
| 1 | Remember the test word mango | 167,520 | 7.35 s |
| 2 | Recall the previous test word | 128,640 | 6.76 s |
| 3 | Define Python briefly | 282,242 | 9.90 s |
| 4 | Give one use of it | 266,880 | 8.97 s |
| 5 | State Indu's date of birth | 149,762 | 6.37 s |

Gemini recalled **mango**, answered the Python follow-up, and returned **“My date of birth is 2 September 2007.”** Explicit stop closed the socket. These timings include paced input speech and waiting for response completion; they are not first-token or inference-only benchmarks.

Evidence: [live-voice-check.json](live-voice-check.json). This test did not record a physical microphone or measure audible speaker quality. The initial Edge TTS fixture was unavailable; Windows speech synthesis generated the test questions instead. The real-provider test made no desktop or WhatsApp actions.

### Controlled browser and backend checks

The headless Edge check used a temporary database, fake microphone, simulated provider events and **real native WebAudio playback** of generated PCM. It verified:

- Five successive audio responses finish playing and return to Listening on the same socket, microphone stream and AudioContext, with microphone frames continuing between answers.
- The history remains visible, and ordinary questions containing exit or stop do not exit.
- Simulated local-command results keep the conversation active.
- Interruption stops queued audio and accepts a new question without reconnecting.
- Stop speaking ignores remaining response audio and leaves the microphone/socket active.
- Exit during playback closes tracks, contexts, sources, sockets and wake recognition, preserves the transcript and remains Sleeping after the old wake-restart interval.
- Voice `Exit Indu` performs the same cleanup.
- Error/Retry stays explicit; missing credentials do not silently show Sleeping.
- Startup cancellation, contact previews, responsive layouts, WebGL rendering and the favicon still work.

Backend tests additionally exercised five audio turns and repeated local commands on one fake provider session, exactly-once execution, Stop speaking behavior, explicit stop, disconnect/error cancellation, and absence of remaining bridge tasks. Frontend tests cover exact exit phrases, old-backend rejection, microphone cancellation and JSX compatibility.

Current automated results and raw output are in [continuous-voice-validation.json](continuous-voice-validation.json); controlled-browser evidence is in [browser-smoke.json](browser-smoke.json).

## Files modified

- `backend/voice/live.py`, `backend/main.py`, `backend/tests/test_live.py`, `backend/tests/test_api.py`.
- `frontend/src/InduApp.jsx`, `voice-session.js`, `api.js`, `components/DesktopDashboard.jsx`, `components/AssistantScene.jsx`, `components/Icon.jsx`, `App.css`.
- `frontend/index.html`, `frontend/public/favicon.svg`, frontend package version/lockfile, frontend compatibility/voice tests.
- `benchmarks/browser_smoke.py`, new `benchmarks/live_voice_check.py`, README and this result report.

## Remaining limits

- There is no application-imposed question limit. Gemini quotas, network failures and provider connection limits still apply. Context compression is enabled; automatic session resumption/reconnection after provider loss remains future work. The app shows Error/Retry rather than silently sleeping, and Retry does not guarantee provider-side context continuity.
- Natural multilingual voice and the English five-turn test use Gemini. Real Telugu/Hindi microphone quality, device switching and physical speaker/echo behavior were not validated in this run.
- Local command acknowledgements display actual router results and now support native Gemini function-call feedback. Transcript fallback still suppresses unverified model audio.
- Personal WhatsApp still uses complete previews, explicit confirmation and user-controlled final Send in official WhatsApp Web. No delivery claim is fabricated.
- Secure onboarding, native credentials, reminders, live-data providers and Windows packaging were implemented after lifecycle validation; see the separate upgrade report for scope and remaining release limits.

The old port-8000 process still advertised the earlier 0.8 feature set after the restart confirmation. The new frontend now requires the setup/reminder/live-information capabilities as well and displays a restart notice for that process. The standalone launcher starts the current bundled backend on its own loopback port. The supplied replacement key is stored without an authenticated test request, as requested by the user.
