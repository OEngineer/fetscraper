"""Test if config is loading properly."""

from src.config import config

print("Config loaded:")
print(f"Username: {config.username}")
print(f"Password: {'*' * len(config.password) if config.password else 'None'}")
print(f"Credentials valid: {config.validate_credentials()}")
