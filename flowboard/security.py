import hashlib
import hmac
import secrets


PBKDF2_ITERATIONS = 310_000


def hash_password(password, *, salt=None, iterations=PBKDF2_ITERATIONS):
    if not isinstance(password, str) or not password:
        raise ValueError("password must not be empty")
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, iterations
    )
    return f"pbkdf2_sha256${iterations}${salt_bytes.hex()}${digest.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, raw_iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hash_password(
            password, salt=salt, iterations=int(raw_iterations)
        ).rsplit("$", 1)[-1]
        return hmac.compare_digest(actual, expected)
    except (AttributeError, TypeError, ValueError):
        return False


def new_token():
    return secrets.token_urlsafe(32)


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

