import base64, hashlib, os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from .config import settings

class EncryptionService:
    def __init__(self):
        if settings.encryption_master_key:
            try:
                self.master = base64.urlsafe_b64decode(settings.encryption_master_key + "==")
            except Exception as exc:
                raise RuntimeError("ENCRYPTION_MASTER_KEY must be urlsafe base64") from exc
        else:
            self.master = hashlib.sha256(settings.secret_key.encode()).digest()
        if len(self.master) < 32:
            self.master = hashlib.sha256(self.master).digest()
        self.master = self.master[:32]

    def _key(self, organization_id: str) -> bytes:
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=("sris-org:"+organization_id).encode()).derive(self.master)

    def encrypt(self, organization_id: str, plaintext: str | None) -> str | None:
        if plaintext is None: return None
        nonce = os.urandom(12)
        ct = AESGCM(self._key(organization_id)).encrypt(nonce, plaintext.encode(), organization_id.encode())
        return "v1." + base64.urlsafe_b64encode(nonce + ct).decode()

    def decrypt(self, organization_id: str, ciphertext: str | None) -> str | None:
        if ciphertext is None: return None
        if not ciphertext.startswith("v1."): return ciphertext
        raw = base64.urlsafe_b64decode(ciphertext[3:].encode())
        return AESGCM(self._key(organization_id)).decrypt(raw[:12], raw[12:], organization_id.encode()).decode()

encryption = EncryptionService()
