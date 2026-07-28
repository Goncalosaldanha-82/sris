import base64, hashlib, hmac, json, secrets, uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from .config import settings

def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + '=' * (-len(data) % 4))

def hash_password(password: str) -> str:
    raw=password.encode('utf-8')
    if len(raw)>1024: raise ValueError('Password too long')
    salt=secrets.token_bytes(16); iterations=600_000
    digest=hashlib.pbkdf2_hmac('sha256',raw,salt,iterations)
    return f'pbkdf2_sha256${iterations}${_b64e(salt)}${_b64e(digest)}'

def verify_password(password: str, password_hash: str) -> bool:
    try:
        alg,it,salt,digest=password_hash.split('$',3)
        if alg!='pbkdf2_sha256': return False
        candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),_b64d(salt),int(it))
        return hmac.compare_digest(candidate,_b64d(digest))
    except Exception:return False

def create_token(subject: str, token_type: str, minutes: int|None=None, days: int|None=None, extra: dict|None=None) -> str:
    now=datetime.now(timezone.utc); exp=now+(timedelta(minutes=minutes) if minutes else timedelta(days=days or 1))
    header={'alg':'HS256','typ':'JWT'}; payload={'sub':subject,'typ':token_type,'iat':int(now.timestamp()),'exp':int(exp.timestamp()),'jti':str(uuid.uuid4())}
    if extra:payload.update(extra)
    signing=f'{_b64e(json.dumps(header,separators=(",",":")).encode())}.{_b64e(json.dumps(payload,separators=(",",":")).encode())}'
    sig=hmac.new(settings.secret_key.encode(),signing.encode(),hashlib.sha256).digest()
    return signing+'.'+_b64e(sig)

def decode_token(token: str, expected_type: str|None=None) -> dict:
    try:
        h,p,s=token.split('.')
        expected=hmac.new(settings.secret_key.encode(),f'{h}.{p}'.encode(),hashlib.sha256).digest()
        if not hmac.compare_digest(expected,_b64d(s)):raise ValueError('signature')
        payload=json.loads(_b64d(p))
        if int(payload.get('exp',0))<int(datetime.now(timezone.utc).timestamp()):raise ValueError('expired')
        if expected_type and payload.get('typ')!=expected_type:raise ValueError('type')
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail='Invalid or expired token') from exc

def new_api_key() -> tuple[str,str,str]:
    raw='sris_'+secrets.token_urlsafe(32);return raw,raw[:13],hashlib.sha256(raw.encode()).hexdigest()
def hash_api_key(raw:str)->str:return hashlib.sha256(raw.encode()).hexdigest()
