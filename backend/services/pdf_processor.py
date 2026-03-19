import pdfplumber
import tiktoken
from pathlib import Path
from typing import List, Dict, Any
import logging
import asyncio

from config import settings

logger = logging.getLogger(__name__)

async def process_document_async(document_id: str):
    """Start async document processing"""
    from worker import process_document
    # This will be handled by Celery in production
    # For development, we can call it directly
    try:
        result = process_document.delay(document_id)
        logger.info(f"Document processing started for {document_id}, task: {result.id}")
    except Exception as e:
        logger.error(f"Failed to start document processing: {str(e)}")
        raise

def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    """Extract text and metadata from PDF"""
    try:
        text_content = []
        metadata = {"pages": []}
        
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    text_content.append({
                        "page_number": i + 1,
                        "content": text.strip(),
                        "char_count": len(text)
                    })
                    metadata["pages"].append({
                        "page": i + 1,
                        "char_count": len(text)
                    })
        
        full_text = "\n".join([page["content"] for page in text_content])
        token_count = count_tokens(full_text)
        
        return {
            "text_content": text_content,
            "full_text": full_text,
            "token_count": token_count,
            "num_pages": len(text_content),
            "metadata": metadata
        }
    except Exception as e:
        logger.error(f"PDF extraction failed: {str(e)}")
        raise

def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count tokens in text"""
    try:
        encoding = tiktoken.encoding_for_model(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback to approximate count
        return len(text.split()) * 1.3

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
    """Split text into chunks with overlap"""
    words = text.split()
    chunks = []
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
        if i + chunk_size >= len(words):
            break
    
    return chunks

def prepare_chunks_for_embedding(
    text_content: List[Dict[str, Any]], 
    chunk_size: int = 400, 
    overlap: int = 50
) -> List[Dict[str, Any]]:
    """Prepare text chunks with metadata for embedding"""
    chunks = []
    
    for page_data in text_content:
        page_chunks = chunk_text(page_data["content"], chunk_size, overlap)
        
        for i, chunk in enumerate(page_chunks):
            chunks.append({
                "content": chunk,
                "metadata": {
                    "page_number": page_data["page_number"],
                    "chunk_index": i,
                    "source": "pdf_page"
                }
            })
    
    return chunks
