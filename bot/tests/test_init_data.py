from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode

import pytest

from tgshop.security.init_data import (
    InitDataError,
    build_data_check_string,
    compute_hash,
    validate_init_data,
)

from .conftest import BOT_TOKEN, USER_ID, make_init_data


def _reason(init_data: str, **kwargs: object) -> str:
    with pytest.raises(InitDataError) as exc_info:
        validate_init_data(init_data, BOT_TOKEN, **kwargs)  # type: ignore[arg-type]
    return exc_info.value.reason


def test_valid_init_data_is_parsed() -> None:
    data = validate_init_data(make_init_data(start_param="promo"), BOT_TOKEN)
    assert data.user.id == USER_ID
    assert data.user.first_name == "Анна"
    assert data.user.language_code == "ru"
    assert data.start_param == "promo"
    assert data.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


def test_algorithm_matches_telegram_docs_step_by_step() -> None:
    """Re-derive the hash exactly as described in the Bot API docs, independently of our code."""
    fields = {"auth_date": "1700000000", "query_id": "Q", "user": '{"id":1,"first_name":"A"}'}
    check = 'auth_date=1700000000\nquery_id=Q\nuser={"id":1,"first_name":"A"}'
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()

    assert build_data_check_string(fields) == check
    assert compute_hash(fields, BOT_TOKEN) == expected


def test_signature_field_is_part_of_data_check_string() -> None:
    # Bot API 8.0 added an Ed25519 `signature`; only `hash` is excluded from the HMAC input.
    fields = {"auth_date": "1", "signature": "abc", "hash": "ignored"}
    assert build_data_check_string(fields) == "auth_date=1\nsignature=abc"


def test_tampered_user_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data()))
    user = json.loads(fields["user"])
    user["id"] = 1  # try to impersonate someone else
    fields["user"] = json.dumps(user)
    assert _reason(urlencode(fields)) == "bad_signature"


def test_other_bot_token_is_rejected() -> None:
    assert _reason(make_init_data(token="42:another-bot")) == "bad_signature"


def test_missing_hash_is_rejected() -> None:
    fields = dict(parse_qsl(make_init_data()))
    del fields["hash"]
    assert _reason(urlencode(fields)) == "missing_hash"


@pytest.mark.parametrize("raw", ["", "not a query string", "a=1&a=2"])
def test_malformed_input_is_rejected(raw: str) -> None:
    assert _reason(raw) in {"empty", "malformed"}


def test_expired_init_data_is_rejected() -> None:
    old = int(time.time()) - 2 * 24 * 3600
    assert _reason(make_init_data(auth_date=old), max_age=24 * 3600) == "expired"


def test_expiry_check_can_be_disabled() -> None:
    old = int(time.time()) - 30 * 24 * 3600
    assert validate_init_data(make_init_data(auth_date=old), BOT_TOKEN, max_age=None)


def test_future_auth_date_is_rejected() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    future = int((now + timedelta(hours=1)).timestamp())
    assert _reason(make_init_data(auth_date=future), now=now) == "auth_date_in_future"


def test_missing_user_is_rejected() -> None:
    from tgshop.security.init_data import sign_init_data

    raw = sign_init_data({"auth_date": str(int(time.time())), "chat_type": "sender"}, BOT_TOKEN)
    assert _reason(raw) == "missing_user"


def test_malformed_user_json_is_rejected_even_if_signed() -> None:
    from tgshop.security.init_data import sign_init_data

    raw = sign_init_data({"auth_date": str(int(time.time())), "user": "{oops"}, BOT_TOKEN)
    assert _reason(raw) == "malformed_user"


def test_uppercase_hash_is_accepted() -> None:
    fields = dict(parse_qsl(make_init_data()))
    fields["hash"] = fields["hash"].upper()
    assert validate_init_data(urlencode(fields), BOT_TOKEN).user.id == USER_ID
