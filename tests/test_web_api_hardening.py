import unittest

try:
    from fastapi.testclient import TestClient
    from pluggy.web.app import app
    HAS_WEB_DEPS = True
except Exception:
    HAS_WEB_DEPS = False


@unittest.skipUnless(HAS_WEB_DEPS, "fastapi/httpx not installed")
class TestWebAPIHardening(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_settings_schema_and_capabilities(self):
        schema = self.client.get("/api/settings/schema")
        self.assertEqual(schema.status_code, 200)
        payload = schema.json()
        self.assertIn("groups", payload)

        caps = self.client.get("/api/system/capabilities")
        self.assertEqual(caps.status_code, 200)
        caps_payload = caps.json()
        self.assertIn("downloadBackends", caps_payload)
        self.assertTrue(isinstance(caps_payload.get("downloadBackends", []), list))

    def test_audit_endpoints(self):
        before = self.client.get("/api/audit")
        self.assertEqual(before.status_code, 200)
        self.assertIn("events", before.json())

        clear = self.client.post("/api/audit/clear")
        self.assertEqual(clear.status_code, 200)
        self.assertTrue(clear.json().get("ok"))

        after = self.client.get("/api/audit")
        self.assertEqual(after.status_code, 200)
        self.assertIn("events", after.json())

    def test_rd_status_endpoint(self):
        status = self.client.get("/api/session/rd/status")
        self.assertEqual(status.status_code, 200)
        payload = status.json()
        self.assertIn("rdConnected", payload)
        self.assertIn("status", payload)


if __name__ == "__main__":
    unittest.main()
