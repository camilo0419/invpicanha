from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

def role_required(*roles):
    def dec(view):
        @login_required
        @wraps(view)
        def wrapped(request,*a,**kw):
            profile=getattr(request.user,'profile',None)
            if not profile or not profile.active or profile.role not in roles: raise PermissionDenied
            return view(request,*a,**kw)
        return wrapped
    return dec
