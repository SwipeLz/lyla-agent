from __future__ import annotations

import re

import pytest

from app.auth.passwords import hash_password, verify_password


def test_hash_password_returns_salt_colon_hash_hex():
    stored = hash_password("admin")
    assert ":" in stored
    salt_hex, hash_hex = stored.split(":", 1)
    assert re.fullmatch(r"[0-9a-f]+", salt_hex)
    assert re.fullmatch(r"[0-9a-f]+", hash_hex)
    assert len(salt_hex) == 64
    assert len(hash_hex) == 128


def test_hash_password_uses_random_salt():
    a = hash_password("admin")
    b = hash_password("admin")
    assert a != b


def test_verify_password_returns_true_for_correct_pair():
    stored = hash_password("admin")
    assert verify_password("admin", stored) is True


def test_verify_password_returns_false_for_wrong_password():
    stored = hash_password("admin")
    assert verify_password("not-admin", stored) is False


def test_verify_password_fail_closed_on_empty_stored():
    assert verify_password("admin", "") is False


def test_verify_password_returns_false_when_no_colon():
    assert verify_password("admin", "garbage") is False


def test_verify_password_returns_false_on_bad_hex():
    assert verify_password("admin", "zz:zz") is False


def test_hash_password_rejects_empty_plaintext():
    with pytest.raises(ValueError):
        hash_password("")
