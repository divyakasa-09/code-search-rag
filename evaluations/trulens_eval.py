import logging
import re
from typing import Optional, List, Dict
import time
import json
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


logger.setLevel(logging.INFO)


if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

logger.info(" evaluation module initialized with logging")

class RAGEvaluator:
    def __init__(self, snowflake_service=None):
        self.snowflake_service = snowflake_service
        self.metrics_history = {"experiments": []}
        logger.info("Initialized Base RAG Evaluator")

    async def process_query(self, query: str, mode: str, repo_name: str = None) -> dict:
        """Process a query and calculate evaluation metrics."""
        try:
            logger.info(f"Processing query in {mode} mode: {query}")
            logger.info(f"Repository: {repo_name}")
            
            # Get search results and response
            result = await self.snowflake_service.search_and_respond(query, repo_name)
            
            # Extract components
            search_results = result["search_results"]
            response = result["response"]
            metadata = result["metadata"]
            
            logger.info(f"Retrieved {len(search_results)} search results")
            logger.info(f"Response length: {len(response.split())}")
            
            # Calculate metrics
            metrics = self._calculate_metrics(response, query, search_results)
            
            # Add experiment metadata
            metrics.update({
                "mode": mode,
                "timestamp": time.time(),
                "query_length": len(query.split()),
                "response_length": len(response.split()),
                "chunks_used": len(search_results) if search_results else 0,
                "has_code": '```' in response
            })
            
            # Store metrics in history
            self.metrics_history["experiments"].append(metrics)
            
            return {
                "response": response,
                "metrics": metrics
            }
            
        except Exception as e:
            logger.error(f"Error in RAGEvaluator process_query: {str(e)}", exc_info=True)
            raise

    def _calculate_chunk_relevance(self, chunk: str, query_terms: set) -> float:
        try:
            chunk_lower = chunk.lower()
            chunk_terms = set(chunk_lower.split())
            
            # Debug original input
            logger.debug(f"Processing chunk: {chunk[:100]}...")
            logger.debug(f"Query terms: {query_terms}")
            
            # 1. Query match scoring
            term_scores = []
            for term in query_terms:
                if term in chunk_lower:
                    occurrences = chunk_lower.count(term)
                    position = chunk_lower.index(term) / len(chunk_lower)
                    # Higher score for terms appearing early and multiple times
                    score = min(1.0, 0.5 + (0.3 * occurrences) + (0.2 * (1 - position)))
                    term_scores.append(score)
                    logger.debug(f"Term '{term}' score: {score:.3f} (occurrences: {occurrences}, position: {position:.2f})")
                else:
                    term_scores.append(0.3)
            
            query_score = sum(term_scores) / len(term_scores) if term_scores else 0.3
            logger.debug(f"Query match score: {query_score:.3f}")
            
            # 2. Code relevance scoring
            code_elements = {
                'def ': {'weight': 0.9, 'found': False},      # Functions
                'class ': {'weight': 0.9, 'found': False},    # Classes
                'import ': {'weight': 0.7, 'found': False},   # Imports
                'return ': {'weight': 0.6, 'found': False},   # Returns
                'if ': {'weight': 0.5, 'found': False},       # Conditionals
                'for ': {'weight': 0.5, 'found': False},      # Loops
                'try:': {'weight': 0.5, 'found': False},      # Error handling
            }
            
            code_score = 0.3  # Base score
            for element, info in code_elements.items():
                if element in chunk_lower:
                    code_score += info['weight'] * 0.2
                    info['found'] = True
                    logger.debug(f"Found code element '{element}' (+{info['weight'] * 0.2:.3f})")
            
            code_score = min(0.95, code_score)
            logger.debug(f"Code relevance score: {code_score:.3f}")
            
            # 3. Content quality scoring
            quality_indicators = {
                'readme': 0.4,
                'description': 0.4,
                'purpose': 0.4,
                'functionality': 0.4,
                'features': 0.4
            }
            
            quality_score = 0.3  # Base score
            for term, weight in quality_indicators.items():
                if term in chunk_lower:
                    quality_score += weight * 0.2
                    logger.debug(f"Found quality term '{term}' (+{weight * 0.2:.3f})")
            
            quality_score = min(0.95, quality_score)
            logger.debug(f"Content quality score: {quality_score:.3f}")
            
            # Combined scoring with weights
            final_score = (
                query_score * 0.4 +      # Query match importance
                code_score * 0.4 +       # Code content importance
                quality_score * 0.2      # General content quality
            )
            
            # Apply length bonus
            if len(chunk_terms) > 50:
                final_score *= 1.15
                logger.debug("Applied length bonus (15%)")
            
            final_score = max(0.3, min(0.95, final_score))
            logger.debug(f"Final relevance score: {final_score:.3f}")
            
            return final_score
            
        except Exception as e:
            logger.error(f"Error calculating chunk relevance: {e}", exc_info=True)
            return 0.3



    def _calculate_response_metrics(self, response: str) -> Dict:
        """Calculate various response-related metrics."""
        try:
            # Code presence metrics
            code_blocks = response.count('```')
            code_references = len(re.findall(r'function|method|class|variable|parameter|module|import|return', response.lower()))
            
            # Explanation metrics
            has_explanation = bool(re.search(r'because|therefore|this means|in other words|specifically|for example', response.lower()))
            
            # Technical content metrics
            technical_terms = len(re.findall(r'function|class|method|parameter|variable|return|import', response.lower()))
            
            return {
                'code_blocks': code_blocks,
                'code_references': code_references,
                'has_explanation': has_explanation,
                'technical_terms': technical_terms
            }
        except Exception as e:
            logger.error(f"Error calculating response metrics: {e}")
            return {}

    def _calculate_metrics(self, response: str, query: str, code_chunks: List[str]) -> dict:
        """Calculate comprehensive metrics for RAG evaluation."""
        try:
            logger.info(f"Calculating metrics for query: {query}")
            logger.info(f"Processing {len(code_chunks)} chunks")
        
        # Process chunks
            processed_chunks = []
            for chunk in code_chunks:
                if isinstance(chunk, dict):
                    chunk_content = chunk.get('chunk', '')
                else:
                    chunk_content = str(chunk)
                if chunk_content and chunk_content.strip():
                    processed_chunks.append(chunk_content)
                    logger.debug(f"Processing chunk: {chunk_content[:100]}...")
        
        # Query analysis
            query_terms = set(query.lower().split())
            query_length = len(query_terms)
        
        # Calculate chunk relevance scores with weight for top scores
            chunk_relevance_scores = []
            for chunk in processed_chunks:
                relevance_score = self._calculate_chunk_relevance(chunk, query_terms)
                if relevance_score > 0:
                    chunk_relevance_scores.append(relevance_score)
        
        # Sort scores and give more weight to top chunks
            if chunk_relevance_scores:
                sorted_scores = sorted(chunk_relevance_scores, reverse=True)
                top_k = min(5, len(sorted_scores))  # Consider top 5 chunks
                context_relevance = sum(sorted_scores[:top_k]) / top_k
            else:
                context_relevance = 0.3  # Increased minimum
        
        # Calculate response metrics
            response_metrics = self._calculate_response_metrics(response)
        
        # Enhanced groundedness calculation
            groundedness = min(1.0, (
            (response_metrics['code_blocks'] * 0.3) +
            (min(1.0, response_metrics['code_references'] / 4) * 0.5) +
            (0.2 if response_metrics['has_explanation'] else 0) +
            (min(1.0, response_metrics['technical_terms'] / 5) * 0.2)  # Added technical terms impact
            ))
        
        # Enhanced answer relevance
            response_terms = set(response.lower().split())
            term_overlap = len(query_terms.intersection(response_terms)) / len(query_terms) if query_terms else 0
        
            structure_score = (
            (bool(response_metrics['code_blocks']) * 0.3) +
            (response_metrics['has_explanation'] * 0.3) +
            (min(1.0, response_metrics['technical_terms'] / 4) * 0.2) +
            (min(1.0, len(response.split()) / 100) * 0.2)
        )
        
            answer_relevance = (term_overlap * 0.6) + (structure_score * 0.4)
        
        # Calculate final metrics with improved minimum thresholds
            metrics = {
            "context_relevance": max(0.3, min(0.95, context_relevance)),
            "groundedness": max(0.3, min(0.95, groundedness)),
            "answer_relevance": max(0.3, min(0.95, answer_relevance)),
            "response_quality": max(0.3, min(0.95, (context_relevance + groundedness + answer_relevance) / 3)),
            "query_length": query_length,
            "debug_info": {
                "response_metrics": response_metrics,
                "num_chunks_processed": len(processed_chunks),
                "avg_chunk_relevance": sum(chunk_relevance_scores) / len(chunk_relevance_scores) if chunk_relevance_scores else 0,
                "top_chunk_scores": sorted(chunk_relevance_scores, reverse=True)[:5] if chunk_relevance_scores else []
            }
        }
        
            logger.info(f"Final metrics calculated: {json.dumps(metrics, indent=2)}")
            return metrics
        
        except Exception as e:
            logger.error(f"Error calculating metrics: {e}", exc_info=True)
            return {
            "context_relevance": 0.3,
            "groundedness": 0.3,
            "answer_relevance": 0.3,
            "response_quality": 0.3,
            "query_length": len(query.split()) if query else 0,
            "error": str(e)
        }
            
class FilteredRAGEvaluator(RAGEvaluator):
    def __init__(self, snowflake_service=None, quality_threshold: float = 0.33):  # Changed from 0.1 to 0.4
        super().__init__(snowflake_service)
        self.quality_threshold = quality_threshold
        logger.info(f"Initialized Filtered RAG Evaluator with threshold {quality_threshold}")

    async def process_query(self, query: str, mode: str, repo_name: str = None) -> dict:
        try:
            enhanced_query = f"""Please analyze the following query about the code:
Question: {query}
Additional instructions:
- Show relevant code snippets using markdown
- Explain any technical concepts used
- Reference specific file paths when relevant
- include any relevant code snippets
- Focus on the implementation details"""
            # Simply use the search_and_respond from snowflake service
            result = await self.snowflake_service.search_and_respond(enhanced_query, repo_name)
        
            # Extract the response and calculate metrics
            response = result["response"]
            search_results = result["search_results"]
        
        # Calculate metrics
            metrics = self._calculate_metrics(response, query, search_results)
            metrics.update({
            "mode": mode,
            "timestamp": int(time.time())
        })
        
        # Store metrics in history
            self.metrics_history["experiments"].append(metrics)
        
            return {
             "response": response,
            "metrics": metrics
        }

        except Exception as e:
            logger.error(f"Error in FilteredRAGEvaluator: {str(e)}")
            raise
    def _calculate_code_quality(self, chunk: str, query: str) -> float:
        """Calculate code quality with a combination of structure and relevance scoring."""
        try:
            base_score = 0.1  # Base score for any chunk

            # Define patterns for code quality scoring
            code_patterns = {
                'function_def': (r'def\s+\w+\s*\(', 0.3),
                'class_def': (r'class\s+\w+', 0.3),
                'docstring': (r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', 0.2),
                'comments': (r'#.*$|//.*$', 0.1),
                'imports': (r'import\s+\w+|from\s+\w+\s+import', 0.1),
                'variables': (r'=\s*[\w\'"[]', 0.1),
                'code_structure': (r'if|else|for|while|try|except|return', 0.2)
            }

            # Calculate pattern-based score
            pattern_score = base_score
            for pattern, weight in code_patterns.values():
                matches = len(re.findall(pattern, chunk, re.MULTILINE))
                if matches > 0:
                    pattern_score += min(weight, matches * weight * 0.2)

            # Calculate query relevance
            query_terms = set(query.lower().split())
            chunk_terms = set(chunk.lower().split())
            term_overlap = len(query_terms.intersection(chunk_terms)) / len(query_terms) if query_terms else base_score

            # Combine scores with adjusted weights
            final_score = max(base_score, min(1.0, (pattern_score * 0.4) + (term_overlap * 0.6)))

            logger.debug(f"Quality scoring - Pattern: {pattern_score:.3f}, Terms: {term_overlap:.3f}, Final: {final_score:.3f}")
            return final_score

        except Exception as e:
            logger.error(f"Error calculating code quality: {e}")
            return base_score

    def _calculate_metrics(self, response: str, query: str, code_chunks: List[str]) -> dict:
        """Calculate metrics for the response."""
        try:
            # Calculate response length and check for code presence
            response_length = len(re.sub(r'```[\s\S]*?```', '', response).split()) + \
                              sum(len(block.split()) for block in re.findall(r'```[\s\S]*?```', response))
            has_code = bool(re.search(r'```[\s\S]*?```', response))

            # Call parent method to calculate base metrics
            base_metrics = super()._calculate_metrics(response, query, code_chunks)

            # Update and return metrics
            base_metrics.update({
                "response_length": response_length,
                "has_code": has_code
            })

            logger.info(f"Final Metrics: {json.dumps(base_metrics, indent=2)}")
            return base_metrics

        except Exception as e:
            logger.error(f"Error calculating metrics: {e}")
            raise

    def set_quality_threshold(self, threshold: float):
        """Update the quality threshold with validation."""
        try:
            new_threshold = max(0.0, min(1.0, threshold))
            old_threshold = self.quality_threshold
            self.quality_threshold = new_threshold
            logger.info(f"Updated quality threshold from {old_threshold:.2f} to {new_threshold:.2f}")
        except Exception as e:
            logger.error(f"Error updating quality threshold: {e}")