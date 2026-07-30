from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from ota_prober_sooner.cli import main
from ota_prober_sooner.protocol import (
    BRICK_ACTION,
    DEFAULT_CHECKIN_URL,
    DEFAULT_CHECKIN_URL_29386,
    FOTA_UPDATE_ACTION,
    ProtocolError,
    build_request,
    build_request_29386,
    parse_reply,
    parse_reply_29386,
)
from ota_prober_sooner.transport import (
    CONTENT_TYPE,
    CONTENT_TYPE_29386,
    FORM_CHARSET_29386,
    post_checkin,
    post_checkin_29386,
)


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

    def test_build_29386_request_matches_transitional_field_names(self) -> None:
        self.assertEqual(
            build_request_29386(
                product="sooner",
                build_id="htc-29386.0.9.0.0",
                build_date="三  8月 29 18:03:11 CST 2007",
                build_type="release",
                build_user="root",
                build_host="sfchiou-desktop",
            ),
            {
                "imei": "Unknown",
                "buildinfo": {
                    "buildinfo.id": "htc-29386.0.9.0.0",
                    "buildinfo.date": "三  8月 29 18:03:11 CST 2007",
                    "buildinfo.type": "release",
                    "buildinfo.product": "sooner",
                    "buildinfo.user": "root",
                    "buildinfo.host": "sfchiou-desktop",
                },
                "stats": [],
            },
        )

    def test_parse_29386_ota_and_ignore_brick_action(self) -> None:
        reply = parse_reply_29386(
            {
                "statsok": True,
                "intents": [
                    {
                        "action": FOTA_UPDATE_ACTION,
                        "data": "http://example.test/29386.zip",
                        "extras": {"sha1": "abc"},
                    },
                    {"action": BRICK_ACTION},
                ],
            }
        )
        self.assertTrue(reply.has_brick_action)
        self.assertEqual(reply.ota_offers[0].url, "http://example.test/29386.zip")
        self.assertEqual(reply.ota_offers[0].extras, (("sha1", "abc"),))

    def test_29386_reply_requires_plural_intents(self) -> None:
        with self.assertRaises(ProtocolError):
            parse_reply_29386({"statsok": True})


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

    def test_posts_29386_form_wrapped_payload(self) -> None:
        with patch(
            "ota_prober_sooner.transport.http.client.HTTPConnection",
            _FakeConnection,
        ):
            request = build_request_29386(
                product="sooner",
                build_id="htc-29386.0.9.0.0",
                build_date="三  8月 29 18:03:11 CST 2007",
                build_type="release",
                build_user="root",
                build_host="sfchiou-desktop",
            )
            _, sent_body = post_checkin_29386(
                "http://android.clients.google.com/checkin", request
            )

        connection = _FakeConnection.instance
        self.assertEqual(connection.headers["Content-Type"], CONTENT_TYPE_29386)
        form = parse_qs(
            sent_body.decode("ascii"),
            encoding=FORM_CHARSET_29386,
            keep_blank_values=True,
        )
        payload = json.loads(form["payload"][0])
        self.assertEqual(payload["buildinfo"]["buildinfo.id"], "htc-29386.0.9.0.0")
        self.assertEqual(
            payload["buildinfo"]["buildinfo.date"],
            "?  8? 29 18:03:11 CST 2007",
        )

    def test_cli_29386_dry_run_uses_supplied_build(self) -> None:
        stdout = io.StringIO()
        result = main(
            [
                "--protocol",
                "29386",
                "--dry-run",
                "--build-id",
                "htc-29386.0.9.0.0",
                "--build-date",
                "三  8月 29 18:03:11 CST 2007",
                "--build-type",
                "release",
                "--build-user",
                "root",
                "--build-host",
                "sfchiou-desktop",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["buildinfo"]["buildinfo.id"], "htc-29386.0.9.0.0"
        )

    def test_cli_uses_protocol_specific_default_urls(self) -> None:
        with patch(
            "ota_prober_sooner.cli.post_checkin",
            return_value=({"stats_ok": True, "intent": []}, b""),
        ) as post_2008:
            self.assertEqual(
                main(["--json"], stdout=io.StringIO(), stderr=io.StringIO()),
                0,
            )
        self.assertEqual(post_2008.call_args.args[0], DEFAULT_CHECKIN_URL)

        with patch(
            "ota_prober_sooner.cli.post_checkin_29386",
            return_value=({"statsok": True, "intents": []}, b""),
        ) as post_29386:
            self.assertEqual(
                main(
                    ["--protocol", "29386", "--json"],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                ),
                0,
            )
        self.assertEqual(
            post_29386.call_args.args[0], DEFAULT_CHECKIN_URL_29386
        )


if __name__ == "__main__":
    unittest.main()
