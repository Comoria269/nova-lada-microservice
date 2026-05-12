"""
Authentification simple par token pour les endpoints /admin.
"""
import secrets

from fastapi import Header, HTTPException, status

from .config import settings


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    """Vérifie le header `X-Admin-Token`."""
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token, settings.admin_api_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Token header.",
        )
