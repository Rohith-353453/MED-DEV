from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import UserProfile

bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=8)
def get_jwks_client(jwks_uri: str) -> PyJWKClient:
    return PyJWKClient(
        jwks_uri,
        cache_keys=True,
        lifespan=3600,
    )


async def get_current_profile(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserProfile:
    settings = get_settings()
    if settings.auth_mode == "mock":
        issuer, subject = "local", settings.mock_user_sub
        claims: dict[str, Any] = {}
    else:
        if not credentials:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign-in required")
        try:
            if settings.auth_mode == "firebase":
                if not settings.firebase_project_id:
                    raise RuntimeError("FIREBASE_PROJECT_ID is not configured")
                project_id = settings.firebase_project_id
                issuer = f"https://securetoken.google.com/{project_id}"
                audience = project_id
                jwks_uri = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
            else:
                if (
                    not settings.entra_tenant_id
                    or not settings.entra_issuer
                    or not settings.entra_api_audience
                ):
                    raise RuntimeError("Entra token validation is not configured")
                issuer = settings.entra_issuer
                audience = settings.entra_api_audience
                issuer_base = issuer.removesuffix("/v2.0")
                jwks_uri = settings.entra_jwks_uri or f"{issuer_base}/discovery/v2.0/keys"
            key = get_jwks_client(jwks_uri).get_signing_key_from_jwt(credentials.credentials)
            claims = jwt.decode(
                credentials.credentials,
                key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            if settings.auth_mode == "entra":
                scopes = set(str(claims.get("scp", "")).split())
                roles = set(claims.get("roles", []))
                if (
                    settings.entra_required_scope not in scopes
                    and settings.entra_required_scope not in roles
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Required API permission is missing",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            # Avoid returning token validation details to callers or application logs.
            raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc
        issuer, subject = str(claims["iss"]), str(claims["sub"])

    profile = await session.scalar(
        select(UserProfile).where(UserProfile.issuer == issuer, UserProfile.subject == subject)
    )
    if profile is None:
        profile = UserProfile(
            issuer=issuer,
            subject=subject,
            display_name=claims.get("name") if claims else "Local Demo User",
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


CurrentProfile = Annotated[UserProfile, Depends(get_current_profile)]
