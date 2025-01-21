
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # GitHub
    github_token: str
    
    # Snowflake
    snowflake_account: str
    snowflake_user: str
    snowflake_password: str
    
    # App Settings
    app_name: str = "Code Expert"
    debug: bool = False

    class Config:
        env_file = ".env"
        extra = "allow"  

@lru_cache
def get_settings() -> Settings:
    return Settings()