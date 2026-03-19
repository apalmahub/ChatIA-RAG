import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
import logging
import uuid

from config import settings
from services.embedding_service import embedding_service

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        # Use PersistentClient with a shared volume path
        self.client = chromadb.PersistentClient(
            path="/app/data/chromadb",
            settings=Settings(anonymized_telemetry=False)
        )
    
    def get_or_create_collection(self, collection_name: str):
        """Get or create a collection"""
        try:
            return self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        except Exception as e:
            logger.error(f"Failed to get/create collection {collection_name}: {str(e)}")
            raise
    
    def add_documents(
        self, 
        collection_name: str, 
        documents: List[str], 
        embeddings: List[List[float]], 
        metadatas: List[Dict[str, Any]], 
        ids: Optional[List[str]] = None
    ):
        """Add documents to collection"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            if ids is None:
                ids = [str(uuid.uuid4()) for _ in documents]
            
            collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Added {len(documents)} documents to collection {collection_name}")
        except Exception as e:
            logger.error(f"Failed to add documents: {str(e)}")
            raise
    
    def search(
        self, 
        collection_name: str, 
        query_embedding: List[float], 
        n_results: int = 20,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search for similar documents"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where
            )
            
            return results
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            raise
    
async def search_documents(query: str, user_id: str, project_id: str = None, n_results: int = 20) -> List[Dict[str, Any]]:
    """Search documents for user with multi-page coverage"""
    try:
        # Generate query embedding
        query_embedding = embedding_service.encode_single(query)
        
        if project_id:
            pid = str(project_id).replace('-', '_')
            collection_name = f"proj_{pid}"
        else:
            collection_name = f"user_{user_id}_documents"
        
        # Pull more raw results to allow for deduplication
        raw_results = vector_store.search(
            collection_name=collection_name,
            query_embedding=query_embedding,
            n_results=n_results * 2 
        )
        
        formatted_results = []
        seen_pages = set()
        
        if raw_results and raw_results["documents"]:
            for i, doc in enumerate(raw_results["documents"][0]):
                metadata = raw_results["metadatas"][0][i] if raw_results["metadatas"] else {}
                page_num = metadata.get("page_number")
                
                # Deduplication logic: try to get unique pages first
                # If we have less than n_results, we eventually allow multiple chunks per page
                if page_num not in seen_pages or len(formatted_results) < 5:
                    formatted_results.append({
                        "content": doc,
                        "metadata": metadata,
                        "score": raw_results["distances"][0][i] if raw_results["distances"] else 0
                    })
                    seen_pages.add(page_num)
                
                if len(formatted_results) >= n_results:
                    break
        
        return formatted_results
    except Exception as e:
        logger.error(f"Document search failed: {str(e)}")
        return []

# Global instance
vector_store = VectorStore()
