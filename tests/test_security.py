from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.security import (
    create_access_token,
    create_session_token,
    decode_access_token,
    decode_session_token,
    get_session_secret,
    hash_password,
    is_first_user,
    verify_password,
)


def test_hash_password_format_and_salt():
    pw = "supersecret123"
    hash1 = hash_password(pw)
    hash2 = hash_password(pw)

    assert hash1.startswith("$argon2id$")
    assert hash2.startswith("$argon2id$")
    assert hash1 != hash2, "Argon2 should generate unique salts per hash"


def test_verify_password():
    pw = "my-secure-password"
    hashed = hash_password(pw)

    assert verify_password(pw, hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(pw, "") is False
    assert verify_password(pw, "not-a-valid-argon2-hash") is False


def test_hash_password_empty_raises():
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")


def test_session_token_roundtrip():
    token = create_session_token(user_id=42, role="admin", expires_in_hours=24)
    assert isinstance(token, str)

    payload = decode_session_token(token)
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["user_id"] == 42
    assert payload["role"] == "admin"
    assert payload["type"] == "session"
    assert "exp" in payload
    assert "iat" in payload


def test_session_token_expired():
    token = create_session_token(user_id=42, role="admin", expires_in_hours=-1)
    assert decode_session_token(token) is None


def test_session_token_tampered():
    token = create_session_token(user_id=42, role="admin")
    tampered_token = token[:-5] + "aaaaa"
    assert decode_session_token(tampered_token) is None


def test_access_token_roundtrip():
    token = create_access_token(
        user_id=99, email="user@example.com", role="organizer", expires_in_seconds=3600
    )
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "99"
    assert payload["user_id"] == 99
    assert payload["email"] == "user@example.com"
    assert payload["role"] == "organizer"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_access_token_expired():
    token = create_access_token(
        user_id=99, email="user@example.com", role="organizer", expires_in_seconds=-10
    )
    assert decode_access_token(token) is None


def test_access_token_tampered():
    token = create_access_token(user_id=99, email="user@example.com", role="organizer")
    tampered_token = token[:-5] + "zzzzz"
    assert decode_access_token(tampered_token) is None


def test_token_type_separation():
    session_token = create_session_token(user_id=1, role="user")
    access_token = create_access_token(user_id=1, email="user@example.com", role="user")

    # Session decoder must reject access token
    assert decode_session_token(access_token) is None

    # Access decoder must reject session token
    assert decode_access_token(session_token) is None


def test_decode_invalid_tokens():
    assert decode_session_token("invalid.token.here") is None
    assert decode_access_token("not-a-token") is None
    assert decode_session_token("") is None
    assert decode_access_token("") is None
    assert decode_session_token(None) is None
    assert decode_access_token(None) is None
    assert decode_session_token(12345) is None
    assert decode_access_token(12345) is None


def test_token_defaults_from_settings():
    session_token = create_session_token(user_id=1, role="user")
    payload_session = decode_session_token(session_token)
    assert payload_session is not None
    assert payload_session["user_id"] == 1

    access_token = create_access_token(user_id=1, email="u@e.com", role="user")
    payload_access = decode_access_token(access_token)
    assert payload_access is not None
    assert payload_access["email"] == "u@e.com"


def test_get_session_secret_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", "configured-secret-key")
    import app.security as sec

    monkeypatch.setattr(sec, "_session_secret", None)

    assert get_session_secret() == "configured-secret-key"


def test_get_session_secret_production_missing_raises(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", None)
    monkeypatch.setattr(settings, "environment", "production")
    import app.security as sec

    # Even if dev secret was previously cached, production mode must block it
    monkeypatch.setattr(sec, "_session_secret", "cached-dev-secret")

    with pytest.raises(RuntimeError, match="SESSION_SECRET must be explicitly set"):
        get_session_secret()


def test_get_session_secret_dev_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "session_secret", None)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    import app.security as sec

    monkeypatch.setattr(sec, "_session_secret", None)

    secret1 = get_session_secret()
    assert len(secret1) == 64  # 32 bytes hex
    secret_file = tmp_path / ".session_secret"
    assert secret_file.exists()
    assert secret_file.read_text(encoding="utf-8").strip() == secret1

    # Reset in-memory cache to verify reading from persisted file
    monkeypatch.setattr(sec, "_session_secret", None)
    secret2 = get_session_secret()
    assert secret2 == secret1


def test_is_first_user_table_absent():
    engine = create_engine("sqlite:///:memory:")
    Session = sessionmaker(bind=engine)
    with Session() as db:
        assert is_first_user(db=db) is True


def test_is_first_user_empty_and_populated():
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    users_table = Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(255), nullable=False),
    )
    metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        # Table exists and is empty
        assert is_first_user(db=db) is True

        # Insert a user
        db.execute(users_table.insert().values(id=1, email="test@example.com"))
        db.commit()

        # Table exists and has at least one row
        assert is_first_user(db=db) is False


def test_is_first_user_default_session(monkeypatch):
    mock_session = MagicMock()
    mock_session.__enter__.return_value = mock_session
    mock_bind = MagicMock()
    mock_session.get_bind.return_value = mock_bind

    with (
        patch("app.security.SessionLocal", return_value=mock_session),
        patch("app.security.inspect") as mock_inspect,
    ):
        mock_inspector = MagicMock()
        mock_inspect.return_value = mock_inspector
        mock_inspector.has_table.return_value = False

        assert is_first_user() is True
        mock_inspector.has_table.assert_called_with("users")
