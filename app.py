import streamlit as st
import snowflake.connector
import re

# Initialize Snowflake connection
def init_connection():
    try:
        return snowflake.connector.connect(
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            account=st.secrets["snowflake"]["account"],
            warehouse=st.secrets["snowflake"]["warehouse"],
            database='CODE_EXPERT',
            schema='PUBLIC'
        )
    except Exception as e:
        st.error(f"Failed to connect to Snowflake: {str(e)}")
        return None

def search_code(query: str):
    conn = init_connection()
    if conn:
        try:
            results = conn.cursor().execute(f"""
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
            """).fetchone()
            return results[0] if results else []
        except Exception as e:
            st.error(f"Search error: {str(e)}")
            return []
        finally:
            conn.close()

def main():
    st.title("Code Search RAG Assistant")

    # GitHub URL input
    repo_url = st.text_input("Enter GitHub Repository URL", 
                            placeholder="https://github.com/owner/repo")

    # Search input
    search_query = st.text_input("Search code", placeholder="Enter search query")

    if search_query:
        with st.spinner('Searching...'):
            results = search_code(search_query)
            if results:
                for result in results:
                    st.code(result['chunk'], language=result['language'].lower())
                    st.caption(f"File: {result['file_url']}")
            else:
                st.info("No results found")

if __name__ == "__main__":
    main()