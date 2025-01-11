import snowflake.connector
import json
import logging
from typing import Dict, Optional, List
from contextlib import contextmanager
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class SnowflakeSearchService:
    MAX_RETRIES = 3

    def __init__(self):
        """Initialize the Snowflake connection and setup database."""
        self.conn = None
        self._connect()
        self._initialize_search()

    def _connect(self, retry_count=0):
        """Establish connection to Snowflake with retry logic."""
        try:
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass

            self.conn = snowflake.connector.connect(
                user=settings.snowflake_user,
                password=settings.snowflake_password,
                account=settings.snowflake_account,
                database='CODE_EXPERT',
                warehouse='CODE_EXPERT_WH',
                schema='PUBLIC',
                autocommit=False
            )
            logger.info("Successfully connected to Snowflake")
        except Exception as e:
            logger.error(f"Error connecting to Snowflake: {e}")
            if retry_count < self.MAX_RETRIES:
                logger.info(f"Retrying connection (attempt {retry_count + 1}/{self.MAX_RETRIES})")
                self._connect(retry_count + 1)
            else:
                raise

    @contextmanager
    def get_cursor(self):
        """Provide a context manager for Snowflake cursors."""
        cursor = None
        try:
            cursor = self.conn.cursor()
            yield cursor
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            if cursor:
                cursor.close()

    def _initialize_search(self):
        """Create the database and table for Cortex Search."""
        with self.get_cursor() as cursor:
            try:
                # Use database and schema
                logger.info("Initializing database and schema...")
                cursor.execute("USE DATABASE CODE_EXPERT")
                cursor.execute("USE SCHEMA PUBLIC")
                logger.info("Database and schema set successfully")

                # Create table for code chunks
                logger.info("Creating or verifying CODE_CHUNKS_TABLE...")
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS CODE_CHUNKS_TABLE (
                    RELATIVE_PATH VARCHAR(16777216),
                    SIZE NUMBER,
                    FILE_URL VARCHAR(16777216),
                    SCOPED_FILE_URL VARCHAR(16777216),
                    CHUNK VARCHAR(16777216),
                    LANGUAGE VARCHAR(16777216),
                    CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
                )
                """)

                # Create Cortex Search service with repository filtering
                logger.info("Creating or replacing Cortex Search service...")
                cursor.execute("""
                CREATE OR REPLACE CORTEX SEARCH SERVICE CODE_SEARCH_SERVICE
                ON chunk
                ATTRIBUTES language, file_url, repository
                WAREHOUSE = CODE_EXPERT_WH
                TARGET_LAG = '1 minute'
                AS (
                    SELECT 
                        chunk,
                        relative_path,
                        file_url,
                        language,
                        CASE 
                            WHEN file_url LIKE 'file://%' 
                            THEN REGEXP_SUBSTR(file_url, 'file://([^/]+)', 1, 1, 'e', 1)
                            ELSE 'unknown'
                        END as repository
                    FROM CODE_CHUNKS_TABLE
                )
                """)
                
                self.conn.commit()
                logger.info("Database, table and search service initialized successfully")
            except Exception as e:
                self.conn.rollback()
                logger.error(f"Error initializing search: {e}")
                raise

    async def store_code_chunk(self, repo_name: str, file_path: str, content: str, language: str):
        """Store code chunk in Snowflake table."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                file_url = f"file://{repo_name}/{file_path}"
                cursor.execute("""
                INSERT INTO CODE_CHUNKS_TABLE (
                    RELATIVE_PATH,
                    FILE_URL,
                    CHUNK,
                    LANGUAGE
                ) VALUES (%s, %s, %s, %s)
                """, (file_path, file_url, content, language))
                logger.info(f"Successfully stored chunk for {file_path}")
            except Exception as e:
                logger.error(f"Error storing chunk: {e}")
                raise

    async def search_code(self, query: str, language: Optional[str] = None, limit: int = 5) -> list:
        """Search code using Cortex Search."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                filter_json = (
                    f', "filter": {{"@eq": {{"language": "{language}"}}}}' 
                    if language else ''
                )
                
                results = cursor.execute(f"""
                SELECT PARSE_JSON(
                    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                        'CODE_SEARCH_SERVICE',
                        '{{
                            "query": "{query}",
                            "columns": ["chunk", "file_url", "language"],
                            "limit": {limit}{filter_json}
                        }}'
                    )
                )['results'] as results
                """).fetchone()
                
                return results[0] if results else []
            except Exception as e:
                logger.error(f"Error searching code: {e}")
                raise

    async def search_and_respond(self, query: str, repo_name: str) -> str:
        """Search code and get AI response using Cortex Search and Mistral."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                logger.info(f"Executing search and completion for query: {query}")
                
                # Prepare the search query with repository filter
                search_query = {
                    "query": query,
                    "columns": ["chunk", "file_url", "language"],
                    "filter": {
                        "@eq": {
                            "repository": repo_name
                        }
                    },
                    "limit": 10
                }
                
                cursor.execute("""
                WITH search_results AS (
                    SELECT PARSE_JSON(
                        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                            'CODE_SEARCH_SERVICE',
                            %s
                        )
                    )['results'] as results
                )
                SELECT SNOWFLAKE.CORTEX.COMPLETE(
                    'mistral-large2',
                    'You are analyzing code from the GitHub repository "' || %s || '". ' ||
                    'Only discuss code and files from this specific repository. ' ||
                    'Based on these code chunks: ' || results::STRING || 
                    ' Answer this specific question: ' || %s || 
                    ' Only reference files and functionality that exist in the provided code chunks.'
                ) AS response
                FROM search_results;
                """, (json.dumps(search_query), repo_name, query))
                
                result = cursor.fetchone()
                if result and result[0]:
                    logger.info("Successfully generated response")
                    return result[0]
                
                logger.warning("No response generated from query")
                return "I couldn't find enough information in this repository to answer that question. Please ask about something specific to this repository's code."
                
            except Exception as e:
                logger.error(f"Error in search_and_respond: {str(e)}")
                raise RuntimeError("An error occurred while processing your query. Please try again.")
            
    async def get_repository_statistics(self, repo_name: str) -> Dict:
        """Get statistics for a repository."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                logger.info(f"Fetching statistics for repository: {repo_name}")
                cursor.execute("""
                SELECT 
                    COUNT(*) as total_chunks,
                    COUNT(DISTINCT relative_path) as total_files,
                    MIN(CREATED_AT) as first_indexed,
                    MAX(CREATED_AT) as last_indexed
                FROM CODE_CHUNKS_TABLE
                WHERE relative_path LIKE %s
                """, (f"%{repo_name}%",))
            
                row = cursor.fetchone()
                if row:
                    stats = {
                        'total_chunks': row[0],
                        'total_files': row[1],
                        'first_indexed': row[2],
                        'last_indexed': row[3]
                    }
                    logger.info(f"Retrieved repository statistics: {stats}")
                    return stats
                
                logger.warning(f"No statistics found for repository: {repo_name}")
                return {
                    'total_chunks': 0,
                    'total_files': 0,
                    'first_indexed': None,
                    'last_indexed': None
                }
            except Exception as e:
                logger.error(f"Error getting repository statistics: {e}")
                raise
    async def get_processed_repositories(self) -> List[Dict]:
        """Retrieve list of all processed repositories."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
            # Query distinct repositories from CODE_CHUNKS_TABLE instead of PROCESSED_REPOSITORIES
                cursor.execute("""
                 SELECT DISTINCT
                REGEXP_SUBSTR(file_url, 'file://([^/]+)', 1, 1, 'e', 1) as repo_name,
                MIN(CREATED_AT) as last_processed_at,
                COUNT(DISTINCT RELATIVE_PATH) as total_files,
                COUNT(*) as total_chunks
            FROM CODE_CHUNKS_TABLE
            WHERE file_url LIKE 'file://%'
            GROUP BY repo_name
            ORDER BY last_processed_at DESC
            """)
            
                repositories = []
                for row in cursor.fetchall():
                    if row[0]:  # if repo_name exists
                        repositories.append({
                        'owner': 'owner',  # Default owner since we don't store it
                        'repo_name': row[0],
                        'last_processed_at': row[1],
                        'total_files': row[2],
                        'total_chunks': row[3],
                        'status': 'active'
                    })
                return repositories
            except Exception as e:
                logger.error(f"Error retrieving processed repositories: {e}")
                raise

    async def add_or_update_repository(self, owner: str, repo_name: str, total_files: int = 0, total_chunks: int = 0):
        """Add or update a repository in the tracking table."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                # Generate repo_id
                repo_id = f"{owner}/{repo_name}"
            
                cursor.execute("""
                MERGE INTO PROCESSED_REPOSITORIES AS target
                USING (SELECT %s AS REPO_ID, %s AS OWNER, %s AS REPO_NAME) AS source
            ON target.OWNER = source.OWNER AND target.REPO_NAME = source.REPO_NAME
            WHEN MATCHED THEN
                UPDATE SET 
                    LAST_PROCESSED_AT = CURRENT_TIMESTAMP(),
                    STATUS = 'active',
                    TOTAL_FILES = %s,
                    TOTAL_CHUNKS = %s
            WHEN NOT MATCHED THEN
                INSERT (REPO_ID, OWNER, REPO_NAME, TOTAL_FILES, TOTAL_CHUNKS)
                VALUES (source.REPO_ID, source.OWNER, source.REPO_NAME, %s, %s)
            """, (repo_id, owner, repo_name, total_files, total_chunks, total_files, total_chunks))
            
                logger.info(f"Successfully updated repository tracking for {repo_id}")
            except Exception as e:
                logger.error(f"Error updating repository tracking: {e}")
                raise

    async def check_repository_exists(self, owner: str, repo_name: str) -> bool:
        """Check if a repository exists in the tracking table."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
            SELECT COUNT(*)
            FROM PROCESSED_REPOSITORIES
            WHERE OWNER = %s 
            AND REPO_NAME = %s 
            AND STATUS = 'active'
            """, (owner, repo_name))
            
                count = cursor.fetchone()[0]
                return count > 0
            except Exception as e:
                logger.error(f"Error checking repository existence: {e}")
                raise

    async def archive_repository(self, owner: str, repo_name: str):
        """Archive a repository (soft delete)."""
        self._ensure_connection()
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
            UPDATE PROCESSED_REPOSITORIES
            SET STATUS = 'archived'
            WHERE OWNER = %s AND REPO_NAME = %s
            """, (owner, repo_name))
            
                logger.info(f"Successfully archived repository {owner}/{repo_name}")
            except Exception as e:
                logger.error(f"Error archiving repository: {e}")
                raise

    def _ensure_connection(self):
        """Ensure the connection to Snowflake is active."""
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            logger.info("Reconnecting to Snowflake...")
            self._connect()

    async def close(self):
        """Close the Snowflake connection."""
        if self.conn:
            try:
                self.conn.close()
                logger.info("Snowflake connection closed successfully")
            except Exception as e:
                logger.error(f"Error closing Snowflake connection: {e}")