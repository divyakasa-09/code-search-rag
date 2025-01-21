import os
import sys
from pathlib import Path
import streamlit as st

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up environment variables from Streamlit secrets
if hasattr(st, 'secrets'):
    for key, value in st.secrets.get("env", {}).items():
        os.environ[key] = str(value)

# Import and run the main application
from app.main import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        raise