"""Validation of Telegram Mini App ``initData``.

Implements the algorithm from https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    secret_key       = HMAC_SHA256(key="WebAppData", msg=<bot_token>)
    data_check_string = "\\n".join(sorted(f"{k}={v}" for every field except "hash"))
    valid            = hex(HMAC_SHA256(key=secret_key, msg=data_check_string)) == hash

On top of the signature we reject stale payloads (``auth_date`` older than ``max_age``) to limit
replay of leaked init data, and payloads without a ``user`` (the shop needs a customer).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode

_CLOCK_SKEW = timedelta(seconds=60)


class InitDataError(Exception):
    """Raised when init data is missing, malformed, forged or expired."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class WebAppUser:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @classmethod
    def from_json(cls, raw: str) -> WebAppUser:
        try:
            data: Any = json.loads(raw)
            return cls(
                id=int(data["id"]),
                first_name=str(data.get("first_name", "")),
                last_name=data.get("last_name"),
                username=data.get("username"),
                language_code=data.get("language_code"),
                is_premium=bool(data.get("is_premium", False)),
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise InitDataError("malformed_user") from exc


@dataclass(frozen=True, slots=True)
class WebAppInitData:
    user: WebAppUser
    auth_date: datetime
    query_id: str | None
    start_param: str | None
    fields: Mapping[str, str]


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def build_data_check_string(fields: Mapping[str, str]) -> str:
    return "\n".join(f"{key}={fields[key]}" for key in sorted(fields) if key != "hash")


def compute_hash(fields: Mapping[str, str], bot_token: str) -> str:
    check_string = build_data_check_string(fields)
    return hmac.new(_secret_key(bot_token), check_string.encode(), hashlib.sha256).hexdigest()


def sign_init_data(fields: Mapping[str, str], bot_token: str) -> str:
    """Produce a signed init data query string (used by tests and local tooling)."""
    payload = {key: value for key, value in fields.items() if key != "hash"}
    payload["hash"] = compute_hash(payload, bot_token)
    return urlencode(payload)


def _parse(init_data: str) -> dict[str, str]:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise InitDataError("malformed") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:  # a duplicated key is never produced by Telegram
            raise InitDataError("malformed")
        fields[key] = value
    return fields


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age: int | None = 24 * 60 * 60,
    now: datetime | None = None,
) -> WebAppInitData:
    if not init_data:
        raise InitDataError("empty")
    fields = _parse(init_data)

    received_hash = fields.get("hash")
    if not received_hash:
        raise InitDataError("missing_hash")
    expected_hash = compute_hash(fields, bot_token)
    if not hmac.compare_digest(expected_hash, received_hash.lower()):
        raise InitDataError("bad_signature")

    try:
        auth_date = datetime.fromtimestamp(int(fields["auth_date"]), tz=UTC)
    except (KeyError, ValueError, OverflowError, OSError) as exc:
        raise InitDataError("bad_auth_date") from exc

    current = now or datetime.now(UTC)
    if auth_date - current > _CLOCK_SKEW:
        raise InitDataError("auth_date_in_future")
    if max_age is not None and current - auth_date > timedelta(seconds=max_age):
        raise InitDataError("expired")

    raw_user = fields.get("user")
    if not raw_user:
        raise InitDataError("missing_user")

    return WebAppInitData(
        user=WebAppUser.from_json(raw_user),
        auth_date=auth_date,
        query_id=fields.get("query_id"),
        start_param=fields.get("start_param"),
        fields=fields,
    )
