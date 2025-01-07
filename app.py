import streamlit as st
from snowflake.snowpark.context import get_active_session
import json
import snowflake.connector

def search_code(query: str):
    session = get_active_session()
    results = session.sql(f"""
    SELECT PARSE_JSON(
        SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
            'CODE_SEARCH_SERVICE',
            '{{
                "query": "{query}",
                "columns": [
                    "chunk",
                    "file_url",
                    "language"
                ],
                "limit": 5
            }}'
        )
    )['results'] as results
    """).collect()[0]['RESULTS']
    return json.loads(results)

def main():
    st.title("Code Search RAG Assistant")
    st.write("Testing Snowflake connection...")
    
    # GitHub URL input
    repo_url = st.text_input("Enter GitHub Repository URL")
    
    # Search input
    search_query = st.text_input("Search code", placeholder="Enter search query")
    
    if search_query:
        results = search_code(search_query)
        for result in results:
            st.code(result['chunk'], language=result['language'])

if __name__ == "__main__":
    main()