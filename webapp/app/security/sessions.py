import hashlib
import secrets
from datetime import timedelta

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import Session, User, utcnow

_signer = URLSafeSerializer(settings.secret_key, salt="session-token")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: DbSession, user: User, ip: str, user_agent: str) -> str:
    """Create a DB session row and return the signed cookie value."""
    token = secrets.token_urlsafe(32)
    row = Session(
        token_hash=_hash_token(token),
        user_id=user.id,
        expires_at=utcnow() + timedelta(days=settings.session_absolute_days),
        ip=ip,
        user_agent=user_agent[:256],
    )
    db.add(row)
    db.commit()
    return _signer.dumps(token)


def resolve_session(db: DbSession, cookie_value: str) -> User | None:
    try:
        token = _signer.loads(cookie_value)
    except BadSignature:
        return None
    row = db.get(Session, _hash_token(token))
    if row is None:
        return None
    now = utcnow()
    idle_cutoff = timedelta(hours=settings.session_idle_hours)
    last_seen = row.last_seen_at
    expires = row.expires_at
    # SQLite returns naive datetimes; stored values are always UTC
    if last_seen.tzinfo is None:
        from datetime import timezone

        last_seen = last_seen.replace(tzinfo=timezone.utc)
        expires = expires.replace(tzinfo=timezone.utc)
    if now > expires or now - last_seen > idle_cutoff:
        db.delete(row)
        db.commit()
        return None
    # Sliding window: only write when meaningfully stale to avoid a write per request
    if now - last_seen > timedelta(minutes=5):
        row.last_seen_at = now
        db.commit()
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def destroy_session(db: DbSession, cookie_value: str) -> None:
    try:
        token = _signer.loads(cookie_value)
    except BadSignature:
        return
    row = db.get(Session, _hash_token(token))
    if row is not None:
        db.delete(row)
        db.commit()
