"""Keep one Gemini Live connection across user turns until explicit stop or error."""

import asyncio
import json
from fastapi import WebSocketDisconnect


async def bridge_voice(websocket, session, execute_command, is_local_command=None):
    transcript = ""
    command_processed = False
    local_complete = False
    suppress_audio = False
    command_result = None
    tasks = []

    def reset_input():
        nonlocal transcript, command_processed, local_complete, command_result
        transcript, command_processed, local_complete = "", False, False
        command_result = None

    async def finish_input():
        nonlocal command_processed, local_complete, command_result
        if not transcript.strip() or command_processed:
            return
        command_processed = True
        await websocket.send_json({"type": "input_complete"})
        local_complete = bool(is_local_command and is_local_command(transcript.strip()))
        if local_complete:
            await websocket.send_json({"type": "command_started"})
        command_result = await execute_command(transcript.strip(), websocket)
        if local_complete:
            # End the local response only, never the conversation or transport.
            await websocket.send_json({"type": "turn_complete"})

    async def receive_browser():
        nonlocal suppress_audio
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            audio = message.get("bytes")
            if audio:
                if len(audio) % 2 or len(audio) > 65536:
                    await websocket.send_json({"type": "warning", "message": "Invalid PCM16 audio frame was skipped."})
                    continue
                await session.send_realtime_input(audio={"data": audio, "mime_type": "audio/pcm;rate=16000"})
                continue
            try:
                data = json.loads(message.get("text") or "{}")
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "stop":
                return
            if data.get("type") == "stop_speaking":
                suppress_audio = True
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    async def receive_gemini():
        nonlocal transcript, suppress_audio, local_complete
        while True:
            received = False
            # SDK receive() ends at a model turn boundary. Re-enter on the SAME session.
            async for response in session.receive():
                received = True
                calls = getattr(getattr(response, "tool_call", None), "function_calls", None) or []
                for call in calls:
                    # The speech transcript is authoritative. A model cannot supply a
                    # different recipient, command or unspoken shell instruction.
                    await finish_input()
                    supplied = (getattr(call, "args", None) or {}).get("command", "")
                    if (call.name == "execute_local_command" and command_result
                            and is_local_command and is_local_command(transcript.strip())
                            and " ".join(supplied.casefold().split()).rstrip(".!?") == " ".join(transcript.casefold().split()).rstrip(".!?")):
                        result = command_result
                        local_complete = False
                        await websocket.send_json({"type":"command_acknowledgement"})
                    else:
                        result = {"success":False, "response":"No action was executed for this tool request. Use an explicit supported command matching the user's speech."}
                    await session.send_tool_response(function_responses=[{
                        "id":call.id, "name":call.name, "response":result,
                    }])
                content = getattr(response, "server_content", None)
                if content is None:
                    continue
                incoming = getattr(content, "input_transcription", None)
                if incoming:
                    text = getattr(incoming, "text", "") or ""
                    if text and (not transcript or command_processed):
                        reset_input()
                        suppress_audio = False
                        await websocket.send_json({"type": "user_turn_started"})
                    transcript += text
                    if text:
                        await websocket.send_json({"type": "user_transcript", "text": text})
                    if getattr(incoming, "finished", False):
                        await finish_input()
                if getattr(content, "interrupted", False):
                    suppress_audio = False
                    await websocket.send_json({"type": "interrupted"})
                outgoing = getattr(content, "output_transcription", None)
                if not local_complete and outgoing and outgoing.text:
                    await websocket.send_json({"type": "indu_transcript", "text": outgoing.text})
                turn = getattr(content, "model_turn", None)
                if not local_complete and not suppress_audio:
                    for part in (getattr(turn, "parts", None) or []):
                        inline = getattr(part, "inline_data", None)
                        if inline and inline.data and (inline.mime_type or "").startswith("audio/pcm"):
                            await websocket.send_bytes(inline.data)
                if getattr(content, "turn_complete", False):
                    await finish_input()
                    if not local_complete:
                        await websocket.send_json({"type": "turn_complete"})
                    reset_input()
                    suppress_audio = False
            if not received:
                raise RuntimeError("Gemini Live connection ended. Retry voice to reconnect.")

    try:
        tasks = [asyncio.create_task(receive_browser(), name="indu-browser-audio"),
                 asyncio.create_task(receive_gemini(), name="indu-gemini-receiver")]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
