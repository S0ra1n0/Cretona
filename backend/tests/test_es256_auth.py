"""Asymmetric (ES256) token verification.

Supabase's current default signs with a rotating EC key and publishes the
public half at a JWKS endpoint. This is the path a real user actually
authenticates through; the HS256 tests next door cover the legacy scheme.
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.config import Settings
from app.jwks import MIN_REFETCH_INTERVAL_SECONDS, JwksCache, JwksError
from app.main import create_app
from app.supabase_jwt import TokenError, verify_asymmetric_token
from tests.conftest import JWT_AUDIENCE, JWT_ISSUER, USER_A, USER_B

JWKS_URL = "https://project-ref.supabase.co/auth/v1/.well-known/jwks.json"


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class SigningKey:
    """An EC key pair plus the JWK the project would publish for it."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self.private = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict[str, Any]:
        numbers = self.private.public_key().public_numbers()
        return {
            "kty": "EC",
            "crv": "P-256",
            "kid": self.kid,
            "use": "sig",
            "alg": "ES256",
            "x": b64u(numbers.x.to_bytes(32, "big")),
            "y": b64u(numbers.y.to_bytes(32, "big")),
        }

    def token(self, **overrides: Any) -> str:
        claims: dict[str, Any] = {
            "sub": USER_A,
            "aud": JWT_AUDIENCE,
            "iss": JWT_ISSUER,
            "exp": overrides.pop("exp", 4102444800),  # 2100
            "email": "a@example.com",
        }
        claims.update(overrides)
        algorithm = overrides.pop("algorithm", "ES256")
        return jwt.encode(
            claims,
            self.private,
            algorithm=algorithm,
            headers={"kid": self.kid},
        )


class FakeClock:
    """A clock the test moves by hand, so staleness is deterministic."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def cache_for(
    keys: list[SigningKey],
    counter: list[int] | None = None,
    clock: FakeClock | None = None,
) -> JwksCache:
    def handler(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append(1)
        return httpx.Response(200, json={"keys": [key.jwk for key in keys]})

    return JwksCache(
        JWKS_URL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock or FakeClock(),
    )


def verify(token: str, jwks: JwksCache) -> Any:
    return verify_asymmetric_token(
        token,
        jwks=jwks,
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
    )


# --- accepted ---------------------------------------------------------------


def test_a_project_signed_token_is_accepted() -> None:
    key = SigningKey("kid-1")

    identity = verify(key.token(), cache_for([key]))

    assert identity.user_id == USER_A
    assert identity.email == "a@example.com"


def test_the_right_key_is_chosen_from_several() -> None:
    first, second = SigningKey("kid-1"), SigningKey("kid-2")

    assert verify(second.token(subject=USER_B, sub=USER_B), cache_for([first, second]))


# --- rejected ---------------------------------------------------------------


def test_a_token_signed_by_an_unpublished_key_is_rejected() -> None:
    published = SigningKey("kid-1")
    attacker = SigningKey("kid-1")  # same kid, different key material

    with pytest.raises(TokenError):
        verify(attacker.token(), cache_for([published]))


def test_an_unknown_kid_is_rejected() -> None:
    published = SigningKey("kid-1")
    stranger = SigningKey("kid-unknown")

    with pytest.raises(TokenError):
        verify(stranger.token(), cache_for([published]))


def test_a_token_without_a_kid_is_rejected() -> None:
    key = SigningKey("kid-1")
    token = jwt.encode({"sub": USER_A, "exp": 4102444800}, key.private, algorithm="ES256")

    with pytest.raises(TokenError):
        verify(token, cache_for([key]))


def test_an_hs256_token_is_refused_on_the_asymmetric_path() -> None:
    """Algorithm confusion, the reason the allowlist is ours and not the token's.

    A caller must not be able to present an HMAC token and have some public
    value treated as a shared secret.
    """
    key = SigningKey("kid-1")
    token = jwt.encode(
        {"sub": USER_A, "aud": JWT_AUDIENCE, "iss": JWT_ISSUER, "exp": 4102444800},
        "not-a-real-secret",
        algorithm="HS256",
        headers={"kid": "kid-1"},
    )

    with pytest.raises(TokenError):
        verify(token, cache_for([key]))


def test_an_expired_token_is_rejected() -> None:
    key = SigningKey("kid-1")

    with pytest.raises(TokenError):
        verify(key.token(exp=1000000000), cache_for([key]))


@pytest.mark.parametrize(
    "claim",
    [{"aud": "anon"}, {"iss": "https://evil.example.com/auth/v1"}],
)
def test_wrong_audience_or_issuer_is_rejected(claim: dict[str, Any]) -> None:
    key = SigningKey("kid-1")

    with pytest.raises(TokenError):
        verify(key.token(**claim), cache_for([key]))


def test_a_token_without_a_subject_is_rejected() -> None:
    key = SigningKey("kid-1")
    token = jwt.encode(
        {"aud": JWT_AUDIENCE, "iss": JWT_ISSUER, "exp": 4102444800},
        key.private,
        algorithm="ES256",
        headers={"kid": "kid-1"},
    )

    with pytest.raises(TokenError):
        verify(token, cache_for([key]))


def test_an_unreachable_key_set_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    jwks = JwksCache(JWKS_URL, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(TokenError):
        verify(SigningKey("kid-1").token(), jwks)


# --- cache behaviour --------------------------------------------------------


def test_the_key_set_is_fetched_once_for_repeated_tokens() -> None:
    key = SigningKey("kid-1")
    fetches: list[int] = []
    jwks = cache_for([key], fetches)

    for _ in range(5):
        verify(key.token(), jwks)

    assert len(fetches) == 1


def test_a_flood_of_unknown_kids_does_not_flood_the_auth_server() -> None:
    """The amplification guard.

    An unauthenticated endpoint takes arbitrary `kid` values, so one request
    per unknown kid would let anyone turn this into a request amplifier.
    """
    clock = FakeClock()
    key = SigningKey("kid-1")
    fetches: list[int] = []
    jwks = cache_for([key], fetches, clock)
    verify(key.token(), jwks)
    assert len(fetches) == 1

    stranger = SigningKey("kid-nope")
    for _ in range(20):
        clock.advance(1)
        with pytest.raises(TokenError):
            verify(stranger.token(), jwks)

    # Still one fetch: the floor absorbed every one of them.
    assert len(fetches) == 1


def test_a_rotated_key_is_picked_up_after_the_floor() -> None:
    clock = FakeClock()
    old = SigningKey("kid-old")
    published = [old]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [k.jwk for k in published]})

    jwks = JwksCache(
        JWKS_URL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock,
    )
    verify(old.token(), jwks)

    new = SigningKey("kid-new")
    published[:] = [new]

    # Inside the floor, rotation is not yet visible.
    with pytest.raises(JwksError):
        jwks.key_for("kid-new")

    clock.advance(MIN_REFETCH_INTERVAL_SECONDS + 1)

    # Past it, the new key is picked up without a restart.
    assert jwks.key_for("kid-new")["kid"] == "kid-new"


def test_a_withdrawn_key_stops_verifying() -> None:
    clock = FakeClock()
    retired, current = SigningKey("kid-retired"), SigningKey("kid-current")
    published = [retired, current]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [k.jwk for k in published]})

    jwks = JwksCache(
        JWKS_URL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        clock=clock,
    )
    verify(retired.token(), jwks)

    published[:] = [current]
    # Past the TTL, so the cached set is refetched rather than trusted.
    clock.advance(jwks.ttl_seconds + 1)

    # Replaced wholesale rather than merged, so a revoked key really is gone.
    with pytest.raises(JwksError):
        jwks.key_for("kid-retired")


def test_a_malformed_key_set_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"not-keys": []})

    jwks = JwksCache(JWKS_URL, client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(JwksError):
        jwks.key_for("kid-1")


# --- configuration ----------------------------------------------------------


def test_es256_mode_needs_a_key_source() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings(auth_mode="supabase", supabase_jwt_algorithm="ES256")


def test_the_jwks_url_defaults_to_the_well_known_endpoint() -> None:
    settings = Settings(
        auth_mode="supabase",
        supabase_jwt_algorithm="ES256",
        supabase_url="https://project-ref.supabase.co",
    )

    assert settings.resolved_jwks_url() == JWKS_URL


def test_es256_mode_needs_no_shared_secret() -> None:
    # The point of asymmetric keys: this backend holds no signing material.
    settings = Settings(
        auth_mode="supabase",
        supabase_jwt_algorithm="ES256",
        supabase_url="https://project-ref.supabase.co",
    )

    assert settings.supabase_jwt_secret.get_secret_value() == ""


# --- through the API --------------------------------------------------------


@pytest.fixture
def es256_client(tmp_path: Path) -> Iterator[tuple[TestClient, SigningKey]]:
    media = tmp_path / "media"
    media.mkdir()
    (media / "demo-output.mp4").write_bytes(b"test-mp4-bytes")
    settings = Settings(
        environment="test",
        auth_mode="supabase",
        supabase_jwt_algorithm="ES256",
        supabase_url="https://project-ref.supabase.co",
        supabase_jwt_audience=JWT_AUDIENCE,
        supabase_jwt_issuer=JWT_ISSUER,
        database_path=tmp_path / "es256.db",
        media_dir=media,
        prompt_llm_provider="deterministic",
        poller_enabled=False,
        generation_log_retention_enabled=False,
    )
    key = SigningKey("kid-live")
    app = create_app(settings)
    app.state.jwks = cache_for([key])
    with TestClient(app, raise_server_exceptions=False) as client:
        client.app.state.database.upsert_user(USER_A, email="a@example.com")
        yield client, key


def test_a_real_shaped_token_authenticates_end_to_end(
    es256_client: tuple[TestClient, SigningKey],
) -> None:
    client, key = es256_client

    response = client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {key.token()}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == USER_A
    assert body["quota"]["limit"] > 0


def test_an_unsigned_request_is_still_refused(
    es256_client: tuple[TestClient, SigningKey],
) -> None:
    client, _ = es256_client

    assert client.get("/api/v1/me").status_code == 401
