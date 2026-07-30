"""Command-line interface for the read-only OTA probe."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence, TextIO

from .protocol import (
    BRICK_ACTION,
    DEFAULT_CHECKIN_URL,
    ProtocolError,
    build_request,
    build_request_29386,
    parse_reply,
    parse_reply_29386,
)
from .transport import TransportError, post_checkin, post_checkin_29386


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ota-prober-sooner",
        description=(
            "Probe the original Android JSON check-in endpoint for an OTA offer. "
            "The tool never downloads or installs an update."
        ),
    )
    parser.add_argument(
        "--protocol",
        choices=("2008", "29386"),
        default="2008",
        help="wire protocol generation (default: 2008)",
    )
    parser.add_argument("--url", default=DEFAULT_CHECKIN_URL)
    parser.add_argument("--product", default="sooner")
    parser.add_argument("--carrier", default="unknown", help="2008 protocol only")
    parser.add_argument("--build-id", default="engineering")
    parser.add_argument(
        "--build-date", default="Unknown", help="29386 protocol only"
    )
    parser.add_argument(
        "--build-type", default="Unknown", help="29386 protocol only"
    )
    parser.add_argument(
        "--build-user", default="Unknown", help="29386 protocol only"
    )
    parser.add_argument(
        "--build-host", default="Unknown", help="29386 protocol only"
    )
    parser.add_argument("--desired-build", help="2008 protocol only")
    parser.add_argument(
        "--android-id",
        type=_parse_int,
        help="decimal or 0x-prefixed Android ID",
    )
    parser.add_argument(
        "--imei", help="optional; sent verbatim and potentially sensitive"
    )
    parser.add_argument("--provisioning-digest", help="2008 protocol only")
    parser.add_argument(
        "--last-checkin-msec", type=int, help="2008 protocol only"
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request JSON without contacting the endpoint",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable result",
    )
    return parser

def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = make_parser().parse_args(argv)

    try:
        if args.protocol == "29386":
            unsupported = {
                "--android-id": args.android_id,
                "--desired-build": args.desired_build,
                "--provisioning-digest": args.provisioning_digest,
                "--last-checkin-msec": args.last_checkin_msec,
            }
            used_unsupported = [
                name for name, value in unsupported.items() if value is not None
            ]
            if used_unsupported:
                raise ProtocolError(
                    f"protocol 29386 does not support {', '.join(used_unsupported)}"
                )
            request = build_request_29386(
                product=args.product,
                build_id=args.build_id,
                build_date=args.build_date,
                build_type=args.build_type,
                build_user=args.build_user,
                build_host=args.build_host,
                imei=args.imei,
            )
        else:
            request = build_request(
                product=args.product,
                carrier=args.carrier,
                build_id=args.build_id,
                imei=args.imei,
                provisioning_digest=args.provisioning_digest,
                android_id=args.android_id,
                desired_build=args.desired_build,
                last_checkin_msec=args.last_checkin_msec,
            )

        if args.dry_run:
            print(
                json.dumps(request, indent=2, sort_keys=True, ensure_ascii=False),
                file=stdout,
            )
            return 0

        if args.protocol == "29386":
            raw_reply, _ = post_checkin_29386(
                args.url, request, timeout=args.timeout
            )
            reply = parse_reply_29386(raw_reply)
        else:
            raw_reply, _ = post_checkin(args.url, request, timeout=args.timeout)
            reply = parse_reply(raw_reply)

    except (ProtocolError, TransportError) as error:
        print(f"error: {error}", file=stderr)
        return 1

    if args.json:
        result = {
            "stats_ok": reply.stats_ok,
            "ota_offers": [offer.as_dict() for offer in reply.ota_offers],
            "intents": [intent.as_dict() for intent in reply.intents],
            "dangerous_action_present": reply.has_brick_action,
        }
        print(json.dumps(result, indent=2, sort_keys=True), file=stdout)
        return 0

    print(f"check-in accepted: {'yes' if reply.stats_ok else 'no'}", file=stdout)
    if reply.ota_offers:
        for index, offer in enumerate(reply.ota_offers, start=1):
            print(f"OTA offer {index}: {offer.url}", file=stdout)
            if offer.mime_type:
                print(f"  MIME type: {offer.mime_type}", file=stdout)
            for name, value in offer.extras:
                print(f"  {name}: {value}", file=stdout)
    else:
        print("OTA offer: none", file=stdout)
    if reply.has_brick_action:
        print(
            f"warning: server returned {BRICK_ACTION!r}; it was ignored",
            file=stderr,
        )
    other_intents = len(reply.intents) - len(reply.ota_offers)
    if other_intents:
        print(f"other server intents (ignored): {other_intents}", file=stdout)
    return 0


def _parse_int(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected a decimal or 0x-prefixed integer") from error
