"""暗号化（ブラウザの WebCrypto でも開ける形）：AES-256-GCM の鍵を RSA-OAEP(SHA-256) で包む。公開鍵は keiba/app_pub.pem"""
import base64, json, os, sys
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

OAEP = padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
b64 = lambda b: base64.b64encode(b).decode()


def seal(data: bytes, pub_pem: bytes) -> dict:
    pub = serialization.load_pem_public_key(pub_pem)
    k = AESGCM.generate_key(256); iv = os.urandom(12)
    return {'v': 2, 'k': b64(pub.encrypt(k, OAEP)), 'iv': b64(iv), 'd': b64(AESGCM(k).encrypt(iv, data, None))}


def unseal(obj: dict, priv_pem: bytes) -> bytes:
    priv = serialization.load_pem_private_key(priv_pem, None)
    k = priv.decrypt(base64.b64decode(obj['k']), OAEP)
    return AESGCM(k).decrypt(base64.b64decode(obj['iv']), base64.b64decode(obj['d']), None)


if __name__ == '__main__':  # python3 keiba/seal2.py 入力 出力
    pub = open(os.path.join(os.path.dirname(__file__), 'app_pub.pem'), 'rb').read()
    json.dump(seal(open(sys.argv[1], 'rb').read(), pub), open(sys.argv[2], 'w'))
