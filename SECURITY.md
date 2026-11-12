# Security status

INDU is a single-user localhost application with a source-run mode and a Windows preview bundle. It is not designed for public hosting. See [the 0.8 report](reports/upgrade-0.8.md) for validation scope and release limits.

Run the backend on `127.0.0.1`. Browser origins and HTTP hostnames are allowlisted for both HTTP and WebSocket operations. The standalone launcher binds an ephemeral loopback port and allows only its own interface origin. Other processes under the same OS account can access the local API; this is not a multi-user security boundary or a remotely authenticated service.

Gemini keys can be validated and stored through Settings using a trusted native keyring backend (Windows Credential Manager, macOS Keychain, or Secret Service). Unknown, plaintext and null keyring backends are refused. Status endpoints never return keys, key-validation errors are sanitized, and provider failures log only an exception class. The optional shell environment key remains supported. No credentials belong in React files, browser storage, Git, screenshots or logs.

Desktop actions use fixed targets and executables. Language-model output cannot become a shell command. New destructive actions require a structured preview and explicit approval before implementation is enabled.

WhatsApp requests prepare a full recipient/message preview. A separate explicit confirmation opens an official WhatsApp Web draft; the user presses Send there. No direct transmission or verified delivery is claimed. Preview IDs are random, single-action, cancellable and expire for confirmation after ten minutes. Request IDs prevent the same draft being opened again automatically.

Contacts and draft metadata use ordinary local SQLite. Full message bodies are not retained in the draft-metadata table; pending previews exist in backend memory. This database is not encrypted. Protect the Windows user account and its files.

Do not distribute the workspace, virtual environments, database, source backups, browser profiles, private reports, `.env` files or API keys. The Windows build packages the frozen application, production frontend and public documentation. Installer/uninstaller targets are validated and user data/credentials are retained on uninstall. The current preview is unsigned and has no automatic updater.

When reporting a vulnerability, describe the trigger and affected version with secrets and personal data removed. No public security contact or release-signing process has been established yet.
