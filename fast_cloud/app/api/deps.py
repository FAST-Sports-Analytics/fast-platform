from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_token_claims
from app.db.session import get_db
from app.models import User

bearer = HTTPBearer(auto_error=True)


def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate a FAST token without requiring the account to be active.

    This is intentionally narrower than ``get_current_user``.  It exists so the
    authoritative /auth/session heartbeat can report that an already signed-in
    account has subsequently been suspended.  Normal protected API endpoints
    continue to use get_current_user and therefore still reject suspended users.
    """
    try:
        claims = decode_token_claims(credentials.credentials)
        user_id = int(claims["sub"])
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account unavailable",
        )
    if int(claims.get("ver", 1)) != int(user.auth_version or 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired. Please sign in again.")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        claims = decode_token_claims(credentials.credentials)
        user_id = int(claims["sub"])
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    if int(claims.get("ver", 1)) != int(user.auth_version or 1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired. Please sign in again.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user
