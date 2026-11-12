# Current privacy behavior

INDU's frontend talks to a local FastAPI backend. The project does not require a developer-operated hosted application server.

- Typed general chat goes from the local backend to Google Gemini using the backend-configured key. Conversation context is held in backend memory and cleared on restart or through the clear-memory endpoint. There is no Ollama connection in the active chat path.
- Activated live voice sends microphone audio to Google Gemini using the backend-configured key. Browser wake recognition depends on the browser's speech service and may use an external provider. Physical recognition and provider account behavior have not been validated in this audit.
- Edge TTS sends text to Microsoft's speech service when speech generation is requested. It is not an offline voice engine.
- Contacts, reminders and minimal draft status metadata are stored in the local SQLite database. Pending WhatsApp message previews are held in memory; persistent deduplication uses a fingerprint instead of a full message body.
- Confirmed drafts send the recipient number and encoded message to official WhatsApp Web through the user's browser. WhatsApp and the browser manage login, cookies, account linking, final sending and browser history. Indu cannot verify account login or message delivery in this mode.
- The React conversation view is held in page memory. No API key is stored in browser localStorage, and there is no analytics integration in the application code.
- The optional 3D visual runs locally. It does not require an image-generation or rendering service.

Gemini setup transmits a key to the loopback backend and validates it with Google, then stores it in the operating system's credential service. No key is returned by status endpoints or stored in browser storage. Validation may incur a small API request. An optional backend environment key remains supported. Device identifiers, but no credentials, can be saved in browser localStorage for audio preferences.

On Windows the default database and temporary speech files live under `%LOCALAPPDATA%/InduAI`, outside the installed application and project folders. The SQLite database is not encrypted. `INDU_DATA_DIR` and `INDU_DATABASE` can override storage. Migration retains the legacy project database, which cloud-sync software may still synchronize. Uninstall retains user data and OS credentials; removing a key is available in Settings.

Live information requests disclose only the requested city, asset or feed query to the fixed public provider. Open-Meteo/GeoNames provides weather/location data, Coinbase Exchange provides prices, and BBC provides technology headlines. Reminder titles remain local except when deliberately spoken or typed into Gemini, or displayed in an enabled desktop notification.

Browser desktop notifications require permission. Timely reminders require a running backend and an open interface for display/desktop notifications. This application cannot wake a powered-off computer. Privacy and installer behavior have local automated checks, but have not undergone an independent security audit or broad device testing.

Developer test reports and source backups are local artifacts, not application distribution assets. They may contain historical private configuration and must be excluded from releases.
