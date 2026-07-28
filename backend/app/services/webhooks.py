import hmac, hashlib, json
from datetime import datetime, timezone
import httpx
from app.core.encryption import encryption

async def dispatch_webhook(endpoint, organization_id: str, event_name: str, payload: dict):
    secret=encryption.decrypt(organization_id, endpoint.secret_encrypted)
    body=json.dumps({"event":event_name,"timestamp":datetime.now(timezone.utc).isoformat(),"data":payload}, separators=(",",":"), default=str).encode()
    signature=hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=10) as client:
        return await client.post(endpoint.url, content=body, headers={"content-type":"application/json","x-sris-signature":"sha256="+signature})
