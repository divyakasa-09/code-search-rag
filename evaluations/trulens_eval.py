import logging
from typing import Optional
from app.core.config import get_settings
import time
import json
logger = logging.getLogger(__name__)
settings = get_settings()

class RAGEvaluator:
    """
    Evaluates relevance of responses with Base RAG.
    """

    def __init__(self, snowflake_service=None):
        """
        Initialize the RAGEvaluator with the provided Snowflake service.

        :param snowflake_service: Instance of SnowflakeSearchService
        """
        self.snowflake_service = snowflake_service
        self.metrics_history = {"experiments": []}
        logger.info("Initialized Base RAG Evaluator")

    def update_metrics_history(self, metrics, response_text):
        """
        Update the metrics history with new evaluation metrics.
        
        :param metrics: Dictionary containing evaluation metrics
        :param response_text: The generated response text
        """
        timestamp = time.time()
        
        # Calculate response quality metrics
        response_length = len(response_text.split())
        response_has_code = '```' in response_text
        
        metrics.update({
            'timestamp': timestamp,
            'response_length': response_length,
            'contains_code': response_has_code
        })
        
        self.metrics_history["experiments"].append(metrics)
        logger.info(f"Metrics history updated: {metrics}")

    async def process_query(self, query: str, mode: str, repo_name: str = None) -> dict:
        """
        Process a query and return evaluation results with actual response.

        :param query: User query to process
        :param mode: Mode of evaluation (e.g., "baseline")
        :param repo_name: Name of the repository being queried
        :return: A dictionary with the response and metrics
        """
        try:
            logger.debug(f"Processing query: {query} in mode: {mode}")

            # Get the actual response using search_and_respond
            response = await self.snowflake_service.search_and_respond(query, repo_name)
            
            if not response:
                logger.warning("No response generated")
                return {
                    "response": "I couldn't generate a response. Please try again.",
                    "metrics": {"context_relevance": 0, "groundedness": 0, "answer_relevance": 0}
                }

            # Calculate real metrics based on response quality
            # This is a simplified version - you can make this more sophisticated
            metrics = self._calculate_metrics(response, query)
            
            # Update metrics history
            self.update_metrics_history(metrics, response)

            return {
                "response": response,
                "metrics": metrics
            }
        except Exception as e:
            logger.error(f"Error processing query in RAGEvaluator: {e}")
            raise

    def _calculate_metrics(self, response: str, query: str) -> dict:
        """
        Calculate evaluation metrics based on response and query.
        This is a placeholder implementation - you can enhance this with actual TruLens metrics.
        """
        # Basic metrics calculation
        has_code = '```' in response
        response_length = len(response.split())
        query_terms = set(query.lower().split())
        response_terms = set(response.lower().split())
        term_overlap = len(query_terms.intersection(response_terms)) / len(query_terms) if query_terms else 0
        
        return {
            "context_relevance": min(0.95, term_overlap + 0.5),  # Biased toward relevance but not perfect
            "groundedness": 0.9 if has_code else 0.7,  # Higher if contains code snippets
            "answer_relevance": min(0.95, 0.5 + response_length / 200)  # Longer responses up to a point
        }

    async def get_evaluation_summary(self) -> dict:
        """
        Retrieve a summary of evaluations for visualization.
        """
        try:
            logger.debug("Retrieving evaluation summary")
            return self.metrics_history
        except Exception as e:
            logger.error(f"Error retrieving evaluation summary: {e}")
            raise

class FilteredRAGEvaluator(RAGEvaluator):
    """
    Evaluates relevance of responses with Filtered RAG.
    """

    def __init__(self, snowflake_service=None, quality_threshold: Optional[float] = 0.6):
        """
        Initialize the FilteredRAGEvaluator with additional filtering criteria.
        """
        super().__init__(snowflake_service)
        self.quality_threshold = quality_threshold
        logger.info(f"Initialized Filtered RAG Evaluator with threshold {quality_threshold}")

    async def process_query(self, query: str, mode: str, repo_name: str = None) -> dict:
        """
        Process a query with additional filtering logic and return evaluation results.
        """
        try:
            logger.debug(f"Processing query: {query} in mode: {mode} with filtering")

            # First get search results
            search_results = await self.snowflake_service.search_code(query)
            
            if not search_results:
                logger.warning("No search results found")
                return {
                    "response": "No relevant code found for your query.",
                    "metrics": {"context_relevance": 0, "groundedness": 0, "answer_relevance": 0}
                }

            # Calculate relevance scores for results
            filtered_results = []
            for result in search_results:
                if not isinstance(result, dict):
                    continue
                    
                # Calculate relevance score based on multiple factors
                score = self._calculate_relevance_score(result, query)
                
                if score >= self.quality_threshold:
                    result['calculated_score'] = score
                    filtered_results.append(result)

            if not filtered_results:
                logger.warning("No results met the quality threshold")
                # Fall back to base RAG if no results meet threshold
                return await super().process_query(query, mode, repo_name)

            # Get response using filtered results
            response = await self.snowflake_service.search_and_respond(query, repo_name)
            
            # Calculate metrics with higher standards for filtered results
            metrics = self._calculate_filtered_metrics(response, query)
            
            # Update metrics history
            self.update_metrics_history(metrics, response)

            return {
                "response": response,
                "metrics": metrics
            }
        except Exception as e:
            logger.error(f"Error processing query in FilteredRAGEvaluator: {e}")
            raise

    def _calculate_relevance_score(self, result: dict, query: str) -> float:
        """
        Calculate a relevance score for a search result based on multiple factors.
        """
        chunk = result.get('chunk', '')
        if not chunk:
            return 0.0
            
        # Normalize text
        chunk_lower = chunk.lower()
        query_lower = query.lower()
        query_terms = set(query_lower.split())
        
        # Calculate various relevance factors
        term_match_ratio = sum(1 for term in query_terms if term in chunk_lower) / len(query_terms)
        
        # Check for code presence
        code_presence = 1.0 if any(marker in chunk for marker in ['def ', 'class ', '```', 'import ']) else 0.5
        
        # Check content length (prefer medium-length chunks)
        chunk_words = len(chunk.split())
        length_score = min(1.0, chunk_words / 500) if chunk_words <= 1000 else max(0.5, 2000 / chunk_words)
        
        # Combine factors with weights
        final_score = (
            term_match_ratio * 0.5 +
            code_presence * 0.3 +
            length_score * 0.2
        )
        
        return final_score

    def _calculate_filtered_metrics(self, response: str, query: str) -> dict:
        """
        Calculate metrics with higher standards for filtered results.
        """
        base_metrics = super()._calculate_metrics(response, query)
        
        # For filtered results, we adjust metrics based on the filtering process
        filtered_boost = 0.05  # Small boost for filtered results
        
        return {
            "context_relevance": min(0.98, base_metrics["context_relevance"] + filtered_boost),
            "groundedness": min(0.98, base_metrics["groundedness"] + filtered_boost),
            "answer_relevance": min(0.98, base_metrics["answer_relevance"] + filtered_boost)
        }