import os
import sys
# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)
# app/tests/test_repo.py
import asyncio
from app.services.repository_ingestion import RepositoryProcessor

async def test_multiple_files():
    processor = RepositoryProcessor()
    
    def progress_callback(current, total, file):
        print(f"Processing {current}/{total}: {file}")
    
    processor.set_callback(progress_callback)
    
    try:
        # Test with your actual repository containing Python files
        success = await processor.ingest_repository(
            owner="divyakasa-09",
            repo="code-search-rag"
        )
        
        # Print processed files for verification
        print("\nProcessed Files:")
        for file in processor.processed_files:
            print(f"- {file}")
            
        print(f"\nTotal files processed: {len(processor.processed_files)}")
        
    finally:
        await processor.cleanup()

if __name__ == "__main__":
    asyncio.run(test_multiple_files())