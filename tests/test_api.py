import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from jarvis.app import app, settings


class ApiTests(unittest.TestCase):
    def test_dashboard_and_demo_tool_flow(self):
        client = TestClient(app)
        result = client.get("/api/dashboard")
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertTrue(data["demo"])
        self.assertEqual(data["system"]["source"], "host")
        self.assertEqual(len(data["devices"]["data"]), 6)
        response = client.post("/api/chat", json={"message": "Jarvis, turn off Living room lights"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["demo"])
        self.assertEqual(response.json()["tools"][-1]["name"], "toggle_device")

    def test_authentication_guards_data_and_actions(self):
        client = TestClient(app)
        with patch.object(settings, "token", "x" * 32):
            self.assertEqual(client.get("/api/config").status_code, 200)
            self.assertEqual(client.get("/api/dashboard").status_code, 401)
            self.assertEqual(client.post("/api/chat", json={"message": "hello"}).status_code, 401)
            response = client.get("/api/dashboard", headers={"Authorization": "Bearer " + "x" * 32})
            self.assertEqual(response.status_code, 200)

    def test_invalid_chat_and_container_control_errors(self):
        client = TestClient(app)
        self.assertEqual(client.post("/api/chat", json={"message": ""}).status_code, 422)
        result = client.post("/api/containers/demo-jellyfin/action", json={"action": "stop"})
        self.assertEqual(result.status_code, 502)
        self.assertIn("disabled", result.json()["detail"])

    def test_static_assets_and_no_secrets_in_config(self):
        client = TestClient(app)
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/app.js").status_code, 200)
        self.assertNotIn("ha_token", client.get("/api/config").json())
