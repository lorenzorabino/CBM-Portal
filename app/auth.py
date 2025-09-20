from functools import wraps
from flask import session, abort


def role_required(*allowed_roles: str):
    """Decorator to enforce user roles via session.

    Accepts one or more roles (e.g., 'admin', 'planner').
    Looks for user_type in either session['user']['user_type'] or session['user_type'].
    Aborts with 403 if user not logged in or role not allowed.
    """
    allowed = {str(r).strip().lower() for r in allowed_roles}

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            utype = None
            try:
                u = session.get('user')
                if isinstance(u, dict):
                    utype = (u.get('user_type') or '').strip().lower()
            except Exception:
                utype = None
            if not utype:
                # Fallback to legacy flat session key
                utype = (session.get('user_type') or '').strip().lower()
            if not utype or (allowed and utype not in allowed):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
