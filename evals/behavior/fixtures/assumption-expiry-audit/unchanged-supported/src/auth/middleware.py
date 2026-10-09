from .errors import Unauthorized
from .session import authorize


def dispatch_authenticated(request, now, protected_handler):
    session = request.session
    try:
        user = authorize(session, now)
    except Unauthorized as error:
        return {"status": error.status, "body": str(error)}
    request.user = user
    return protected_handler(request)
