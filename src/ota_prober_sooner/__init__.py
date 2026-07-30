"""Probe the original Android JSON check-in endpoint for OTA offers."""

from .protocol import (
    DEFAULT_CHECKIN_URL,
    FOTA_UPDATE_ACTION,
    CheckinReply,
    OtaOffer,
    build_request,
    parse_reply,
)

__all__ = [
    "DEFAULT_CHECKIN_URL",
    "FOTA_UPDATE_ACTION",
    "CheckinReply",
    "OtaOffer",
    "build_request",
    "parse_reply",
]

__version__ = "0.1.0"

