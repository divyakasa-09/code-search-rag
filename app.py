import os
import sys
import time
import re
import streamlit as st
import asyncio
import logging
from typing import Tuple, Optional
import pandas as pd
import json
from streamlit import components

# Add the project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import application-specific modules
from app.services.repository_ingestion import RepositoryProcessor
from app.services.snowflake import SnowflakeSearchService
from evaluations.trulens_eval import RAGEvaluator, FilteredRAGEvaluator

# Configure logging
logger = logging.getLogger(__name__)

# Initialize settings
from app.core.config import get_settings
settings = get_settings()

# Streamlit cache for resource-heavy initializations
@st.cache_resource
def initialize_evaluators():
    try:
        snowflake_service = SnowflakeSearchService()
        base_rag = RAGEvaluator(snowflake_service)  # Instantiating Base RAG
        filtered_rag = FilteredRAGEvaluator(snowflake_service)  # Instantiating Filtered RAG
        return base_rag, filtered_rag
    except Exception as e:
        st.error(f"Error initializing evaluators: {str(e)}")
        return None, None

# Initialize session state variables
def initialize_session_state():
    if 'loading' not in st.session_state:
        st.session_state.loading = True
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
    if 'metrics_history' not in st.session_state:
        st.session_state.metrics_history = {"experiments": []}

def parse_github_url(url: str) -> Optional[Tuple[str, str]]:
    """Extract owner and repository name from GitHub URL."""
    pattern = r"github.com/([^/]+)/([^/]+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1), match.group(2)
    return None

# Process repository and update progress
async def process_repository(owner: str, repo: str):
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

# Load processed repositories from Snowflake
async def load_processed_repositories():
    snowflake = None
    try:
        snowflake = SnowflakeSearchService()
        repos = await snowflake.get_processed_repositories()
        return repos
    except Exception as e:
        logger.error(f"Error loading repositories: {str(e)}")
        return []
    finally:
        if snowflake:
            snowflake.close()

# Display repository processing status
def display_processing_status():
    if st.session_state.processing:
        st.info("Processing repository...")
        if hasattr(st.session_state, 'total_files'):
            progress = st.session_state.current_progress / st.session_state.total_files
            st.progress(progress)
            st.text(f"Processing file: {st.session_state.progress_file}")
    elif st.session_state.error:
        st.error(f"Error: {st.session_state.error}")

# Render the TruLens evaluation dashboard
def render_comparison_dashboard(base_rag, filtered_rag):
    """Render the comparison dashboard using Streamlit components."""
    st.divider()
    st.subheader("RAG Evaluation Dashboard")
    
    # Get metrics history from both evaluators
    base_metrics = base_rag.metrics_history.get("experiments", [])
    filtered_metrics = filtered_rag.metrics_history.get("experiments", [])
    
    # Create tabs for different views
    tab1, tab2, tab3 = st.tabs(["Performance Comparison", "Metrics Over Time", "Detailed Stats"])
    
    with tab1:
        st.subheader("Average Metrics Comparison")
        
        # Calculate averages
        def calculate_averages(metrics):
            if not metrics:
                return {"context_relevance": 0, "groundedness": 0, "answer_relevance": 0}
            return {
                "context_relevance": sum(m.get("context_relevance", 0) for m in metrics) / len(metrics),
                "groundedness": sum(m.get("groundedness", 0) for m in metrics) / len(metrics),
                "answer_relevance": sum(m.get("answer_relevance", 0) for m in metrics) / len(metrics)
            }
        
        base_avg = calculate_averages(base_metrics)
        filtered_avg = calculate_averages(filtered_metrics)
        
        # Display metrics side by side
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Base RAG - Context Relevance", f"{base_avg['context_relevance']:.3f}")
            st.metric("Base RAG - Groundedness", f"{base_avg['groundedness']:.3f}")
            st.metric("Base RAG - Answer Relevance", f"{base_avg['answer_relevance']:.3f}")
        
        with col2:
            st.metric("Filtered RAG - Context Relevance", 
                     f"{filtered_avg['context_relevance']:.3f}",
                     f"{filtered_avg['context_relevance'] - base_avg['context_relevance']:.3f}")
            st.metric("Filtered RAG - Groundedness", 
                     f"{filtered_avg['groundedness']:.3f}",
                     f"{filtered_avg['groundedness'] - base_avg['groundedness']:.3f}")
            st.metric("Filtered RAG - Answer Relevance", 
                     f"{filtered_avg['answer_relevance']:.3f}",
                     f"{filtered_avg['answer_relevance'] - base_avg['answer_relevance']:.3f}")
    
    with tab2:
        st.subheader("Metrics Over Time")
        
        # Prepare data for line chart
        chart_data = {
            "Base RAG": base_metrics,
            "Filtered RAG": filtered_metrics
        }
        
        # Create separate charts for each metric
        metrics = ["context_relevance", "groundedness", "answer_relevance"]
        metric_names = ["Context Relevance", "Groundedness", "Answer Relevance"]
        
        for metric, name in zip(metrics, metric_names):
            st.subheader(f"{name} Over Time")
            
            # Create dataframe for this metric
            data = []
            for rag_type, metrics_list in chart_data.items():
                for m in metrics_list:
                    data.append({
                        "timestamp": pd.to_datetime(m.get("timestamp", 0), unit='s'),
                        "value": m.get(metric, 0),
                        "type": rag_type
                    })
            
            if data:
                df = pd.DataFrame(data)
                st.line_chart(df.pivot(index='timestamp', columns='type', values='value'))
    
    with tab3:
        st.subheader("Detailed Statistics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("Base RAG Stats")
            st.write(f"Total Queries: {len(base_metrics)}")
            if base_metrics:
                st.write(f"Success Rate: {sum(1 for m in base_metrics if m.get('context_relevance', 0) > 0.7) / len(base_metrics):.2%}")
        
        with col2:
            st.write("Filtered RAG Stats")
            st.write(f"Total Queries: {len(filtered_metrics)}")
            if filtered_metrics:
                st.write(f"Success Rate: {sum(1 for m in filtered_metrics if m.get('context_relevance', 0) > 0.7) / len(filtered_metrics):.2%}")
        
        # Add explanation
        st.markdown("""
        ### Metrics Explanation
        - **Context Relevance**: Measures how well the retrieved code chunks match the query
        - **Groundedness**: Evaluates if the response is based on the actual code content
        - **Answer Relevance**: Assesses how well the response answers the query
        
        ### Improvements in Filtered RAG
        1. **Quality Threshold**: Filters out low-quality matches
        2. **Stricter Relevance**: Uses multiple factors to evaluate content
        3. **Smart Fallback**: Uses Base RAG when needed
        """)
        
        # Add experiment controls
        st.subheader("Experiment Settings")
        quality_threshold = st.slider(
            "Filtered RAG Quality Threshold",
            min_value=0.0,
            max_value=1.0,
            value=0.6,
            step=0.05
        )
        
        if st.button("Update Threshold"):
            filtered_rag.set_quality_threshold(quality_threshold)
            st.success(f"Updated quality threshold to {quality_threshold}")

# Main application function
def main():
    st.title("Code Repository Assistant")

    # Initialize session state
    initialize_session_state()

    # Initialize loading placeholder
    loading_placeholder = st.empty()

    # Show loading indicator during initialization
    if st.session_state.loading:
        with loading_placeholder.container():
            st.markdown("### Loading Code Repository Assistant")
            st.progress(0.75, "Initializing services and loading repositories...")
            st.info("Setting up connection to Snowflake and loading repository data...")

    # Load processed repositories
    try:
        repos = asyncio.run(load_processed_repositories())
        repo_options = [f"{repo['owner']}/{repo['repo_name']}" for repo in repos] if repos else []
        st.session_state.loading = False
        loading_placeholder.empty()
    except Exception as e:
        st.error(f"Error loading repositories: {str(e)}")
        repo_options = []
        st.session_state.loading = False
        loading_placeholder.empty()

    if not st.session_state.loading:
        # Repository input and processing UI
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
                    asyncio.run(process_repository(owner, repo))
                    st.rerun()
                else:
                    st.error("Invalid GitHub URL")

        # Display processing status
        display_processing_status()

        # Repository selection and chat interface
        if repo_options:
            selected_repo = st.selectbox(
                "Select a repository to chat about",
                options=repo_options,
                index=0 if repo_options else None
            )

            if selected_repo:
                st.divider()

                # Initialize evaluators
                base_rag, filtered_rag = initialize_evaluators()

                # Add experiment type selector
                experiment_type = st.radio(
                    "Select RAG version:",
                    ["Base RAG", "Filtered RAG (with quality threshold)"],
                    key="rag_version"
                )

                # Chat interface
                st.subheader(f"Chat about {selected_repo}")

                # Display chat history
                for message in st.session_state.messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])

                # Chat input and response
                if prompt := st.chat_input("Ask about the code"):
                # Add user message
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    with st.chat_message("user"):
                       st.markdown(prompt)

                # Generate and display assistant response
                    with st.chat_message("assistant"):
                        try:
                        # Get repository name from selected_repo
                            repo_name = selected_repo.split('/')[-1] if selected_repo else None
                        
                        # Process query based on selected experiment type
                            if experiment_type == "Base RAG":
                                result = asyncio.run(base_rag.process_query(prompt, "baseline", repo_name))
                            else:
                                result = asyncio.run(filtered_rag.process_query(prompt, "filtered", repo_name))

                            response = result["response"]
                            metrics = result["metrics"]

                        # Display response
                            st.markdown(response)

                        # Show metrics in expander
                            with st.expander("Query Metrics"):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Context Relevance", f"{metrics['context_relevance']:.3f}")
                                with col2:
                                    st.metric("Groundedness", f"{metrics['groundedness']:.3f}")
                                with col3:
                                    st.metric("Answer Relevance", f"{metrics['answer_relevance']:.3f}")

                        # Add response to chat history
                            st.session_state.messages.append({"role": "assistant", "content": response})

                        # Update metrics history
                            if hasattr(st.session_state, 'metrics_history'):
                                st.session_state.metrics_history["experiments"].append({
                                "timestamp": time.time(),
                                **metrics
                                })

                        except Exception as e:
                            error_msg = f"An error occurred while analyzing the code: {str(e)}"
                            st.error(error_msg)
                            st.session_state.messages.append({"role": "assistant", "content": error_msg})
                            logger.error(f"Error processing chat query: {str(e)}")
                st.divider()  # Add a visual separator
                if st.checkbox("Show Evaluation Summary"):
                    try:
                        render_comparison_dashboard(base_rag, filtered_rag)
                    except Exception as e:
                        st.error(f"Error displaying evaluation summary: {str(e)}")           

if __name__ == "__main__":
    main()
 