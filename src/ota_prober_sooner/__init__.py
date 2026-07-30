"""Probe the original Android JSON check-in endpoint for OTA offers."""

from .protocol import (
    DEFAULT_CHECKIN_URL,
    FOTA_UPDATE_ACTION,
    CheckinReply,
    OtaOffer,
    build_request,
    build_request_29386,
    parse_reply,
    parse_reply_29386,
)

__all__ = [
    "DEFAULT_CHECKIN_URL",
    "FOTA_UPDATE_ACTION",
    "CheckinReply",
    "OtaOffer",
    "build_request",
    "build_request_29386",
    "parse_reply",
    "parse_reply_29386",
]

__version__ = "0.2.0"
