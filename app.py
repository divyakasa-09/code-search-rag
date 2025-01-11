import os
import sys


# Add the project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.services.repository_ingestion import RepositoryProcessor
from app.services.snowflake import SnowflakeSearchService



import re
import streamlit as st
import asyncio
import logging
from typing import Tuple, Optional
from app.core.config import get_settings
logger = logging.getLogger(__name__)
settings = get_settings()

def initialize_session_state():
    """Initialize or reset session state variables."""
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'current_progress' not in st.session_state:
        st.session_state.current_progress = 0
    if 'progress_file' not in st.session_state:
        st.session_state.progress_file = ""
    if 'error' not in st.session_state:
        st.session_state.error = None
    if 'messages' not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "👋 Hi! I'm your code repository assistant. You can either:\n"
             "1. Process a new GitHub repository by entering its URL above, or\n"
             "2. Select a previously processed repository from the dropdown to start chatting about it."}
        ]

def parse_github_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract owner and repository name from GitHub URL."""
    pattern = r"github\.com/([^/]+)/([^/]+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2)
    return None

async def process_repository(owner: str, repo: str):
    """Process repository and show progress."""
    st.session_state.processing = True
    st.session_state.current_progress = 0
    st.session_state.progress_file = ""
    st.session_state.error = None

    processor = RepositoryProcessor(batch_size=2)

    async def progress_callback(current: int, total: int, file_path: str):
        st.session_state.current_progress = current
        st.session_state.total_files = total
        st.session_state.progress_file = file_path

    processor.set_callback(progress_callback)

    try:
        success = await processor.ingest_repository(owner, repo)
        if success:
            st.success("Repository processed successfully!")
        else:
            st.error("Failed to process repository. Check the logs for more details.")
    except Exception as e:
        st.error(f"Error processing repository: {str(e)}")
        st.session_state.error = str(e)
    finally:
        st.session_state.processing = False
        st.session_state.progress_file = ""
        await processor.cleanup()

async def load_processed_repositories():
    """Load processed repositories from Snowflake."""
    try:
        snowflake = SnowflakeSearchService()
        repos = await snowflake.get_processed_repositories()
        snowflake.close()  # Remove await here since close() is not async
        return repos
    except Exception as e:
        logger.error(f"Error loading repositories: {str(e)}")
        return []

def main():
    st.title("Code Repository Assistant")
    
    # Initialize session state
    initialize_session_state()
    
    # Load processed repositories using asyncio.run
    try:
        repos = asyncio.run(load_processed_repositories())
        repo_options = [f"{repo['owner']}/{repo['repo_name']}" for repo in repos] if repos else []
    except Exception as e:
        st.error(f"Error loading repositories: {str(e)}")
        repo_options = []
    
    # Create two columns for repository input
    col1, col2 = st.columns([2, 1])
    
    with col1:
        repo_url = st.text_input(
            "Enter GitHub Repository URL",
            placeholder="https://github.com/owner/repo"
        )
    
    with col2:
        if st.button("Process Repository", disabled=st.session_state.processing):
            repo_info = parse_github_url(repo_url)
            if repo_info:
                owner, repo = repo_info
                try:
                    asyncio.run(process_repository(owner, repo))
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {str(e)}")
            else:
                st.error("Invalid GitHub URL")

    # Show processing progress
    if st.session_state.processing:
        st.info("Processing repository...")
        progress_placeholder = st.empty()
        
        if st.session_state.total_files > 0:
            progress = min(st.session_state.current_progress / st.session_state.total_files, 1.0)
            progress_placeholder.progress(progress)
            st.text(f"Processed {st.session_state.current_progress} of {st.session_state.total_files} files")
            if st.session_state.progress_file:
                st.text(f"Current file: {st.session_state.progress_file}")

    # Repository selection dropdown
    if repo_options:
        selected_repo = st.selectbox(
            "Select a repository to chat about",
            options=repo_options,
            index=0 if repo_options else None
        )
        
        if selected_repo:
            st.divider()
            
            # Chat interface
            st.subheader(f"Chat about {selected_repo}")
            
            # Display chat messages
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # Chat input
           
            # Inside main() function, in the chat response section:
            if prompt := st.chat_input("Ask about the code"):
            # Add user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)

    # Generate and display assistant response
                with st.chat_message("assistant"):
                    try:
                        with st.spinner("Analyzing repository code..."):
                            owner, repo = selected_repo.split('/')
                            snowflake = SnowflakeSearchService()
                # Pass repository name to search_and_respond
                            response = asyncio.run(snowflake.search_and_respond(prompt, repo))
                            asyncio.run(snowflake.close())   # Use await here

                            if response:
                               st.session_state.messages.append({"role": "assistant", "content": response})
                               st.markdown(response)
                            else:
                               error_msg = f"I couldn't find relevant information in the {repo} repository. Could you rephrase your question?"
                               st.error(error_msg)
                               st.session_state.messages.append({"role": "assistant", "content": error_msg})
                    except Exception as e:
                            error_msg = "An error occurred while analyzing the code. Please try again."
                            st.error(error_msg)
                            st.session_state.messages.append({"role": "assistant", "content": error_msg})
                            logger.error(f"Error processing chat query: {str(e)}")
                    finally:
                        try:
                            asyncio.run(snowflake.close())  # Use await here
                        except Exception as e:
                             logger.error(f"Error closing Snowflake connection: {e}")
    else:
        st.info("No repositories processed yet. Enter a GitHub URL above to get started!")

if __name__ == "__main__":
    main()