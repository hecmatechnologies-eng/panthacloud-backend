#!/usr/bin/env python3
"""Generate cryptographically secure production keys for Railway deployment.

Generates:
  1. JWT_SECRET_KEY: A high-entropy random string for signing authentication tokens.
  2. SECRET_ENCRYPTION_KEY: A Fernet key for encrypting repository tokens at rest.

Outputs values formatted for direct pasting into Railway's Variables dashboard.
"""

from secrets import token_urlsafe

from cryptography.fernet import Fernet


def generate_keys() -> tuple[str, str]:
    jwt_secret = token_urlsafe(48)
    encryption_key = Fernet.generate_key().decode("ascii")
    return jwt_secret, encryption_key


def main() -> None:
    jwt_secret, encryption_key = generate_keys()

    print("=" * 72)
    print("  Fussion Production Secrets Generator for Railway")
    print("=" * 72)
    print("\nCopy and paste the block below into Railway's Variables tab (RAW Editor):\n")
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"SECRET_ENCRYPTION_KEY={encryption_key}")
    print("\n" + "=" * 72)
    print("NOTE: Store these securely. If SECRET_ENCRYPTION_KEY is lost, previously")
    print("encrypted GitHub tokens stored in the database cannot be decrypted.")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
