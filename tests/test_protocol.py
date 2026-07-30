from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from ota_prober_sooner.cli import main
from ota_prober_sooner.protocol import (
    BRICK_ACTION,
    FOTA_UPDATE_ACTION,
    ProtocolError,
    build_request,
    parse_reply,
)
from ota_prober_sooner.transport import CONTENT_TYPE, post_checkin


class ProtocolTest(unittest.TestCase):
    def test_build_request_matches_old_field_names(self) -> None:
        self.assertEqual(
            build_request(
                product="sooner",
                carrier="T-Mobile",
                build_id="TC4-RC29",
                imei="1234",
                provisioning_digest="digest-value",
                android_id=0xCAFE,
                desired_build="TC5",
                last_checkin_msec=123,
            ),
            {
                "imei": "1234",
                "digest": "digest-value",
                "id": 0xCAFE,
                "desired_build": "TC5",
                "checkin": {
                    "build": {
                        "product": "sooner",
                        "carrier": "T-Mobile",
                        "id": "TC4-RC29",
                    },
                    "last_checkin_msec": 123,
                },
            },
        )

    def test_parse_ota_and_never_execute_other_intents(self) -> None:
        reply = parse_reply(
            {
                "stats_ok": True,
                "intent": [
                    {
                        "action": FOTA_UPDATE_ACTION,
                        "data_uri": "http://example.test/update.zip",
                        "mime_type": "application/zip",
                        "extra": [{"name": "sha1", "value": "abc"}],
                    },
                    {"action": BRICK_ACTION},
                ],
            }
        )
        self.assertTrue(reply.has_brick_action)
        self.assertEqual(len(reply.ota_offers), 1)
        self.assertEqual(reply.ota_offers[0].url, "http://example.test/update.zip")
        self.assertEqual(reply.ota_offers[0].extras, (("sha1", "abc"),))

    def test_reply_requires_stats_ok(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_reply({"intent": []})


class _FakeResponse:
    status = 200
    reason = "OK"

    def read(self, amount: int) -> bytes:
        return json.dumps(
            {
                "stats_ok": True,
                "intent": [
                    {
                        "action": FOTA_UPDATE_ACTION,
                        "data_uri": "http://example.test/sooner-ota.zip",
                    }
                ],
            }
        ).encode()


class _FakeConnection:
    instance: "_FakeConnection"

    def __init__(self, host: str, port: int | None, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.method = ""
        self.target = ""
        self.body = b""
        self.headers: dict[str, str] = {}
        type(self).instance = self

    def request(
        self, method: str, target: str, *, body: bytes, headers: dict[str, str]
    ) -> None:
        self.method = method
        self.target = target
        self.body = body
        self.headers = headers

    def getresponse(self) -> _FakeResponse:
        return _FakeResponse()

    def close(self) -> None:
        pass


class TransportTest(unittest.TestCase):
    def test_posts_old_content_type_and_parses_offer(self) -> None:
        with patch(
            "ota_prober_sooner.transport.http.client.HTTPConnection",
            _FakeConnection,
        ):
            request = build_request(
                product="sooner", carrier="unknown", build_id="engineering"
            )
            reply, sent_body = post_checkin(
                "http://android.clients.google.com/checkin", request
            )

        connection = _FakeConnection.instance
        self.assertEqual(connection.host, "android.clients.google.com")
        self.assertEqual(connection.method, "POST")
        self.assertEqual(connection.target, "/checkin")
        self.assertEqual(connection.headers["Content-Type"], CONTENT_TYPE)
        self.assertEqual(connection.body, sent_body)
        self.assertEqual(json.loads(sent_body), request)
        self.assertEqual(
            parse_reply(reply).ota_offers[0].url,
            "http://example.test/sooner-ota.zip",
        )

    def test_cli_dry_run_does_not_use_network(self) -> None:
        stdout = io.StringIO()
        result = main(
            ["--dry-run", "--build-id", "TC4-RC29"],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(result, 0)
        self.assertEqual(
            json.loads(stdout.getvalue())["checkin"]["build"]["id"], "TC4-RC29"
        )


if __name__ == "__main__":
    unittest.main()
