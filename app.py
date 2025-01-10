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
from app.core.config import get_settings
logger = logging.getLogger(__name__)
settings = get_settings()

# Initialize session state variables
if 'repositories' not in st.session_state:
    st.session_state.repositories = []
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'current_progress' not in st.session_state:
    st.session_state.current_progress = 0
if 'progress_file' not in st.session_state:
    st.session_state.progress_file = ""
if 'error' not in st.session_state:
    st.session_state.error = None
if 'total_files' not in st.session_state:
    st.session_state.total_files = 0
if 'messages' not in st.session_state:
    st.session_state.messages = []

def parse_github_url(url: str):
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
            repo_key = f"{owner}/{repo}"
            if repo_key not in st.session_state.repositories:
                st.session_state.repositories.append(repo_key)

            snowflake = SnowflakeSearchService()
            stats = await snowflake.get_repository_statistics(repo)
            await snowflake.close()

            st.success("Repository processed successfully!")
            st.json({
                "Total Files": stats['total_files'],
                "Total Chunks": stats['total_chunks'],
                "First Indexed": str(stats['first_indexed']),
                "Last Indexed": str(stats['last_indexed'])
            })
        else:
            st.error("Failed to process repository. Check the logs for more details.")
    except Exception as e:
        st.error(f"Error processing repository: {str(e)}")
        st.session_state.error = str(e)
    finally:
        st.session_state.processing = False
        st.session_state.progress_file = ""
        await processor.cleanup()

def main():
    st.title("Code Repository Assistant")
    st.subheader("GitHub Repository Analysis")

    # Repository URL input
    repo_url = st.text_input("Enter GitHub Repository URL", 
                            placeholder="https://github.com/owner/repo")

    # Repository dropdown
    selected_repo = None
    if st.session_state.repositories:
        selected_repo = st.selectbox(
            "Or select a processed repository",
            options=st.session_state.repositories
        )

    # Process button
    if repo_url and st.button("Process Repository"):
        repo_info = parse_github_url(repo_url)
        if repo_info:
            owner, repo = repo_info
            try:
                asyncio.run(process_repository(owner, repo))
                st.rerun()
            except Exception as e:
                st.error(f"Error: {str(e)}")

    # Show progress during processing
    if st.session_state.processing:
        st.info("Processing repository... Please wait.")
        
        if st.session_state.progress_file:
            st.text(f"Processing: {st.session_state.progress_file}")
        
        if st.session_state.total_files > 0:
            progress = min(st.session_state.current_progress / st.session_state.total_files, 1.0)
            st.progress(progress)
            st.text(f"Processed {st.session_state.current_progress} of {st.session_state.total_files} files")

    # Show repository stats and chat interface if a repository is selected
    if st.session_state.repositories and selected_repo:
        st.subheader("Repository Information")
        owner, repo = selected_repo.split('/')

        try:
            snowflake = SnowflakeSearchService()
            stats = asyncio.run(snowflake.get_repository_statistics(repo))
            
            st.write("Statistics:")
            st.json({
                "Total Files": stats['total_files'],
                "Total Chunks": stats['total_chunks'],
                "First Indexed": str(stats['first_indexed']),
                "Last Indexed": str(stats['last_indexed'])
            })

            # Chat interface
            st.subheader(f"Chat about {selected_repo}")
            
            # Display chat messages
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # Chat input
            if prompt := st.chat_input("Ask about the code"):
                # Add user message
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                # Generate and display assistant response
                with st.chat_message("assistant"):
                    try:
                        with st.spinner("Analyzing repository code..."):
                            snowflake = SnowflakeSearchService()
                            response = asyncio.run(snowflake.search_and_respond(prompt))
                            asyncio.run(snowflake.close())
                            
                            if response:
                                st.session_state.messages.append({"role": "assistant", "content": response})
                                st.markdown(response)
                            else:
                                error_msg = "I couldn't analyze the code properly. Please try asking a different question."
                                st.error(error_msg)
                                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                                
                    except Exception as e:
                        error_msg = "An error occurred while analyzing the code. Please try again."
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
                        logger.error(f"Error processing chat query: {str(e)}")
                    finally:
                        asyncio.run(snowflake.close())

        except Exception as e:
            st.error(f"Error fetching repository statistics: {str(e)}")

if __name__ == "__main__":
    main()