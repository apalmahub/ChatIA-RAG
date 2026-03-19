from typing import List, Dict, Any, Optional
import logging

from services.vector_store import vector_store
from services.embedding_service import embedding_service
from config import settings

logger = logging.getLogger(__name__)

class MemoRAGService:
    def __init__(self, threshold_tokens: int = None):
        self.threshold = threshold_tokens or settings.memorag_threshold_tokens
        self.vector_store = vector_store
        self.embedding_service = embedding_service
    
    def should_activate(self, token_count: int) -> bool:
        """Check if MemoRAG should be activated"""
        return token_count > self.threshold
    
    async def create_global_memory(
        self, 
        document_id: str, 
        chunks: List[Dict[str, Any]]
    ):
        """Create global memory for a document"""
        try:
            collection_name = f"global_memory_{document_id}"
            
            # Create a summary of the document
            all_text = " ".join([chunk["content"] for chunk in chunks])
            summary_chunks = self._summarize_document(all_text)
            
            # Generate embeddings for summary
            embeddings = self.embedding_service.encode_texts(summary_chunks)
            
            # Prepare metadata
            metadatas = [
                {
                    "type": "global_memory",
                    "document_id": document_id,
                    "chunk_index": i
                }
                for i in range(len(summary_chunks))
            ]
            
            # Store in vector store
            self.vector_store.add_documents(
                collection_name=collection_name,
                documents=summary_chunks,
                embeddings=embeddings,
                metadatas=metadatas
            )
            
            logger.info(f"Global memory created for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to create global memory: {str(e)}")
            raise
    
    async def query_global_memory(
        self, 
        user_query: str, 
        document_id: Optional[str] = None
    ) -> str:
        """Query global memory for relevant context"""
        try:
            if not document_id:
                return ""
            
            collection_name = f"global_memory_{document_id}"
            
            # Generate query embedding
            query_embedding = self.embedding_service.encode_single(user_query)
            
            # Search global memory
            results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                n_results=3
            )
            
            # Extract relevant memories
            memories = []
            if results and results["documents"]:
                for doc in results["documents"][0]:
                    memories.append(doc)
            
            return " ".join(memories)
        except Exception as e:
            logger.error(f"Global memory query failed: {str(e)}")
            return ""
    
    async def update_memory(
        self, 
        document_id: str, 
        new_interactions: List[Dict[str, Any]]
    ):
        """Update global memory with new interactions"""
        try:
            # This is a simplified implementation
            # In a real system, you might want to periodically
            # update the global memory based on user interactions
            
            logger.info(f"Memory update triggered for document {document_id}")
            # Implementation would depend on specific MemoRAG algorithm
        except Exception as e:
            logger.error(f"Memory update failed: {str(e)}")
    
    def _summarize_document(self, text: str) -> List[str]:
        """Create summary chunks for global memory"""
        # Simple chunking for demonstration
        # In practice, you might use an LLM to create better summaries
        words = text.split()
        chunk_size = 500  # Smaller chunks for memory
        chunks = []
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
        
        return chunks
