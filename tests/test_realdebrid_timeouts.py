import unittest
from unittest.mock import patch, Mock

from pluggy.core.event_bus import EventBus
from pluggy.services.realdebrid_client import RealDebridClient


class _Settings:
    def __init__(self):
        self.data = {
            "rd_client_id": "X245A4XAIBGVM",
            "rd_access_token": "token",
            "rd_refresh_token": "",
            "rd_request_timeout_seconds": 9.0,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def update(self, values):
        self.data.update(values)


class TestRealDebridTimeouts(unittest.TestCase):
    def test_api_request_uses_default_timeout(self):
        client = RealDebridClient(_Settings(), EventBus())
        mock_response = Mock(status_code=200)
        with patch("requests.request", return_value=mock_response) as req:
            client._api_request("GET", "user")
            self.assertTrue(req.called)
            kwargs = req.call_args.kwargs
            self.assertEqual(kwargs.get("timeout"), 9.0)

    def test_api_request_honors_explicit_timeout(self):
        client = RealDebridClient(_Settings(), EventBus())
        mock_response = Mock(status_code=200)
        with patch("requests.request", return_value=mock_response) as req:
            client._api_request("GET", "user", timeout=3.0)
            kwargs = req.call_args.kwargs
            self.assertEqual(kwargs.get("timeout"), 3.0)


if __name__ == "__main__":
    unittest.main()
