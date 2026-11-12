"""Standalone local launcher: bundled UI, loopback backend and clean shutdown."""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--credential-backend-check", action="store_true")
    args = parser.parse_args()
    if args.credential_backend_check:
        from backend.credentials import credential_backend
        print(json.dumps({"backend":type(credential_backend()).__module__}))
        return 0
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    os.environ["INDU_FRONTEND_DIR"] = str(base / "frontend/dist")
    os.environ["INDU_DESKTOP"] = "1"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    os.environ["INDU_ALLOWED_ORIGINS"] = url
    import uvicorn
    from backend.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=sock.getsockname()[1], log_level="warning", access_log=False))
    app.state.exit_callback = lambda: setattr(server, "should_exit", True)
    result = {"status":"failed", "reason":"Server did not become ready"}
    def open_interface():
        for _ in range(200):
            if server.should_exit:
                return
            try:
                with urllib.request.urlopen(url + "/health", timeout=.5) as response:
                    metadata = json.load(response)
                if args.smoke_test:
                    request = urllib.request.Request(url, headers={"Accept":"text/html"})
                    with urllib.request.urlopen(request, timeout=2) as response:
                        assert b"<div id=\"root\"></div>" in response.read()
                    with urllib.request.urlopen(url + "/favicon.svg", timeout=2) as response:
                        assert response.status == 200
                    result.update(status="passed", version=metadata["version"], bundled_frontend=True,
                                  loopback_only=True, clean_shutdown=True)
                    result.pop("reason", None)
                    server.should_exit = True
                else:
                    if args.ready_file:
                        args.ready_file.write_text(json.dumps({"url":url}), encoding="utf-8")
                    if not args.no_browser:
                        webbrowser.open(url)
                return
            except (OSError, ValueError, AssertionError):
                time.sleep(.1)
        server.should_exit = True
    worker = threading.Thread(target=open_interface, daemon=True)
    worker.start()
    try:
        server.run(sockets=[sock])
    finally:
        sock.close()
        worker.join(timeout=3)
    if args.smoke_test:
        print(json.dumps(result))
        return 0 if result["status"] == "passed" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
