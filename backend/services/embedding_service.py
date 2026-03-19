from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Dict, Any
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self.model_name = settings.embedding_model
        self.dimension = settings.embedding_dimension
        
        # Initialize model
        try:
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {str(e)}")
            raise
    
    def encode_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {str(e)}")
            raise
    
    def encode_single(self, text: str) -> List[float]:
        """Generate embedding for a single text"""
        try:
            embedding = self.model.encode([text], convert_to_numpy=True)[0]
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Single embedding generation failed: {str(e)}")
            raise

# Global instance
embedding_service = EmbeddingService()
