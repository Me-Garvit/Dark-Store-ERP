"""
Run once to generate your admin credentials.
Usage: python3 set_password.py
Then paste the output into .streamlit/secrets.toml
"""
import hashlib
import secrets
import getpass

username = input("Choose admin username: ").strip()
password = getpass.getpass("Choose admin password: ")

salt   = secrets.token_hex(16)
hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()

print("\nAdd these lines to .streamlit/secrets.toml:\n")
print(f'ADMIN_USERNAME     = "{username}"')
print(f'ADMIN_SALT         = "{salt}"')
print(f'ADMIN_PASSWORD_HASH = "{hashed}"')
