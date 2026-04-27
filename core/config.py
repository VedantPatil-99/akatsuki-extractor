from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SECRET_KEY: str
    QSTASH_CURRENT_SIGNING_KEY: str
    QSTASH_NEXT_SIGNING_KEY: str
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()