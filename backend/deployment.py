"""Deployment policy shared by API routes and desktop helpers."""
import os


def deployment_mode():
    mode = os.environ.get("INDU_DEPLOYMENT_MODE", "local").strip().casefold()
    if mode not in {"local", "cloud"}:
        raise ValueError("INDU_DEPLOYMENT_MODE must be local or cloud.")
    return mode


def is_cloud():
    return deployment_mode() == "cloud"


def allowed_origins():
    defaults = "" if is_cloud() else "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    origins = [value.strip().rstrip("/") for value in os.environ.get("INDU_ALLOWED_ORIGINS", defaults).split(",") if value.strip()]
    if is_cloud() and os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
        origins.append("https://" + os.environ["RENDER_EXTERNAL_HOSTNAME"].strip())
    return list(dict.fromkeys(origins))


def allowed_hosts():
    hosts = ["127.0.0.1", "localhost", "testserver"]
    hosts.extend(value.strip() for value in os.environ.get("INDU_ALLOWED_HOSTS", "").split(",") if value.strip())
    if is_cloud():
        hosts.extend(filter(None, [os.environ.get("RENDER_EXTERNAL_HOSTNAME")]))
        # Custom public API domains must be explicit; CORS frontends are separate.
    return list(dict.fromkeys(hosts))
