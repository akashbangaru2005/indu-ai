import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from backend.voice.live import bridge_voice


class Browser:
    def __init__(self):
        self.input = asyncio.Queue()
        self.messages = []
        self.turns = asyncio.Queue()
    async def receive(self):
        return await self.input.get()
    async def send_json(self, data):
        self.messages.append(data)
        if data["type"] == "turn_complete":
            await self.turns.put(True)
    async def send_bytes(self, data):
        self.messages.append(data)


class Session:
    def __init__(self):
        self.batches = asyncio.Queue()
        self.send_realtime_input = AsyncMock()
        self.receive_calls = 0
    async def receive(self):
        self.receive_calls += 1
        batch = await self.batches.get()
        if isinstance(batch, Exception):
            raise batch
        for content in batch:
            yield NS(server_content=content)


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def run_session(self, batches):
        socket, session, execute = Browser(), Session(), AsyncMock()
        for batch in batches:
            await session.batches.put(batch)
        task = asyncio.create_task(bridge_voice(socket, session, execute))
        for _ in batches:
            await asyncio.wait_for(socket.turns.get(), 2)
        await socket.input.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(task, 2)
        return socket, session, execute

    async def test_fragmented_command_is_executed_once_after_completion(self):
        socket, _, execute = await self.run_session([[
            NS(input_transcription=NS(text="send a message to deva Hello ", finished=False)),
            NS(input_transcription=NS(text="You", finished=False)),
            NS(input_transcription=NS(text="Tube", finished=True)),
            NS(turn_complete=True),
        ]])
        execute.assert_awaited_once_with("send a message to deva Hello YouTube", socket)

    async def test_receive_continues_across_turns_and_repeated_commands_work(self):
        _, _, execute = await self.run_session([
            [NS(input_transcription=NS(text="open youtube")), NS(turn_complete=True)],
            [NS(input_transcription=NS(text="open youtube")), NS(turn_complete=True)],
        ])
        self.assertEqual(execute.await_count, 2)

    async def test_disconnect_cancels_upstream_receiver(self):
        socket, session = Browser(), Session()
        await socket.input.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(bridge_voice(socket, session, AsyncMock()), 2)

    async def test_invalid_audio_and_json_do_not_crash_receiver(self):
        socket, session = Browser(), Session()
        for data in [
            {"bytes": b"x"}, {"text": "[]"}, {"text": "bad json"},
            {"bytes": b"\x00\x00"}, {"text": '{"type":"stop"}'},
        ]:
            await socket.input.put({"type": "websocket.receive", **data})
        await asyncio.wait_for(bridge_voice(socket, session, AsyncMock()), 2)
        session.send_realtime_input.assert_awaited_once()
        self.assertEqual(socket.messages[0]["type"], "warning")

    async def test_upstream_error_is_propagated_and_browser_task_cleaned_up(self):
        socket, session = Browser(), Session()
        await session.batches.put(RuntimeError("upstream failed"))
        with self.assertRaisesRegex(RuntimeError, "upstream failed"):
            await asyncio.wait_for(bridge_voice(socket, session, AsyncMock()), 2)

    async def test_five_audio_turns_share_session_until_explicit_stop(self):
        socket, session, execute = Browser(), Session(), AsyncMock()
        task = asyncio.create_task(bridge_voice(socket, session, execute))
        for index in range(5):
            await socket.input.put({"type":"websocket.receive", "bytes": b"\x00\x00"})
            audio = NS(data=bytes([index, 0]), mime_type="audio/pcm;rate=24000")
            await session.batches.put([
                NS(input_transcription=NS(text=f"Question {index}", finished=True)),
                NS(output_transcription=NS(text=f"Answer {index}"), model_turn=NS(parts=[NS(inline_data=audio)])),
                NS(turn_complete=True),
            ])
            await asyncio.wait_for(socket.turns.get(), 2)
            self.assertFalse(task.done(), "Turn completion ended the conversation")
        await socket.input.put({"type":"websocket.receive", "text":'{"type":"stop"}'})
        await asyncio.wait_for(task, 2)
        self.assertEqual(execute.await_count, 5)
        self.assertEqual(session.send_realtime_input.await_count, 5)
        self.assertEqual(len([message for message in socket.messages if isinstance(message, bytes)]), 5)
        self.assertGreaterEqual(session.receive_calls, 5)
        self.assertFalse(any(item.get_name() in {"indu-browser-audio", "indu-gemini-receiver"}
                             for item in asyncio.all_tasks() if not item.done()))

    async def test_local_commands_do_not_end_session_or_execute_twice(self):
        socket, session = Browser(), Session()
        async def execute(command, websocket):
            await websocket.send_json({"type":"command_result", "response":command})
        execute = AsyncMock(side_effect=execute)
        task = asyncio.create_task(bridge_voice(socket, session, execute, lambda text: text.startswith("open ")))
        for command in ["open youtube", "open instagram", "open youtube"]:
            await session.batches.put([
                NS(input_transcription=NS(text=command, finished=True)),
                NS(output_transcription=NS(text="Unverified model action")),
                NS(turn_complete=True),
            ])
            await asyncio.wait_for(socket.turns.get(), 2)
            self.assertFalse(task.done())
        await socket.input.put({"type":"websocket.disconnect"})
        await asyncio.wait_for(task, 2)
        self.assertEqual(execute.await_count, 3)
        self.assertFalse(any(isinstance(message, dict) and message.get("text") == "Unverified model action" for message in socket.messages))

    async def test_stop_speaking_preserves_microphone_forwarding_and_next_turn(self):
        socket, session = Browser(), Session()
        task = asyncio.create_task(bridge_voice(socket, session, AsyncMock()))
        await socket.input.put({"type":"websocket.receive", "text":'{"type":"stop_speaking"}'})
        await socket.input.put({"type":"websocket.receive", "bytes":b"\x00\x00"})
        await socket.input.put({"type":"websocket.receive", "text":'{"type":"ping"}'})
        while not any(isinstance(message, dict) and message.get("type") == "pong" for message in socket.messages):
            await asyncio.sleep(0)
        audio = NS(data=b"\x01\x00", mime_type="audio/pcm;rate=24000")
        await session.batches.put([NS(model_turn=NS(parts=[NS(inline_data=audio)])), NS(turn_complete=True)])
        await asyncio.wait_for(socket.turns.get(), 2)
        self.assertNotIn(b"\x01\x00", socket.messages)
        await session.batches.put([NS(input_transcription=NS(text="Next question", finished=True)),
                                   NS(model_turn=NS(parts=[NS(inline_data=audio)])), NS(turn_complete=True)])
        await asyncio.wait_for(socket.turns.get(), 2)
        self.assertIn(b"\x01\x00", socket.messages)
        self.assertFalse(task.done())
        await socket.input.put({"type":"websocket.disconnect"})
        await asyncio.wait_for(task, 2)
        session.send_realtime_input.assert_awaited_once()
