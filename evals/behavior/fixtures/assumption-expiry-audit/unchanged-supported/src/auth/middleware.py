from .session import authorize


def dispatch_authenticated(request, now, protected_handler):
    session = request.session
    user = authorize(session, now)
    request.user = user
    return protected_handler(request)
