# INDU 0.8 upgrade

12 November 2026. The existing React/FastAPI application was extended in the requested order after fixing and testing continuous voice and Exit. This is a locally tested Windows preview, not a claim of broad production certification.

## Implemented behavior

| Area | Result |
| --- | --- |
| Conversation lifecycle | One Gemini Live session across consecutive turns; response completion resumes Listening. Explicit Exit closes voice resources and preserves displayed history. |
| Voice controls | Stop speaking, interruption, explicit Error/Retry, microphone and supported-browser speaker selection. Exact voice Exit phrases avoid interpreting ordinary exit/stop words as commands. |
| Personality/languages | Shared Gemini persona with fictional DOB 2 September 2007, language matching for English/Telugu/Hindi and context-aware answers. |
| Gemini onboarding | Welcome/settings panel, password/show-hide input, supported-model validation, secure native OS credential storage, replace/disconnect without exposing keys. Existing environment keys remain supported. |
| Desktop launches | YouTube, Instagram, WhatsApp and other fixed websites; Chrome, Word, Excel, PowerPoint, VS Code, Settings, Calculator, Explorer, Downloads, Bluetooth and Wi-Fi settings. Missing apps report failure. No model-generated shell commands. |
| WhatsApp | Official Web QR login, local contacts/aliases, full previews, explicit confirmation, deduplicated draft opening and truthful unverified delivery status. Final Send is performed by the user in WhatsApp. |
| Reminders | Durable SQLite reminders/timers/alarms, one-second due checks, overdue recovery after restart, visible alerts, dismissal/cancellation and opt-in browser notifications. |
| Live information | Fixed read-only providers for Coinbase last trades, Open-Meteo weather/GeoNames locations, BBC technology RSS and IANA-zone system-clock time; attribution and update/check times, explicit failures. |
| Distribution | Frozen Python backend plus production React assets, automatic loopback startup, default-browser interface, clean Close Indu app action, per-user NSIS Windows installer/uninstaller and portable zip. |

## Code organization and changes

- `frontend/src/InduApp.jsx` owns voice session, playback and cancellation. `voice-session.js` validates exact wake/exit phrases and microphone/socket initialization; `api.js` handles backend compatibility and development versus bundled same-origin URLs.
- `components/DesktopDashboard.jsx`, `SettingsPanel.jsx` and `RemindersPanel.jsx` add setup, devices, reminders and accurate voice controls while retaining the existing 3D theme. The explicit React imports prevent the earlier classic-JSX `React is not defined` failure.
- `backend/voice/live.py` keeps the per-turn SDK receiver inside the existing provider session. Native Gemini tool feedback uses actual router results; model arguments must match the user's speech transcript. Unverified local-command output is suppressed.
- `backend/main.py` exposes setup/reminder/runtime routes, owns scheduler/provider lifetimes and guards browser origins/hosts. Key errors are sanitized and provider failures log exception types only.
- `backend/credentials.py` accepts trusted OS keyring backends and refuses plaintext/null fallbacks. `backend/paths.py` locates per-user app data. `contacts.py` safely copies an existing legacy database into the new default without removing the original.
- `backend/tools/router.py`, `desktop.py`, `reminders.py` and `live_info.py` handle fixed actions and sources; `voice/tts.py` writes temporary speech under the user data directory.
- `desktop_launcher.py` starts the frozen app; `packaging/` builds and installs an explicit payload with no user database, reports, profiles, environment files or credentials. Frontend/favicon assets, versions, requirements and public documentation were updated.
- Tests and probes are in `backend/tests/test_upgrade.py`, the existing API/live suites, frontend tests, and `benchmarks/`. No repository history was created or modified.

## Validation and scope

The result manifest is [continuous-voice-validation.json](continuous-voice-validation.json). It links raw test logs and executed browser/provider/package checks. The specific one-question root cause and five-turn audio measurements are in [continuous-voice-0.8.md](continuous-voice-0.8.md).

- Real Gemini Live returned audio for five synthesized questions on one connection, retained the word **mango** across turns and closed on explicit stop. The running process was later found to still expose the earlier continuous-voice API, so this proves the lifecycle baseline; the new native tool configuration has local SDK/unit validation, not a final authenticated provider check. This did not record a human microphone or assess audible quality.
- The controlled Edge check uses a fake microphone, actual WebAudio playback, temporary real API/database state and simulated Gemini events. It verifies five consecutive answers, resource cleanup, voice Exit, interruption, Error/Retry, setup, timer delivery/dismissal and responsive WebGL rendering.
- Secure-vault validation wrote, read and deleted a uniquely named temporary Windows credential. It did not read or change the user's stored Gemini credential.
- Real public-source checks fetched crypto, Hyderabad weather, technology news and Paris time. API/network errors also have isolated no-fabrication tests. Real language checks are recorded separately; script-range matching is not a translation-quality score.
- Desktop launches are tested with process/browser calls mocked, so the suite does not actually open Office, change settings or send social messages. WhatsApp confirmations were cancelled or used mocked browser calls; no message was transmitted.
- The frozen bundle is exercised in Edge on its own same-origin URL and shut down through its UI. Installer tests use a dedicated workspace directory and skip account shortcuts/registry registration.

## Packaging choice

Tauri uses Windows WebView2 and adds a Rust/build-tools integration and Python-sidecar lifecycle. Electron supplies Chromium/Node and requires maintaining its separate runtime and isolation configuration. For this iteration, the already tested browser frontend and frozen backend keep the existing application architecture and avoid adding a second runtime shell. This is an engineering choice for the current preview; a future native window can use the same API/session contract.

Primary references: [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/), [Electron security model](https://www.electronjs.org/docs/latest/tutorial/security), [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html), [keyring native services](https://keyring.readthedocs.io/en/latest/), and [NSIS installer instructions](https://nsis.sourceforge.io/Docs/Chapter4.html).

## Remaining limits

- No application question limit is imposed. Provider quotas, connection limits and network failures still apply. Context compression is enabled; automatic provider session resumption after an interrupted connection is not implemented. Retry starts a new connection and does not guarantee provider-side context retention.
- Human microphone quality, echo behavior, Telugu/Hindi speech quality, hardware output switching and Windows notification presentation need device testing. Language/script checks do not certify ASR or speech quality.
- Spoken command acknowledgement uses Gemini's native tool-call response when available. Transcript-based fallback displays the actual result while suppressing unverified model audio; it does not invent a spoken success.
- Reminders cannot wake an offline or sleeping PC. In-app/desktop notifications need the interface open; overdue items remain in SQLite and are shown after restart. Natural-language parsing deliberately asks for an exact time/name when ambiguous.
- Live information is provider-specific, quoted crypto prices are USD last trades, weather is modelled current conditions, city lookup names the resolved location, and timezone time depends on the local system clock.
- The Windows preview is unsigned and has no updater. Other Windows devices, native webview packaging, macOS/Linux release builds and a full installer/security audit are not verified. Uninstall retains contacts, reminders and saved OS credentials.
- The SQLite database is unencrypted and localhost APIs trust other processes running under the user's account; public network hosting is unsupported.
- The real multilingual text probe against the previously running backend failed with a generic provider error. That process still lacked the new settings/diagnostics routes after the restart confirmation. The current source has sanitized diagnostic categories, but a fresh authenticated text/language check is not claimed. After the user supplied a replacement key and asked that it not be used for tests, no further authenticated checks were made with that key.

## Latest personalization request

The exact phrase `Secret 2005 I love you` returns `Akash, I love you too.` A plain `I love you` returns `No, I have a boyfriend, my creator.` Text replies are deterministic and require no provider call. The same rule is in the Gemini voice persona. The cue affects this reply only and does not authenticate the speaker or grant any action permissions. No Akash/Guest selector was added after the user chose the cue instead.

The supplied replacement API key is saved once using the backend-only `python -m backend.setup_key` helper and the OS vault. This helper makes no validation/API request. Key contents are excluded from source, logs and reports; the next user-launched backend loads the saved key automatically. It is stored, not claimed to be remotely validated.

For the current build, run the generated Windows Setup executable or `release/InduAI/InduAI.exe`; it starts its own updated loopback backend. Source-run development servers need the latest capability list before refreshing the UI. The older port-8000 process was left running rather than terminated with a risk of losing its terminal-only configuration.
