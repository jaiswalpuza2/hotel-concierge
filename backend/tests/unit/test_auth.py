"""Unit tests for JWT creation, decoding, and the password utilities."""
from __future__ import annotations

import uuid

import pytest
from app.auth.jwt import (
    _revoked_jtis,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    revoke_refresh_token,
)
from app.auth.password import hash_password, verify_password
from app.exceptions import AuthError

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_is_not_plain(self) -> None:
        hashed = hash_password("MySecret123")
        assert hashed != "MySecret123"
        assert len(hashed) > 20

    def test_verify_correct_password(self) -> None:
        hashed = hash_password("Nepal2081!")
        assert verify_password("Nepal2081!", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("Nepal2081!")
        assert verify_password("WrongPassword", hashed) is False

    def test_two_hashes_of_same_password_differ(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        # bcrypt uses random salts — same input produces different hashes
        assert h1 != h2

    def test_verify_empty_password(self) -> None:
        hashed = hash_password("Nepal2081!")
        assert verify_password("", hashed) is False


# ---------------------------------------------------------------------------
# JWT creation and decoding
# ---------------------------------------------------------------------------


class TestAccessToken:
    def test_create_and_decode_access_token(self) -> None:
        user_id = uuid.uuid4()
        token, expires_in = create_access_token(user_id, "admin")
        assert isinstance(token, str)
        assert expires_in > 0

        payload = decode_access_token(token)
        assert payload.sub == str(user_id)
        assert payload.role == "admin"
        assert payload.type == "access"
        assert payload.jti != ""

    def test_decode_with_wrong_type_raises(self) -> None:
        """Passing a refresh token to decode_access_token must fail."""
        user_id = uuid.uuid4()
        refresh_token, _ = create_refresh_token(user_id, "staff")
        with pytest.raises(AuthError) as exc:
            decode_access_token(refresh_token)
        assert exc.value.code == "wrong_token_type"

    def test_decode_tampered_token_raises(self) -> None:
        user_id = uuid.uuid4()
        token, _ = create_access_token(user_id, "admin")
        # Tamper with the first character of the signature. The last base64url
        # character carries padding bits, so flipping it can decode to the same
        # bytes and leave the token legitimately valid.
        header, payload, sig = token.split(".")
        bad_sig = ("X" if sig[0] != "X" else "Y") + sig[1:]
        bad_token = f"{header}.{payload}.{bad_sig}"
        with pytest.raises(AuthError) as exc:
            decode_access_token(bad_token)
        assert exc.value.code == "token_invalid"

    def test_decode_empty_string_raises(self) -> None:
        with pytest.raises(AuthError) as exc:
            decode_access_token("")
        assert exc.value.code in ("token_invalid", "token_expired")

    def test_staff_role_preserved(self) -> None:
        token, _ = create_access_token(uuid.uuid4(), "staff")
        payload = decode_access_token(token)
        assert payload.role == "staff"


class TestRefreshToken:
    def test_create_and_decode_refresh_token(self) -> None:
        user_id = uuid.uuid4()
        token, jti = create_refresh_token(user_id, "admin")
        assert isinstance(token, str)
        assert isinstance(jti, str)

        payload = decode_refresh_token(token)
        assert payload.sub == str(user_id)
        assert payload.type == "refresh"
        assert payload.jti == jti

    def test_decode_with_wrong_type_raises(self) -> None:
        user_id = uuid.uuid4()
        access_token, _ = create_access_token(user_id, "admin")
        with pytest.raises(AuthError) as exc:
            decode_refresh_token(access_token)
        assert exc.value.code == "wrong_token_type"

    def test_revoked_token_raises(self) -> None:
        user_id = uuid.uuid4()
        token, jti = create_refresh_token(user_id, "admin")
        revoke_refresh_token(jti)
        try:
            with pytest.raises(AuthError) as exc:
                decode_refresh_token(token)
            assert exc.value.code == "token_revoked"
        finally:
            # Clean up revocation store after test
            _revoked_jtis.discard(jti)

    def test_different_calls_produce_different_jtis(self) -> None:
        user_id = uuid.uuid4()
        _, jti1 = create_refresh_token(user_id, "admin")
        _, jti2 = create_refresh_token(user_id, "admin")
        assert jti1 != jti2
