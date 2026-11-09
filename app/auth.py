import base64, hashlib, hmac, os
from fastapi import Request
from sqlalchemy.orm import Session
from .models import User
try:
    import bcrypt as _bcrypt
except Exception:
    _bcrypt = None

def hash_password(password: str) -> str:
    if _bcrypt is not None:
        return _bcrypt.hashpw(password.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')
    salt=os.urandom(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
    return 'scrypt$'+base64.b64encode(salt).decode()+'$'+base64.b64encode(digest).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        if hashed.startswith('scrypt$'):
            _,s,d=hashed.split('$',2); salt=base64.b64decode(s); expected=base64.b64decode(d)
            got=hashlib.scrypt(password.encode(),salt=salt,n=2**14,r=8,p=1,dklen=32)
            return hmac.compare_digest(got,expected)
        if _bcrypt is None:
            return False
        h = hashed.replace('$2y$', '$2b$')
        return _bcrypt.checkpw(password.encode('utf-8'), h.encode('utf-8'))
    except Exception:
        return False

def current_user(request: Request, db: Session) -> User | None:
    uid = request.session.get('user_id')
    if not uid:
        return None
    return db.get(User, uid)
