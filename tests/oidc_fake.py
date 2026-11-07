"""A fake in-memory OIDC provider for tests. Never touches the network.

The real authlib client is used with static provider metadata and an inline
JWKS, so state, nonce, PKCE and ID token validation all run for real. Only the
token-endpoint HTTP call is replaced, returning an ID token signed here.
"""

import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.starlette_client import OAuth
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "https://auth.example.test/application/o/llc-manager/"
CLIENT_ID = "test-client-id"
REDIRECT_URI = "https://llc.example.test/auth/callback"


class FakeProvider:
    """Signs ID tokens and exposes an authlib client wired to itself."""

    def __init__(self) -> None:
        """Generate a signing key and register the authlib client."""
        self._key = RSAKey.generate_key(
            2048, {"kid": "test-key", "use": "sig", "alg": "RS256"}
        )
        self.next_claims: dict[str, Any] = {}
        self.fail_with: Exception | None = None
        self.last_exchange: dict[str, Any] = {}
        oauth = OAuth()
        oauth.register(
            name="authentik",
            client_id=CLIENT_ID,
            client_secret="test-client-secret",  # pragma: allowlist secret
            issuer=ISSUER,
            authorization_endpoint="https://auth.example.test/authorize/",
            token_endpoint="https://auth.example.test/token/",
            jwks={"keys": [self._key.as_dict(private=False)]},
            id_token_signing_alg_values_supported=["RS256"],
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )
        self.client: Any = oauth.authentik
        self.client.fetch_access_token = self._fetch_access_token
        self._nonce: str | None = None

    def remember_authorization(self, location: str) -> dict[str, str]:
        """Capture state and nonce from the redirect to the provider.

        Args:
            location: The ``Location`` header of the authorize redirect.

        Returns:
            Single-valued query parameters of the authorize URL.
        """
        query = parse_qs(urlsplit(location).query)
        params = {key: values[0] for key, values in query.items()}
        self._nonce = params["nonce"]
        return params

    def claims(self, **overrides: Any) -> dict[str, Any]:
        """Build valid claims for the remembered authorization, with overrides.

        Args:
            **overrides: Claims to add or replace. A value of ``None`` removes
                the claim.

        Returns:
            The claim set.
        """
        now = int(time.time())
        base: dict[str, Any] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "user-123",
            "iat": now,
            "exp": now + 300,
            "nonce": self._nonce,
            "email": "ada@example.test",
            "name": "Ada Lovelace",
            "groups": ["llc-manager-admins"],
        }
        base.update(overrides)
        return {key: value for key, value in base.items() if value is not None}

    def sign(self, claims: dict[str, Any]) -> str:
        """Sign an ID token.

        Args:
            claims: The claim set.

        Returns:
            The compact JWT.
        """
        return jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, self._key)

    async def _fetch_access_token(self, **params: Any) -> dict[str, Any]:
        self.last_exchange = dict(params)
        if self.fail_with is not None:
            raise self.fail_with
        return {
            "access_token": "fake-access-token",
            "token_type": "Bearer",
            "id_token": self.sign(self.next_claims),
        }
