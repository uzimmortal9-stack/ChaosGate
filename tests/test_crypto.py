from core import crypto
from core.models import Workspace


def test_encrypt_decrypt_roundtrip():
    token = "gh" + "p_" + "9sKmQ2xVn4RtY7wZ1aB3cD5eF6gH8iJ0kL2m"
    enc = crypto.encrypt_token(token, secret="test-secret-key-1234")
    assert enc.startswith("enc:v1:")
    assert enc != token

    dec = crypto.decrypt_token(enc, secret="test-secret-key-1234")
    assert dec == token


def test_decrypt_plaintext_legacy_token():
    legacy = "gh" + "p_" + "legacy_plaintext_token"
    # Should return legacy token as-is without raising
    assert crypto.decrypt_token(legacy) == legacy


def test_tampered_token_returns_payload_safely():
    token = "gh" + "p_" + "secret_token"
    enc = crypto.encrypt_token(token, secret="test-secret")
    # Tamper with the base64 content
    tampered = enc[:-4] + "AAAA"
    # Tampered tag should fail authentication cleanly
    res = crypto.decrypt_token(tampered, secret="test-secret")
    assert res == tampered  # Does not decrypt, returns payload safely


from core.db import SessionLocal, init_db


def test_workspace_model_transparent_encryption():
    init_db()
    session = SessionLocal()
    token_val = "gh" + "p_" + "my_secret_token_123"
    try:
        ws = Workspace(github_login="octocat", github_token=token_val)
        session.add(ws)
        session.commit()

        # Column in SQLite is encrypted
        assert ws._github_token.startswith("enc:v1:")
        assert token_val not in ws._github_token

        # Property getter decrypts transparently
        assert ws.github_token == token_val
    finally:
        session.close()
