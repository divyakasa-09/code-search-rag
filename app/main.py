import streamlit as st
import asyncio
import time
import re
from typing import Tuple, Optional
import json
from streamlit import components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import logging
import os
import sys

from app.services.repository_ingestion import RepositoryProcessor
from app.services.snowflake import SnowflakeSearchService
from evaluations.trulens_eval import RAGEvaluator, FilteredRAGEvaluator
from app.core.config import get_settings

# Configure logging
logger = logging.getLogger(__name__)

# Initialize settings
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
    """Enhanced dashboard with more detailed TruLens metrics visualization."""
    st.divider()
    st.subheader("🎯 RAG Evaluation Dashboard")
    
    # Get metrics history from both evaluators
    base_metrics = base_rag.metrics_history.get("experiments", [])
    filtered_metrics = filtered_rag.metrics_history.get("experiments", [])
    
    # Create tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Performance Comparison", "📈 Metrics Over Time", "🔍 Detailed Analysis"])
    
    with tab1:
        st.markdown("### Real-time RAG Performance Comparison")
        
        # Calculate averages for both RAG versions
        def calculate_averages(metrics):
            if not metrics:
                return {
                    "context_relevance": 0,
                    "groundedness": 0,
                    "answer_relevance": 0,
                    "response_quality": 0,
                    "filter_stats": {}
                }
            return {
                "context_relevance": sum(m.get("context_relevance", 0) for m in metrics) / len(metrics),
                "groundedness": sum(m.get("groundedness", 0) for m in metrics) / len(metrics),
                "answer_relevance": sum(m.get("answer_relevance", 0) for m in metrics) / len(metrics),
                "response_quality": sum(m.get("response_quality", 0) for m in metrics) / len(metrics),
                "filter_stats": metrics[-1].get("filter_stats", {}) if metrics else {}
            }
        
        base_avg = calculate_averages(base_metrics)
        filtered_avg = calculate_averages(filtered_metrics)
        
        # Create comparison DataFrame
        metrics_data = pd.DataFrame({
            'Metric': ['Context Relevance', 'Groundedness', 'Answer Relevance', 'Response Quality'],
            'Base RAG': [
                base_avg['context_relevance'],
                base_avg['groundedness'],
                base_avg['answer_relevance'],
                base_avg.get('response_quality', 0)
            ],
            'Filtered RAG': [
                filtered_avg['context_relevance'],
                filtered_avg['groundedness'],
                filtered_avg['answer_relevance'],
                filtered_avg.get('response_quality', 0)
            ]
        })
        
        # Calculate improvements
        metrics_data['Improvement'] = metrics_data['Filtered RAG'] - metrics_data['Base RAG']
        metrics_data['Improvement %'] = (metrics_data['Improvement'] / metrics_data['Base RAG'] * 100).round(2)
        
        # Display metrics with color coding
        st.dataframe(
            metrics_data.style.format({
                'Base RAG': '{:.3f}',
                'Filtered RAG': '{:.3f}',
                'Improvement': '{:+.3f}',
                'Improvement %': '{:+.2f}%'
            }).background_gradient(
                subset=['Improvement'],
                cmap='RdYlGn',
                vmin=-0.1,
                vmax=0.1
            ),
            height=200
        )
        
      
    
    with tab2:
        st.markdown("### 📈 Metrics Over Time")
        
        if base_metrics or filtered_metrics:
            # Prepare time series data
            experiment_data = []
            for exp in (base_metrics + filtered_metrics):
                experiment_data.append({
                    'Timestamp': pd.to_datetime(exp['timestamp'], unit='s'),
                    'Type': 'Filtered RAG' if exp.get('mode') == 'filtered' else 'Base RAG',
                    'Context Relevance': exp['context_relevance'],
                    'Groundedness': exp['groundedness'],
                    'Answer Relevance': exp['answer_relevance'],
                    'Has Code': exp.get('has_code', False),
                    'Query Length': exp.get('query_length', 0),
                    'Response Length': exp.get('response_length', 0)
                })
            
            if experiment_data:
                exp_df = pd.DataFrame(experiment_data)
                
               
                
                
                # Show detailed experiment history with table
                st.subheader("Recent Experiments")
                styled_df = exp_df.sort_values('Timestamp', ascending=False).style.format({
                    'Context Relevance': '{:.3f}',
                    'Groundedness': '{:.3f}',
                    'Answer Relevance': '{:.3f}',
                    'Timestamp': lambda x: x.strftime('%Y-%m-%d %H:%M:%S')
                })
                
                st.dataframe(
                    styled_df,
                    height=300
                )
                
                # Add experiment statistics
                st.subheader("Experiment Statistics")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Experiments", len(experiment_data))
                    st.metric("Base RAG Experiments", 
                             len([e for e in experiment_data if e['Type'] == 'Base RAG']))
                with col2:
                    st.metric("Filtered RAG Experiments",
                             len([e for e in experiment_data if e['Type'] == 'Filtered RAG']))
                   
                  
                
               
            
        else:
            st.info("No metrics data available yet. Try asking some questions to see the trends!")

    
    with tab3:
        st.markdown("### 🔍 Detailed Analysis")
        
        # Query characteristics
        if filtered_metrics:
            st.markdown("#### Query Analysis")
            
            avg_query_length = sum(m.get('query_length', 0) for m in filtered_metrics) / len(filtered_metrics)
            avg_response_length = sum(m.get('response_length', 0) for m in filtered_metrics) / len(filtered_metrics)
            code_responses = sum(1 for m in filtered_metrics if m.get('has_code', False))
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Avg Query Length", f"{avg_query_length:.1f} words")
            with col2:
                st.metric("Avg Response Length", f"{avg_response_length:.1f} words")
            with col3:
                st.metric("Responses with Code", f"{code_responses}/{len(filtered_metrics)}")
        
      
       
            
        # Add explanation
        st.markdown("""
        ### 📚 Metrics Explanation
        - **Context Relevance**: How well retrieved code chunks match the query
        - **Groundedness**: Whether responses are based on actual code content
        - **Answer Relevance**: How well responses address the query
        - **Response Quality**: Overall response effectiveness
        
        ### 🔍 Filter Effectiveness
        - Higher filter rates with good relevance scores indicate effective filtering
        - Lower filter rates might suggest the threshold needs adjustment
        - Monitor the trade-off between quality and coverage
        """)
        
      
       
       

# Main application function
def main():
    st.set_page_config(
        page_title="Code Expert",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="auto"
    )

    # Enhanced CSS styling
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        /* Global Styles */
        .stApp {
            background-color: #f8f9fa;
            font-family: 'Inter', sans-serif;
        }

        /* Main Header */
        .main-header {
            background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
            padding: 2.5rem;
            border-radius: 12px;
            color: white;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .main-header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }

        .main-header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }

        /* Repository Section */
        .repo-section {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            margin-bottom: 2rem;
            border: 1px solid #e5e7eb;
        }

        /* Input Fields */
        .stTextInput > div > div {
            border: 1px solid #e5e7eb !important;
            border-radius: 8px !important;
            padding: 1rem !important;
            background: white !important;
            align-items: center;
            justify-content: center; 
            text-align: center;         
        }

        .stTextInput > div > div:focus-within {
            border-color: #2563EB !important;
            box-shadow: 0 0 0 2px rgba(79, 70, 235, 0.2) !important;
        }

        /* Buttons */
        .stButton > button {
            background: white !important;
            color: #1E3A8A !important;
            padding: 0.75rem 1.5rem !important;
            border: 2px solid #D1D5DB !important;
            border-radius: 8px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease !important;
            width: auto !important;
            min-width: 200px;
            cursor: pointer;
        }

        .stButton > button:hover {
            border-color: #1E3A8A !important;
            color: #1E3A8A !important; 
            background: white !important;
            transform: translateY(-1px) !important; 
        }

        /* Chat Messages */
        .chat-message {
           padding: 1.25rem;
            border-radius: 12px;
            margin-bottom: 1rem;
           border: 1px solid #e5e7eb;
           box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
            background: #F5F5F5 !important;  /* Subtle light gray */
            }
                
        [data-testid="user-chat-message"] .chat-message.user-message {
               background: #F5F5F5 !important;
             
            }
        [data-testid="assistant-chat-message"] .chat-message.assistant-message {
              background: #F5F5F5 !important;
            
           }
                
        @keyframes fadeIn {
         from { opacity: 0; transform: translateY(10px); }
         to { opacity: 1; transform: translateY(0); } 
          } 
                      
        .user-message {
            background: #F5F5F5 !important;
          
        }

        .assistant-message {
            background: #F5F5F5 !important;
           
        }

        /* Code Blocks */
        .code-block {
            background: #1E1E1E;
            border-radius: 8px;
            margin: 1rem 0;
            overflow: hidden;
        }

        .code-header {
            background: #2D2D2D;
            padding: 0.75rem 1rem;
            color: #E0E0E0;
            font-size: 0.9rem;
            border-bottom: 1px solid #404040;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .code-content {
            padding: 1rem;
            margin: 0;
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            line-height: 1.6;
            color: #D4D4D4;
            overflow-x: auto;
        }

        /* Loading Animation */
        .loading-ring {
            display: inline-block;
            width: 30px;
            height: 30px;
            border: 3px solid #f3f3f3;
            border-radius: 50%;
            border-top: 3px solid #4F46E5;
            animation: spin 1s linear infinite;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Progress Bar */
        .stProgress > div > div > div {
            background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        }

        /* Select Box */
        .stSelectbox > div > div {
            border: 1px solid #e5e7eb !important;
            border-radius: 8px !important;
            background: white !important;
        }

        .stSelectbox > div > div:focus-within {
            border-color: #4F46E5 !important;
            box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.2) !important;
        }
                 
        
        </style>
    """, unsafe_allow_html=True)

    # Enhanced Header
    # Update the banner section in your main() function
    st.markdown("""
         <style>
         /* Banner Container */
        .banner-container {
    background: linear-gradient(135deg, #93C5FD 0%, #60A5FA 100%);
    border-radius: 16px;
    padding: 2rem;
    position: relative;
    overflow: hidden;
    margin-bottom: 2rem;
    box-shadow: 0 10px 30px rgba(96, 165, 250, 0.2);
  }
    
        /* Background Pattern */
    .banner-pattern {
        position: absolute;
        top: 0;
        right: 0;
        bottom: 0;
        left: 0;
        opacity: 0.1;
        background-image: radial-gradient(circle at 2px 2px, white 1px, transparent 0);
        background-size: 24px 24px;
    }
    
    /* Content Container */
    .banner-content {
        position: relative;
        z-index: 1;
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    
    /* Logo Container */
    .logo-container {
        background: rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 1rem;
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Text Content */
    .banner-text {
        flex: 1;
    }
    
    .banner-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: white !important;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .beta-tag {
        background: rgba(255, 255, 255, 0.2);
        color: white;
        font-size: 0.875rem;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 500;
    }
    
    .banner-subtitle {
        color: rgba(255, 255, 255, 0.9);
        font-size: 1.1rem;
        margin: 0.5rem 0 0 0;
    }
    </style>
    
    <div class="banner-container">
        <div class="banner-pattern"></div>
        <div class="banner-content">
            <div class="logo-container">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
                    <polyline points="14 2 14 8 20 8"/>
                    <path d="M8 13h8"/>
                    <path d="M8 17h8"/>
                    <path d="M8 9h3"/>
                </svg>
            </div>
            <div class="banner-text">
                <h1 class="banner-title">
                    Code Expert
                    <span class="beta-tag">Beta</span>
                </h1>
                <p class="banner-subtitle">Intelligent Code Analysis & Repository Management</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
     # Initialize session state
    initialize_session_state()

    # Initialize loading placeholder
   
    # Loading State
    loading_placeholder = st.empty()
    if st.session_state.loading:
        with loading_placeholder.container():
            st.markdown("""
                <div style="background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin: 1rem 0;">
                    <div style="display: flex; align-items: center; gap: 1rem;">
                        <div class="loading-ring"></div>
                        <div>
                            <h3 style="margin: 0; color: #1F2937; font-size: 1.25rem;">Initializing Code Expert</h3>
                            <p style="margin: 0.5rem 0 0 0; color: #6B7280;">Setting up connections and loading repository data...</p>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    
   

  

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

    st.markdown("""
        <div class="repo-section">
            <h2 style="color: #1F2937; font-size: 1.5rem; margin-bottom: 1.5rem;">
                📚 Repository Management
            </h2>
        </div>
    """, unsafe_allow_html=True)    
   
    if not st.session_state.loading:
       
        with st.form("repo_form"):
            repo_url = st.text_input(
            "Enter GitHub Repository URL",
             placeholder="https://github.com/owner/repo",
              key="repo_url"
             )
            submit = st.form_submit_button("Process Repository", disabled=st.session_state.processing)
    
        if submit:
            repo_info = parse_github_url(repo_url)
            if repo_info:
                owner, repo = repo_info
                asyncio.run(process_repository(owner, repo))
            # The form will naturally clear on rerun
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

                # experiment type selector with explanation
                st.markdown("""
                ### Select RAG Version
                Choose which version of RAG to use for your query:
                """)
                experiment_type = st.radio(
                    "RAG Version:",
                    ["Base RAG", "Filtered RAG (with quality threshold)"],
                    help="""
                    Base RAG: Standard retrieval-augmented generation
                    Filtered RAG: Enhanced version with quality filtering of results
                    """,
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
                    if not st.session_state.messages or st.session_state.messages[-1]["content"] != prompt:
                        st.session_state.messages.append({"role": "user", "content": prompt})
                        with st.chat_message("user"):
                            st.markdown(prompt)

                    # Generate and display assistant response
                    with st.chat_message("assistant"):
                        try:
                            # Get repository name
                            repo_name = selected_repo.split('/')[-1] if selected_repo else None
                            with st.spinner('Processing your query...'):
                            # Process query based on selected experiment type
                                if experiment_type == "Base RAG":
                                    result = asyncio.run(base_rag.process_query(prompt, "base", repo_name))
                                else:
                                    result = asyncio.run(filtered_rag.process_query(prompt, "filtered", repo_name))

                                response = result.get("response", "")
                                metrics = result.get("metrics", {})
                                if not response:
                                    st.error("No response generated. Please try rephrasing your question.")
                                    return
                            # Display response
                                st.markdown(response)
 
                            # Show metrics in expander
                                with st.expander("Query Performance Metrics"):
                                    col1, col2, col3, col4 = st.columns(4)
                                    with col1:
                                        st.metric("Context Relevance", f"{metrics['context_relevance']:.3f}")
                                    with col2:
                                        st.metric("Groundedness", f"{metrics['groundedness']:.3f}")
                                    with col3:
                                        st.metric("Answer Relevance", f"{metrics['answer_relevance']:.3f}")
                                    with col4:
                                        st.metric("Response Quality", f"{metrics.get('response_quality', 0):.3f}")

                                if 'filter_stats' in metrics:
                                    st.markdown("### Filter Statistics")
                                    stats = metrics['filter_stats']
                                    st.markdown(f"""
                                    - Total Results: {stats.get('total_results', 0)}
                                    - Filtered Results: {stats.get('filtered_results', 0)}
                                    - Average Relevance: {stats.get('average_relevance', 0):.3f}
                                    """)

                            # response to chat history
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

                st.divider()  

                # evaluation dashboard
                if st.checkbox("Show TruLens Evaluation Summary", value=True):
                    try:
                        render_comparison_dashboard(base_rag, filtered_rag)
                    except Exception as e:
                        st.error(f"Error displaying evaluation summary: {str(e)}")

        else:
            st.info("No repositories processed yet. Please enter a GitHub URL above to begin.")

if __name__ == "__main__":
    main()


