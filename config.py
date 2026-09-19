from typing import Optional
from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    KITE_API_KEY: str
    KITE_SECRET_KEY: str
    REQUEST_TOKEN: Optional[str] = None
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB: str
    OPENAI_API_KEY: str
    KITE_ACCESS_TOKEN: Optional[str] = None
    ACCESS_TOKEN: Optional[str] = None

    @property
    def DATABASE_URL(self) -> str:
        """Construct database URL from settings."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = True

settings = Settings(_env_file='.env')  # Explicitly specify env file