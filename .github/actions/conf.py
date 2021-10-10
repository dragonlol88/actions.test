import logging
import typing as t
from pydantic import BaseSettings, SecretStr


class Settings(BaseSettings):
    token: SecretStr
    g_context: t.Dict[str, t.Any]
    github_server_url: str


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    logging.info(f"Using config: {settings.json()}")



