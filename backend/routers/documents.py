from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import os
import uuid
import logging
from pathlib import Path

from database import get_db
from models import Document, Project
from schemas import Document as DocumentSchema, DocumentCreate
from auth import get_current_active_user
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path("/app/uploads")

@router.post("/upload", response_model=DocumentSchema)
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload a PDF document"""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only administrators can upload documents")
    try:
        # Validate file type (also accept octet-stream for some clients)
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Read and validate size
        content = await file.read()
        file_size = len(content)
        if settings.max_file_size_mb > 0 and file_size > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File too large. Max size: {settings.max_file_size_mb}MB")
        
        # Check if project exists
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalars().first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Save file to shared upload directory
        unique_filename = f"{uuid.uuid4()}.pdf"
        user_dir = UPLOAD_DIR / str(current_user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        file_path = user_dir / unique_filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Create document record
        db_document = Document(
            project_id=project_id,
            filename=file.filename,
            file_path=str(file_path),
            status="pending"
        )
        db.add(db_document)
        await db.commit()
        await db.refresh(db_document)
        
        # Fire off Celery task (non-blocking)
        try:
            from worker import process_document
            task = process_document.delay(
                str(db_document.id),
                str(project_id),
                str(current_user.id)
            )
            logger.info(f"Processing task queued: {task.id} for doc {db_document.id}")
        except Exception as celery_err:
            logger.error(f"Could not queue Celery task: {celery_err}. Document saved but not processed.")
            # Don't fail the upload — document is saved, just won't be processed immediately
        
        logger.info(f"Document uploaded: {file.filename} by user {current_user.email}")
        return db_document

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/", response_model=List[DocumentSchema])
async def get_documents(
    project_id: str = None,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get documents"""
    try:
        query = select(Document)
        if project_id:
            # Validate it's a UUID to avoid SQL errors
            try:
                import uuid as uuid_lib
                uuid_lib.UUID(project_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid project_id format")
            query = query.where(Document.project_id == project_id)
        
        query = query.offset(skip).limit(limit).order_by(Document.created_at.desc())
        result = await db.execute(query)
        documents = result.scalars().all()
        
        return documents
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get documents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve documents")

@router.get("/{document_id}", response_model=DocumentSchema)
async def get_document(
    document_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific document"""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalars().first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return document
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve document")

@router.get("/{document_id}/status")
async def get_document_status(
    document_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get document processing status"""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalars().first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {"status": document.status, "progress": 100 if document.status == "ready" else 50}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve status")

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document"""
    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalars().first()
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        if not current_user.is_superuser:
            raise HTTPException(status_code=403, detail="Only administrators can delete documents")
        
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        await db.delete(document)
        await db.commit()
        
        logger.info(f"Document deleted: {document.filename} by user {current_user.email}")
        return {"message": "Document deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Delete failed")
