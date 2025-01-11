# app/services/repository_ingestion.py
import asyncio
import logging
from typing import List, Dict, Optional, Callable
import base64
from app.services.github import GitHubService
from app.services.snowflake import SnowflakeSearchService

logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    """Custom exception for processing errors."""
    pass

class RepositoryProcessor:
    def __init__(self, batch_size: int = 2):
        self.github_service = GitHubService()
        self.snowflake_service = SnowflakeSearchService()
        self.batch_size = batch_size
        self.processed_files = set()
        self.callback: Optional[Callable[[int, int, str], None]] = None
        self.total_files = 0
        self.processed_count = 0
        self.current_file = ""

    def set_callback(self, callback: Callable[[int, int, str], None]):
        """Set a callback function to report progress."""
        self.callback = callback

    async def _update_progress(self, file_path: str):
        """Update processing progress."""
        self.processed_count += 1
        self.current_file = file_path
        if self.callback:
            await self.callback(self.processed_count, self.total_files, self.current_file)

    async def process_file(self, file_info: Dict, repo: str) -> Optional[Dict]:
        """Process a single file with improved error handling."""
        file_path = file_info['path']
        file_url = file_info['url']

        if file_path in self.processed_files:
            logger.info(f"Skipping already processed file: {file_path}")
            return None

        try:
            # Skip binary files and very large files
            if file_path.endswith(('.exe', '.bin', '.zip', '.tar.gz')):
                logger.info(f"Skipping binary file: {file_path}")
                return None

            content = await self.github_service.get_file_content(file_url)
            if not content:
                logger.warning(f"No content found for file: {file_path}")
                return None

            try:
                decoded_content = base64.b64decode(content).decode('utf-8')
            except UnicodeDecodeError:
                logger.warning(f"Could not decode file as UTF-8: {file_path}")
                return None

            # Get file extension for language detection
            extension = file_path.split('.')[-1].lower() if '.' in file_path else ''
            if not extension:
                logger.info(f"Skipping file without extension: {file_path}")
                return None

            # Store in Snowflake
            await self.snowflake_service.store_code_chunk(
                repo_name=repo,
                file_path=file_path,
                content=decoded_content,
                language=extension
            )

            self.processed_files.add(file_path)
            await self._update_progress(file_path)
            
            return {
                "file_path": file_path,
                "language": extension,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return {
                "file_path": file_path,
                "status": "error",
                "error": str(e)
            }

    async def ingest_repository(self, owner: str, repo: str) -> bool:
        """Process all files in a repository with improved error handling and progress tracking."""
        try:
        # Validate repository first
            if not await self.github_service.validate_repository(owner, repo):
               raise ValueError(f"Repository {owner}/{repo} does not exist or is not accessible")

        # Get repository tree
            repo_files = await self.github_service.get_repository_tree(owner, repo)
            self.total_files = len(repo_files)
            self.processed_count = 0
        
            if self.total_files == 0:
               logger.warning("No files found in repository")
               return False

        # Begin tracking the repository
            await self.snowflake_service.add_or_update_repository(
            owner=owner,
            repo_name=repo,
            total_files=self.total_files,
            total_chunks=0  # Will update this as we process
             )

        # Process files in batches
            success_count = 0
            error_count = 0
            chunks_processed = 0
        
            for i in range(0, len(repo_files), self.batch_size):
                batch = repo_files[i:i + self.batch_size]
                tasks = [self.process_file(file, repo) for file in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            
                for result in results:
                    if isinstance(result, Exception):
                       error_count += 1
                       continue
                    if result and result.get('status') == 'success':
                       success_count += 1
                       chunks_processed += 1  # Increment for each successful chunk

            # Update repository stats periodically
                if i % 10 == 0 or i == len(repo_files) - 1:
                    await self.snowflake_service.add_or_update_repository(
                    owner=owner,
                    repo_name=repo,
                    total_files=success_count,
                    total_chunks=chunks_processed
                    )

            logger.info(f"Repository processing completed. "
                   f"Processed {success_count} files successfully, "
                   f"{error_count} files failed.")

        # Final update of repository stats
            await self.snowflake_service.add_or_update_repository(
            owner=owner,
            repo_name=repo,
            total_files=success_count,
            total_chunks=chunks_processed
            )

            return success_count > 0
   
        except Exception as e:
            logger.error(f"Error processing repository: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self):
        """Clean up resources."""
        try:
            await self.github_service.close()
            await self.snowflake_service.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")