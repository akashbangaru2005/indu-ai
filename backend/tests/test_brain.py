import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import httpx
from backend.brain.llm import BrainError, InduBrain


def client_with_reply(text="Answer"):
    client = Mock()
    client.models.generate_content.return_value = NS(text=text)
    return client


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("Provider details must not leak a private key")


class BrainTests(unittest.TestCase):
    def test_zero_history_does_not_retain_messages(self):
        brain = InduBrain(max_history=0, client=client_with_reply())
        brain.chat("Hello")
        self.assertEqual(brain.history, [])

    def test_history_keeps_complete_gemini_turns_under_odd_limit(self):
        client = client_with_reply()
        brain = InduBrain(max_history=3, client=client)
        brain.chat("one")
        brain.chat("two")
        self.assertEqual([m["role"] for m in brain.history], ["user", "model"])
        self.assertEqual(brain.history[0]["parts"][0]["text"], "two")
        payload = client.models.generate_content.call_args.kwargs
        self.assertEqual(len(payload["contents"]), 3)
        self.assertIn("system_instruction", payload["config"])
        self.assertTrue(payload["model"].startswith("gemini-"))

    def test_upstream_failures_have_http_status_and_do_not_change_history(self):
        for error, code in [(httpx.ConnectError("offline"), 503), (httpx.ReadTimeout("timeout"), 504),
                            (ProviderError(403), 503), (ProviderError(429), 429),
                            (ProviderError(404), 503), (ProviderError(500), 502)]:
            client = client_with_reply()
            client.models.generate_content.side_effect = error
            with self.subTest(code=code):
                brain = InduBrain(client=client)
                with self.assertRaises(BrainError) as raised:
                    brain.chat("Hello")
                self.assertEqual(raised.exception.status_code, code)
                self.assertNotIn("private key", str(raised.exception))
                self.assertEqual(brain.history, [])

    def test_malformed_and_empty_model_responses_fail(self):
        for value in [None, " ", 5]:
            with self.subTest(value=value), self.assertRaises(BrainError):
                InduBrain(client=client_with_reply(value)).chat("Hello")

    def test_concurrent_chat_payloads_preserve_turn_order(self):
        client = client_with_reply()
        brain = InduBrain(client=client)
        lengths = []
        def respond(**kwargs):
            contents = kwargs["contents"]
            lengths.append(len(contents))
            return NS(text=contents[-1]["parts"][0]["text"])
        client.models.generate_content.side_effect = respond
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(brain.chat, ["one", "two", "three", "four"]))
        self.assertEqual(lengths, [1, 3, 5, 7])
        brain.clear_history()
        self.assertEqual(brain.history, [])

    def test_health_is_local_configuration_only_and_does_not_make_model_calls(self):
        client = client_with_reply()
        status = InduBrain(client=client).readiness()
        self.assertTrue(status["configured"])
        self.assertFalse(status["connection_verified"])
        self.assertEqual(status["provider"], "gemini")
        client.models.generate_content.assert_not_called()

    def test_missing_key_has_actionable_error_without_network_calls(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY":""}):
            brain = InduBrain()
            self.assertFalse(brain.readiness()["configured"])
            with self.assertRaisesRegex(BrainError, "GEMINI_API_KEY"):
                brain.chat("Hello")
