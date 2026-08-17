from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_token
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
        user_id = decode_token(credentials.credentials)
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
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = decode_token(credentials.credentials)
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc
    user = db.get(User, user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return user
