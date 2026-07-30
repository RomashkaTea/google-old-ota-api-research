"""The JSON protocol used by Android's original CheckinService.

This module deliberately models only the read-only portion needed to discover
OTA offers. It never interprets an intent as an instruction to execute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DEFAULT_CHECKIN_URL = "http://android.clients.google.com/checkin"
FOTA_UPDATE_ACTION = "android.server.checkin.FOTA_UPDATE"
BRICK_ACTION = "SHES_A_BRICK_HOUSE"


class ProtocolError(ValueError):
    """Raised when a check-in response does not match the old JSON protocol."""


@dataclass(frozen=True)
class Intent:
    action: str
    data_uri: str | None = None
    mime_type: str | None = None
    extras: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"action": self.action}
        if self.data_uri is not None:
            result["data_uri"] = self.data_uri
        if self.mime_type is not None:
            result["mime_type"] = self.mime_type
        if self.extras:
            result["extra"] = [
                {"name": name, "value": value} for name, value in self.extras
            ]
        return result


@dataclass(frozen=True)
class OtaOffer:
    url: str
    mime_type: str | None = None
    extras: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"url": self.url}
        if self.mime_type is not None:
            result["mime_type"] = self.mime_type
        if self.extras:
            result["extras"] = dict(self.extras)
        return result


@dataclass(frozen=True)
class CheckinReply:
    stats_ok: bool
    intents: tuple[Intent, ...]
    raw: Mapping[str, Any]

    @property
    def ota_offers(self) -> tuple[OtaOffer, ...]:
        return tuple(
            OtaOffer(
                url=intent.data_uri,
                mime_type=intent.mime_type,
                extras=intent.extras,
            )
            for intent in self.intents
            if intent.action == FOTA_UPDATE_ACTION and intent.data_uri is not None
        )

    @property
    def has_brick_action(self) -> bool:
        return any(intent.action == BRICK_ACTION for intent in self.intents)


def build_request(
    *,
    product: str,
    carrier: str,
    build_id: str,
    imei: str | None = None,
    provisioning_digest: str | None = None,
    android_id: int | None = None,
    desired_build: str | None = None,
    last_checkin_msec: int | None = None,
) -> dict[str, Any]:
    """Construct the request emitted by the old CheckinProtocol.formatRequest."""

    if not product:
        raise ProtocolError("product must not be empty")
    if not carrier:
        raise ProtocolError("carrier must not be empty")
    if not build_id:
        raise ProtocolError("build_id must not be empty")
    if android_id is not None and android_id < 0:
        raise ProtocolError("android_id must be non-negative")
    if last_checkin_msec is not None and last_checkin_msec < 0:
        raise ProtocolError("last_checkin_msec must be non-negative")

    checkin: dict[str, Any] = {
        "build": {
            "product": product,
            "carrier": carrier,
            "id": build_id,
        }
    }
    if last_checkin_msec is not None:
        checkin["last_checkin_msec"] = last_checkin_msec

    request: dict[str, Any] = {"checkin": checkin}
    if imei is not None:
        request["imei"] = imei
    if provisioning_digest is not None:
        request["digest"] = provisioning_digest
    if android_id is not None:
        request["id"] = android_id
    if desired_build is not None:
        request["desired_build"] = desired_build
    return request


def build_request_29386(
    *,
    product: str,
    build_id: str,
    build_date: str,
    build_type: str,
    build_user: str,
    build_host: str,
    imei: str | None = None,
) -> dict[str, Any]:
    """Construct the payload JSON emitted by build 29386's CheckinRequest."""

    fields = {
        "product": product,
        "build_id": build_id,
        "build_date": build_date,
        "build_type": build_type,
        "build_user": build_user,
        "build_host": build_host,
    }
    for name, value in fields.items():
        if not value:
            raise ProtocolError(f"{name} must not be empty")

    # StatisticsService.getImei() used getProperty(), whose fallback was
    # literally "Unknown". The field was always present in this protocol.
    request_imei = imei if imei is not None else "Unknown"
    return {
        "imei": request_imei,
        "buildinfo": {
            "buildinfo.id": build_id,
            "buildinfo.date": build_date,
            "buildinfo.type": build_type,
            "buildinfo.product": product,
            "buildinfo.user": build_user,
            "buildinfo.host": build_host,
        },
        # A real device appended accumulated tag/value/date statistics here.
        # A probe sends none: OTA selection only needs the build identity.
        "stats": [],
    }


def parse_reply(value: object) -> CheckinReply:
    """Parse a JSON-decoded check-in response without acting on its intents."""

    if not isinstance(value, Mapping):
        raise ProtocolError("reply must be a JSON object")

    stats_ok = value.get("stats_ok")
    if not isinstance(stats_ok, bool):
        raise ProtocolError("reply is missing boolean field 'stats_ok'")

    raw_intents = value.get("intent", [])
    if not isinstance(raw_intents, list):
        raise ProtocolError("reply field 'intent' must be an array")

    intents: list[Intent] = []
    for index, item in enumerate(raw_intents):
        if not isinstance(item, Mapping):
            raise ProtocolError(f"intent[{index}] must be an object")
        action = item.get("action")
        if not isinstance(action, str) or not action:
            raise ProtocolError(f"intent[{index}].action must be a non-empty string")
        data_uri = _optional_string(item, "data_uri", index)
        mime_type = _optional_string(item, "mime_type", index)

        raw_extras = item.get("extra", [])
        if not isinstance(raw_extras, list):
            raise ProtocolError(f"intent[{index}].extra must be an array")
        extras: list[tuple[str, str]] = []
        for extra_index, extra in enumerate(raw_extras):
            if not isinstance(extra, Mapping):
                raise ProtocolError(
                    f"intent[{index}].extra[{extra_index}] must be an object"
                )
            name = extra.get("name")
            extra_value = extra.get("value")
            if not isinstance(name, str) or not isinstance(extra_value, str):
                raise ProtocolError(
                    f"intent[{index}].extra[{extra_index}] needs string name/value"
                )
            extras.append((name, extra_value))

        intents.append(
            Intent(
                action=action,
                data_uri=data_uri,
                mime_type=mime_type,
                extras=tuple(extras),
            )
        )

    return CheckinReply(stats_ok=stats_ok, intents=tuple(intents), raw=value)


def parse_reply_29386(value: object) -> CheckinReply:
    """Parse build 29386's transitional statsok/intents response schema."""

    if not isinstance(value, Mapping):
        raise ProtocolError("reply must be a JSON object")

    stats_ok = value.get("statsok")
    if not isinstance(stats_ok, bool):
        raise ProtocolError("reply is missing boolean field 'statsok'")

    raw_intents = value.get("intents")
    if not isinstance(raw_intents, list):
        raise ProtocolError("reply field 'intents' must be an array")

    intents: list[Intent] = []
    for index, item in enumerate(raw_intents):
        if not isinstance(item, Mapping):
            raise ProtocolError(f"intents[{index}] must be an object")
        action = item.get("action")
        if not isinstance(action, str) or not action:
            raise ProtocolError(
                f"intents[{index}].action must be a non-empty string"
            )
        data_uri = _optional_string(item, "data", index, collection="intents")

        raw_extras = item.get("extras", {})
        if raw_extras is None:
            raw_extras = {}
        if not isinstance(raw_extras, Mapping):
            raise ProtocolError(f"intents[{index}].extras must be an object")
        extras: list[tuple[str, str]] = []
        for name, extra_value in raw_extras.items():
            if not isinstance(name, str) or not isinstance(extra_value, str):
                raise ProtocolError(
                    f"intents[{index}].extras needs string names and values"
                )
            extras.append((name, extra_value))

        intents.append(
            Intent(
                action=action,
                data_uri=data_uri,
                extras=tuple(extras),
            )
        )

    return CheckinReply(stats_ok=stats_ok, intents=tuple(intents), raw=value)


def _optional_string(
    item: Mapping[str, object],
    field: str,
    intent_index: int,
    *,
    collection: str = "intent",
) -> str | None:
    result = item.get(field)
    if result is not None and not isinstance(result, str):
        raise ProtocolError(
            f"{collection}[{intent_index}].{field} must be a string"
        )
    return result
