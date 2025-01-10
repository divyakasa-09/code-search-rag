# app/tests/test_env.py
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from app.core.config import get_settings

def test_env():
    print("Testing environment variables...")
    settings = get_settings()
    
    # Print the values (but mask them for security)
    print(f"GitHub Token exists: {'✓' if settings.github_token else '✗'}")
    print(f"Snowflake Account exists: {'✓' if settings.snowflake_account else '✗'}")
    print(f"Snowflake User exists: {'✓' if settings.snowflake_user else '✗'}")
    print(f"Snowflake Password exists: {'✓' if settings.snowflake_password else '✗'}")
    print(f"App Name: {settings.app_name}")

if __name__ == "__main__":
    test_env()