from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from atlas_common import auth
from atlas_common.config import settings


@pytest.fixture
def cognito_token(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    issuer = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example"
    monkeypatch.setattr(auth, "cognito_issuer", lambda: issuer)
    monkeypatch.setattr(settings, "auth_mode", "cognito")
    monkeypatch.setenv("ATLAS_COGNITO_APP_CLIENT_ID", "atlas-client")
    monkeypatch.setattr(
        auth,
        "_jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=public_key)
        ),
    )

    def issue(**overrides):
        claims = {
            "iss": issuer,
            "sub": "cognito-user-123",
            "token_use": "access",
            "client_id": "atlas-client",
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        }
        claims.update(overrides)
        return jwt.encode(claims, private_key, algorithm="RS256")

    return issue


def test_accepts_valid_cognito_access_token(cognito_token):
    claims = auth.verify_bearer(cognito_token())
    assert claims["sub"] == "cognito-user-123"


@pytest.mark.parametrize(
    ("claim", "error_type"),
    [
        ({"token_use": "id"}, ValueError),
        ({"client_id": "different-client"}, ValueError),
        ({"sub": ""}, ValueError),
        (
            {"exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())},
            jwt.ExpiredSignatureError,
        ),
    ],
)
def test_rejects_invalid_cognito_access_token(cognito_token, claim, error_type):
    with pytest.raises(error_type):
        auth.verify_bearer(cognito_token(**claim))


def test_rejects_cross_tenant_claim():
    with pytest.raises(HTTPException) as error:
        auth.require_user_id("victim", "attacker")
    assert error.value.status_code == 403
