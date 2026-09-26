from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    return generate_password_hash(password, method="scrypt")


def verify_password(password, password_hash):
    if not isinstance(password, str) or not isinstance(password_hash, str):
        return False

    return check_password_hash(password_hash, password)
