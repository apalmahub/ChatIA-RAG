from celery import Celery
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import logging
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "chatia_worker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

def get_sync_engine():
    """Create a new async engine for Celery tasks"""
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(settings.database_url, echo=False)

@celery_app.task(bind=True, max_retries=3)
def process_document(self, document_id: str, project_id: str = None, user_id: str = None):
    """Process uploaded PDF document asynchronously via Celery"""
    try:
        asyncio.run(_process_document_async(document_id, project_id, user_id))
        return {"status": "success", "document_id": document_id}
    except Exception as e:
        logger.error(f"Document processing failed for {document_id}: {str(e)}")
        try:
            asyncio.run(_update_document_status(document_id, "error"))
        except Exception:
            pass
        raise self.retry(countdown=60, exc=e)

async def _process_document_async(document_id: str, project_id: str = None, user_id: str = None):
    """Async document processing logic"""
    from models import Document
    from services.pdf_processor import extract_text_from_pdf, prepare_chunks_for_embedding
    from services.embedding_service import embedding_service
    from services.vector_store import vector_store
    from services.memorag_service import MemoRAGService

    engine = get_sync_engine()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # Get document
            result = await db.execute(select(Document).where(Document.id == document_id))
            document = result.scalars().first()
            
            if not document:
                raise Exception(f"Document {document_id} not found")
            
            # Update to processing
            await db.execute(
                update(Document).where(Document.id == document_id).values(status="processing")
            )
            await db.commit()
            
            # Extract text from PDF
            logger.info(f"Extracting text from {document.file_path}")
            pdf_data = extract_text_from_pdf(document.file_path)
            
            # Prepare chunks
            chunks = prepare_chunks_for_embedding(pdf_data["text_content"])
            
            if chunks:
                # Generate embeddings
                texts = [chunk["content"] for chunk in chunks]
                embeddings = embedding_service.encode_texts(texts)
                
                # Use project_id for the collection name to keep it under 63 chars
                # All project documents go in the same collection
                pid = str(document.project_id).replace('-', '_')
                collection_name = f"proj_{pid}"
                
                # Prepare metadata
                uid = user_id or str(document.project_id)
                metadatas = []
                for chunk in chunks:
                    meta = chunk["metadata"].copy()
                    meta.update({
                        "document_id": str(document_id),
                        "project_id": str(document.project_id),
                        "user_id": str(uid)
                    })
                    metadatas.append(meta)
                
                # Add to vector store
                vector_store.add_documents(
                    collection_name=collection_name,
                    documents=texts,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                
                # MemoRAG check
                try:
                    memorag_service = MemoRAGService()
                    if memorag_service.should_activate(pdf_data["token_count"]):
                        await memorag_service.create_global_memory(str(document_id), chunks)
                except Exception as me:
                    logger.warning(f"MemoRAG skipped: {me}")
            
            # Mark as ready
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    status="ready",
                    num_pages=pdf_data["num_pages"],
                    token_count=pdf_data["token_count"]
                )
            )
            await db.commit()
            logger.info(f"Document {document_id} processed successfully")
            
        except Exception as e:
            logger.error(f"Processing error: {str(e)}")
            try:
                await db.execute(
                    update(Document).where(Document.id == document_id).values(status="error")
                )
                await db.commit()
            except Exception:
                pass
            raise
        finally:
            await engine.dispose()

async def _update_document_status(document_id: str, status: str):
    """Update document status standalone"""
    from models import Document
    engine = get_sync_engine()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as db:
        await db.execute(
            update(Document).where(Document.id == document_id).values(status=status)
        )
        await db.commit()
    await engine.dispose()
