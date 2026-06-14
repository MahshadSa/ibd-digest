import email.message
import http.client
import json
import unittest
import urllib.error
from unittest import mock

from lineage import openalex
from lineage.resolve import FetchFailed, WorkNotFound


class _FakeResp:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", email.message.Message(), None)


@mock.patch("lineage.openalex.time.sleep")
@mock.patch("urllib.request.urlopen")
class TestHttpFetchBoundary(unittest.TestCase):
    def test_retries_then_succeeds(self, urlopen, _sleep):
        urlopen.side_effect = [
            http.client.RemoteDisconnected("drop"),
            http.client.RemoteDisconnected("drop"),
            _FakeResp({"id": "https://openalex.org/W1"}),
        ]
        result = openalex.http_fetch("W1")
        self.assertEqual(result["id"], "https://openalex.org/W1")
        self.assertEqual(urlopen.call_count, 3)

    def test_404_is_work_not_found(self, urlopen, _sleep):
        urlopen.side_effect = _http_error(404)
        with self.assertRaises(WorkNotFound):
            openalex.http_fetch("W1")
        self.assertEqual(urlopen.call_count, 1)

    def test_persistent_transient_becomes_fetch_failed(self, urlopen, _sleep):
        urlopen.side_effect = http.client.RemoteDisconnected("drop")
        with self.assertRaises(FetchFailed):
            openalex.http_fetch("W1")
        self.assertEqual(urlopen.call_count, openalex.MAX_RETRIES + 1)

    def test_persistent_5xx_becomes_fetch_failed(self, urlopen, _sleep):
        urlopen.side_effect = _http_error(503)
        with self.assertRaises(FetchFailed):
            openalex.http_fetch("W1")
        self.assertEqual(urlopen.call_count, openalex.MAX_RETRIES + 1)

    def test_403_propagates(self, urlopen, _sleep):
        urlopen.side_effect = _http_error(403)
        with self.assertRaises(urllib.error.HTTPError):
            openalex.http_fetch("W1")
        self.assertEqual(urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
