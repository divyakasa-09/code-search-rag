from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # GitHub
    github_token: str = ""  # Added default empty string
    
    # Snowflake
    snowflake_account: str = ""  # Added default empty string
    snowflake_user: str = ""     # Added default empty string
    snowflake_password: str = "" # Added default empty string
    
    # App Settings
    app_name: str = "Code Expert"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        case_sensitive = False

@lru_cache
def get_settings() -> Settings:
    return Settings()