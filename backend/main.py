"""Local Indu API. Start with: python -m uvicorn backend.main:app --host 127.0.0.1"""

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, SecretStr
from starlette.background import BackgroundTask

if __package__:
    from . import credentials
    from .deployment import deployment_mode, is_cloud, allowed_hosts, allowed_origins
    from .brain.persona import affection_reply
    from .brain.llm import BrainError, InduBrain, SYSTEM_INSTRUCTION
    from .tools.router import InduCommandRouter
    from .voice.live import bridge_voice
    from .voice.tts import InduTextToSpeech
else:
    import credentials
    from deployment import deployment_mode, is_cloud, allowed_hosts, allowed_origins
    from brain.persona import affection_reply
    from brain.llm import BrainError, InduBrain, SYSTEM_INSTRUCTION
    from tools.router import InduCommandRouter
    from voice.live import bridge_voice
    from voice.tts import InduTextToSpeech

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = types = None

logger = logging.getLogger(__name__)
VERSION = "0.8.0"
API_CONTRACT = 1
FEATURES = ["contacts", "whatsapp_previews", "gemini_text", "gemini_live", "continuous_voice", "secure_setup", "reminders", "live_information", "desktop_launch"]
if is_cloud():
    FEATURES.remove("desktop_launch")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_LIVE_MODEL = os.environ.get("GEMINI_LIVE_MODEL", "gemini-3.8-live")
ALLOWED_ORIGINS = allowed_origins()
brain = InduBrain(client_provider=lambda: gemini_client)
router = InduCommandRouter()
tts = InduTextToSpeech()
stt = None
stt_lock = threading.Lock()
gemini_client = None
active_voice_sessions = 0
credential_lock = asyncio.Lock()
key_source = "environment" if GEMINI_API_KEY else None
key_verified = False


@asynccontextmanager
async def lifespan(app):
    global gemini_client, GEMINI_API_KEY, key_source
    stored = None if is_cloud() else await asyncio.to_thread(credentials.load_key)
    if stored:
        GEMINI_API_KEY, key_source = stored, "os_credential_store"
    if genai is not None and GEMINI_API_KEY:
        try:
            gemini_client = genai.Client(api_key=GEMINI_API_KEY, http_options={"timeout": 45000})
        except Exception as failure:
            logger.warning("Could not initialize Gemini (%s)", type(failure).__name__)
    async def schedule_reminders():
        while True:
            await asyncio.to_thread(router.reminders.tick)
            await asyncio.sleep(1)
    scheduler = asyncio.create_task(schedule_reminders(), name="indu-reminders")
    yield
    scheduler.cancel()
    await asyncio.gather(scheduler, return_exceptions=True)
    await router.messenger.close()
    if gemini_client is not None:
        await gemini_client.aio.aclose()
        gemini_client.close()
        gemini_client = None


app = FastAPI(title="Indu AI Assistant", version=VERSION, lifespan=lifespan)
# No cookie-based authentication/session is used by the browser client.
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
# Last added runs first: validate Host even when CORS handles OPTIONS directly.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())


# CORS does not block execution of simple cross-origin POSTs or WebSockets.
# Reject browser origins before any route can launch a local app or record audio.
@app.middleware("http")
async def check_origin(request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Origin is not allowed."}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    if request.url.path.startswith("/api/settings/gemini"):
        return JSONResponse({"detail": "Enter a Gemini API key in the password field."}, status_code=422)
    return JSONResponse({"detail": [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
                                    for item in error.errors()]}, status_code=422)


class GeminiKeyRequest(BaseModel):
    api_key: SecretStr = Field(min_length=20, max_length=512)


@app.get("/api/settings/gemini")
def gemini_settings():
    return {"configured": gemini_client is not None, "source": key_source,
            "verified": key_verified, "model": brain.model, "live_model": GEMINI_LIVE_MODEL,
            "active_voice_sessions": active_voice_sessions,
            "credential_management":"environment" if is_cloud() else "os_credential_store"}


@app.put("/api/settings/gemini")
async def configure_gemini(request: GeminiKeyRequest):
    global gemini_client, GEMINI_API_KEY, key_source, key_verified
    if is_cloud():
        raise HTTPException(409, "Cloud credentials are managed with GEMINI_API_KEY in Render environment settings.")
    async with credential_lock:
        if active_voice_sessions:
            raise HTTPException(409, "Exit the active voice conversation before replacing the key.")
        if genai is None:
            raise HTTPException(503, "Install google-genai before connecting.")
        value = request.api_key.get_secret_value().strip()
        candidate = None
        try:
            candidate = genai.Client(api_key=value, http_options={"timeout": 20000})
            response = await candidate.aio.models.generate_content(
                model=brain.model, contents="Reply with OK.", config={"max_output_tokens": 64})
            if not response.text:
                raise ValueError("Empty validation response")
        except Exception:
            if candidate is not None:
                await candidate.aio.aclose()
                candidate.close()
            raise HTTPException(400, "Gemini validation failed. Check the key, model access, quota and internet connection.") from None
        try:
            await asyncio.to_thread(credentials.save_key, value)
        except RuntimeError as failure:
            await candidate.aio.aclose()
            candidate.close()
            raise HTTPException(503, str(failure)) from None
        previous = gemini_client
        gemini_client, GEMINI_API_KEY = candidate, value
        key_source, key_verified = "os_credential_store", True
        await asyncio.to_thread(brain.clear_history)
        if previous is not None:
            await previous.aio.aclose()
            previous.close()
        return gemini_settings()


@app.delete("/api/settings/gemini")
async def disconnect_gemini():
    global gemini_client, GEMINI_API_KEY, key_source, key_verified
    if is_cloud():
        raise HTTPException(409, "Cloud credentials are managed with GEMINI_API_KEY in Render environment settings.")
    async with credential_lock:
        if active_voice_sessions:
            raise HTTPException(409, "Exit the active voice conversation before disconnecting Gemini.")
        try:
            await asyncio.to_thread(credentials.delete_key)
        except RuntimeError as failure:
            raise HTTPException(503, str(failure)) from None
        previous, gemini_client = gemini_client, None
        GEMINI_API_KEY, key_source, key_verified = None, None, False
        await asyncio.to_thread(brain.clear_history)
        if previous is not None:
            await previous.aio.aclose()
            previous.close()
        return {**gemini_settings(), "note": "A key set in the launching terminal can configure Gemini again after a process restart."}


def build_live_config():
    if types is None:
        raise RuntimeError("Install google-genai to use Gemini Live.")
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            name="execute_local_command",
            description="Execute an explicit user request to open an allowlisted app or website, prepare a WhatsApp message preview, manage a reminder or fetch live weather, crypto prices, time or technology news. Use the user's exact command. Never claim sending a WhatsApp draft transmits it. Speak only the actual returned result.",
            parameters={"type":"object", "properties":{"command":{"type":"string"}}, "required":["command"]},
        )])],
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False, prefix_padding_ms=100, silence_duration_ms=500,
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
            ), activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        ),
        context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    request_id: str | None = Field(default=None, min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


class ChatResponse(BaseModel):
    success: bool
    response: str
    confirmation: dict | None = None


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


class ReminderRequest(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    due_at: datetime


@app.get("/api/reminders")
def list_reminders():
    return {"reminders": router.reminders.list()}


@app.post("/api/reminders")
def create_reminder(request: ReminderRequest):
    try:
        return router.reminders.create(request.title, request.due_at)
    except ValueError as failure:
        raise HTTPException(422, str(failure)) from None


@app.post("/api/reminders/{identifier}/{action}")
def update_reminder(identifier: str, action: str):
    try:
        router.reminders.update(identifier, {"cancel": "cancelled", "dismiss": "dismissed"}.get(action))
    except ValueError as failure:
        raise HTTPException(409, str(failure)) from None
    return {"success": True}


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=8, max_length=30)
    aliases: list[str] = Field(default_factory=list, max_length=10)


class WhatsAppSendRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")


@app.post("/api/whatsapp/preview/{identifier}/confirm")
async def confirm_whatsapp_preview(identifier: str):
    try:
        return await router.messenger.confirm_preview(identifier)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/whatsapp/preview/{identifier}/cancel")
def cancel_whatsapp_preview(identifier: str):
    return router.messenger.cancel_preview(identifier)


@app.get("/api/contacts")
def contacts():
    return {"contacts": router.contacts.list()}


@app.post("/api/contacts")
def add_contact(request: ContactRequest):
    try:
        return router.contacts.save(request.name, request.phone, request.aliases)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.put("/api/contacts/{contact_id}")
def edit_contact(contact_id: str, request: ContactRequest):
    try:
        return router.contacts.save(request.name, request.phone, request.aliases, contact_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.delete("/api/contacts/{contact_id}")
def delete_contact(contact_id: str):
    try:
        router.contacts.delete(contact_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    return {"success": True}


@app.get("/api/whatsapp/status")
def whatsapp_status():
    return router.messenger.status()


@app.post("/api/whatsapp/connect")
async def connect_whatsapp():
    try:
        return await router.messenger.connect()
    except (RuntimeError, OSError, asyncio.TimeoutError) as error:
        raise HTTPException(503, str(error)) from error


@app.post("/api/whatsapp/disconnect")
async def disconnect_whatsapp():
    try:
        return await router.messenger.disconnect()
    except (RuntimeError, OSError, asyncio.TimeoutError) as error:
        raise HTTPException(503, str(error)) from error


@app.get("/api/whatsapp/messages")
def whatsapp_messages():
    return {"messages": router.contacts.messages()}


@app.post("/api/whatsapp/send")
async def send_whatsapp(request: WhatsAppSendRequest):
    try:
        return await router.messenger.send_text(request.recipient, request.message, request.request_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


async def execute_voice_command(command_text, websocket):
    result = await router.execute(command_text)
    if result.get("type") != "browser":
        return False
    await websocket.send_json({"type": "command_result", "command": command_text,
                               "success": result["success"], "response": result["response"],
                               "action": result.get("action"), "status": result.get("status"),
                               "confirmation": result.get("confirmation")})
    return result


@app.get("/")
def root(request: Request = None):
    static_dir = os.environ.get("INDU_FRONTEND_DIR")
    if request and static_dir and "text/html" in request.headers.get("accept", ""):
        return FileResponse(Path(static_dir) / "index.html")
    return {"name": "Indu", "status": "online", "version": VERSION,
            "api_contract": API_CONTRACT, "features": FEATURES,
            "message": "Indu AI backend is running."}


@app.get("/api/app/status")
def desktop_status():
    return {"desktop": not is_cloud() and os.environ.get("INDU_DESKTOP") == "1"}


@app.post("/api/app/exit")
def exit_application():
    if is_cloud():
        raise HTTPException(409, "The cloud service is managed by Render; desktop shutdown is disabled.")
    callback = getattr(app.state, "exit_callback", None)
    if os.environ.get("INDU_DESKTOP") != "1" or callback is None:
        raise HTTPException(409, "Stop the development backend in its terminal with Ctrl+C.")
    callback()
    return {"success":True}


frontend_directory = os.environ.get("INDU_FRONTEND_DIR")
if frontend_directory:
    frontend_path = Path(frontend_directory).resolve()
    app.mount("/assets", StaticFiles(directory=frontend_path / "assets"), name="assets")

    @app.get("/favicon.svg")
    def favicon():
        return FileResponse(frontend_path / "favicon.svg", media_type="image/svg+xml")

    @app.get("/mic-processor.js")
    def microphone_processor():
        return FileResponse(frontend_path / "mic-processor.js", media_type="application/javascript")


@app.get("/health")
def health():
    gemini = brain.readiness()
    configured = gemini["configured"]
    return {
        "status": "configured" if configured else "degraded",
        "deployment_mode": deployment_mode(),
        "capabilities":{"desktop_control":not is_cloud(), "backend_microphone":not is_cloud(),
                        "backend_audio_playback":not is_cloud(), "browser_audio_streaming":True},
        "version": VERSION, "api_contract": API_CONTRACT, "features": FEATURES,
        "assistant": "Indu", "router": router is not None,
        "brain": configured, "gemini": gemini,
        "gemini_live": configured, "gemini_sdk": genai is not None,
        "gemini_key_configured": bool(GEMINI_API_KEY),
        "stt_loaded": stt is not None, "tts": tts.available,
    }


@app.post("/api/chat", response_model=ChatResponse, response_model_exclude_none=True)
async def chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(400, "Message cannot be empty.")
    reply = affection_reply(message)
    if reply:
        return ChatResponse(success=True, response=reply)
    try:
        result = await router.execute(message, request_id=request.request_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if result["type"] == "browser":
        return ChatResponse(success=result["success"], response=result["response"], confirmation=result.get("confirmation"))
    try:
        response = await asyncio.to_thread(brain.chat, message)
    except BrainError as error:
        raise HTTPException(error.status_code, str(error)) from error
    return ChatResponse(success=True, response=response)


@app.post("/api/speak")
def speak(request: SpeakRequest):
    if not request.text.strip():
        raise HTTPException(400, "Text cannot be empty.")
    if not tts.available:
        raise HTTPException(503, "Install edge-tts to use speech generation.")
    audio = tts.generate_audio(request.text.strip())
    if audio is None:
        raise HTTPException(502, "Indu could not generate speech.")
    return FileResponse(str(audio), media_type="audio/mpeg", filename="indu_output.mp3",
                        background=BackgroundTask(Path(audio).unlink, missing_ok=True))


@app.post("/api/memory/clear")
def clear_memory():
    brain.clear_history()
    return {"success": True, "message": "Conversation memory cleared."}


@app.post("/api/listen")
def listen():
    global stt
    if is_cloud():
        raise HTTPException(409, "The server microphone is disabled in cloud mode. Use browser audio through /ws/voice for Gemini Live.")
    # Only load Whisper on demand, and serialize access to the physical microphone.
    with stt_lock:
        try:
            if stt is None:
                if __package__:
                    from .voice.stt import InduSpeechToText
                else:
                    from voice.stt import InduSpeechToText
                stt = InduSpeechToText(model_size=os.environ.get("WHISPER_MODEL", "base"))
            text, language = stt.listen(duration=5.0)
            return {"success": True, "text": text, "language": language}
        except Exception as error:
            logger.exception("Local speech recognition failed")
            raise HTTPException(503, "Local speech recognition is unavailable. Check audio dependencies, model and microphone.") from error


@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    global active_voice_sessions
    origin = websocket.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    registered = False
    try:
        if genai is None:
            await websocket.send_json({"type": "error", "message": "Install google-genai in the backend environment to use live voice."})
            return
        if not GEMINI_API_KEY or gemini_client is None:
            await websocket.send_json({"type": "error", "message": "Connect Gemini in Settings, or configure GEMINI_API_KEY in the backend terminal."})
            return
        async with credential_lock:
            client = gemini_client
            if client is None:
                await websocket.send_json({"type": "error", "message": "Gemini was disconnected. Connect it in Settings."})
                return
            active_voice_sessions += 1
            registered = True
        async with client.aio.live.connect(model=GEMINI_LIVE_MODEL, config=build_live_config()) as session:
            await websocket.send_json({"type": "ready"})
            await bridge_voice(websocket, session, execute_voice_command, router.is_local_command)
    except WebSocketDisconnect:
        pass
    except Exception as failure:
        logger.warning("Gemini Live session failed (%s)", type(failure).__name__)
        try:
            await websocket.send_json({"type": "error", "message": "Live voice failed. Check the backend log, API key, model access and network."})
        except (RuntimeError, WebSocketDisconnect):
            pass
    finally:
        if registered:
            active_voice_sessions -= 1
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass
