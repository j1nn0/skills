from .errors import Unauthorized


def authorize(session, now):
    if now >= session.expires_at:
        raise Unauthorized("expired session")
    return session.user
