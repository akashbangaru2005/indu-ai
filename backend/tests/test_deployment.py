"""Deployment configuration and cloud-mode integration regression checks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from backend.deployment import deployment_mode, is_cloud, allowed_hosts, allowed_origins


class DeploymentTests(unittest.TestCase):
    def test_local_is_default_and_retains_development_origins(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(deployment_mode(), "local")
            self.assertFalse(is_cloud())
            self.assertIn("http://localhost:5173", allowed_origins())
            self.assertEqual(allowed_hosts(), ["127.0.0.1", "localhost", "testserver"])

    def test_cloud_allows_render_domain_and_explicit_frontend_without_wildcard(self):
        with patch.dict(os.environ, {"INDU_DEPLOYMENT_MODE":"cloud", "RENDER_EXTERNAL_HOSTNAME":"indu-test.onrender.com", "INDU_ALLOWED_ORIGINS":"https://frontend.example/", "INDU_ALLOWED_HOSTS":"api.example.com"}, clear=True):
            self.assertTrue(is_cloud())
            self.assertEqual(allowed_origins(), ["https://frontend.example", "https://indu-test.onrender.com"])
            self.assertIn("indu-test.onrender.com", allowed_hosts())
            self.assertIn("api.example.com", allowed_hosts())
            self.assertNotIn("frontend.example", allowed_hosts())
            self.assertNotIn("*", allowed_hosts())

    def test_cloud_has_no_implicit_local_browser_origins(self):
        with patch.dict(os.environ, {"INDU_DEPLOYMENT_MODE":"cloud"}, clear=True):
            self.assertEqual(allowed_origins(), [])

    def test_invalid_mode_fails_clearly(self):
        with patch.dict(os.environ, {"INDU_DEPLOYMENT_MODE":"cluod"}, clear=True):
            with self.assertRaisesRegex(ValueError, "local or cloud"):
                deployment_mode()

    def test_cloud_import_and_bridge_with_desktop_imports_blocked(self):
        root = Path(__file__).resolve().parents[2]
        environment = dict(os.environ)
        environment.pop("GEMINI_API_KEY", None)
        with tempfile.TemporaryDirectory(prefix="indu-cloud-regression-") as folder:
            report = Path(folder) / "result.json"
            result = subprocess.run([sys.executable, str(root / "benchmarks/cloud_smoke.py"), "--report", str(report)],
                                    cwd=root, env=environment, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(report.read_text())["status"], "passed")
