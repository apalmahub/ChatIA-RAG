from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import time
import logging

from database import get_db
from models import Chat, Message, Project
from schemas import Chat as ChatSchema, ChatCreate, Message as MessageSchema, ChatMessage, ChatResponse
from auth import get_current_active_user
from services.llm_service import generate_response
from services.vector_store import search_documents
from services.memorag_service import MemoRAGService
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=ChatSchema)
async def create_chat(
    chat: ChatCreate,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new chat"""
    try:
        if chat.project_id:
            # Verify project belongs to user
            result = await db.execute(
                select(Project).where(Project.id == chat.project_id, Project.user_id == current_user.id)
            )
            project = result.scalars().first()
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
        
        db_chat = Chat(
            user_id=current_user.id,
            project_id=chat.project_id,
            title=chat.title
        )
        db.add(db_chat)
        await db.commit()
        await db.refresh(db_chat)
        
        logger.info(f"Chat created: {db_chat.id} by user {current_user.email}")
        return db_chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat creation failed")

@router.get("/", response_model=List[ChatSchema])
async def get_chats(
    project_id: str = None,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's chats"""
    try:
        query = select(Chat).where(Chat.user_id == current_user.id)
        if project_id:
            query = query.where(Chat.project_id == project_id)
        
        query = query.offset(skip).limit(limit).order_by(Chat.created_at.desc())
        result = await db.execute(query)
        chats = result.scalars().all()
        
        return chats
    except Exception as e:
        logger.error(f"Failed to get chats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chats")

@router.get("/{chat_id}", response_model=ChatSchema)
async def get_chat(
    chat_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific chat"""
    try:
        result = await db.execute(
            select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
        )
        chat = result.scalars().first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return chat
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat")

@router.get("/{chat_id}/messages", response_model=List[MessageSchema])
async def get_chat_messages(
    chat_id: str,
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get messages for a chat"""
    try:
        # Verify chat belongs to user
        result = await db.execute(
            select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
        )
        chat = result.scalars().first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .offset(skip)
            .limit(limit)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()
        
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get messages: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages")

@router.post("/ask", response_model=ChatResponse)
async def ask_question(
    chat_message: ChatMessage,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Ask a question and get response"""
    try:
        start_time = time.time()
        
        # Get or create chat
        chat_id = chat_message.chat_id
        if not chat_id:
            # Create new chat
            db_chat = Chat(user_id=current_user.id, project_id=chat_message.project_id)
            db.add(db_chat)
            await db.commit()
            await db.refresh(db_chat)
            chat_id = db_chat.id
        else:
            # Verify chat belongs to user
            result = await db.execute(
                select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
            )
            chat = result.scalars().first()
            if not chat:
                raise HTTPException(status_code=404, detail="Chat not found")
        
        # Save user message
        user_message = Message(
            chat_id=chat_id,
            role="user",
            content=chat_message.message
        )
        db.add(user_message)
        await db.commit()
        
        # Get chat history
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at)
            .limit(20)  # Last 20 messages
        )
        chat_history = result.scalars().all()
        
        # Search documents
        search_results = await search_documents(
            query=chat_message.message,
            user_id=str(current_user.id),
            project_id=str(chat_message.project_id) if chat_message.project_id else None
        )
        
        # Check if MemoRAG should be used
        use_memorag = chat_message.use_memorag if chat_message.use_memorag is not None else settings.memorag_enabled
        context = ""
        citations = []
        
        if use_memorag:
            memorag_service = MemoRAGService()
            # Query global memory
            global_memory = await memorag_service.query_global_memory(
                chat_message.message, 
                str(chat_message.project_id) if chat_message.project_id else None
            )
            context += f"Global Memory: {global_memory}\n\n"
        
        # Add retrieved chunks to context
        for result in search_results:
            context += f"Document: {result['content']}\n"
            citations.append({
                "page": result["metadata"].get("page_number"),
                "content": result["content"][:200] + "..."
            })
        
        # Generate response
        response_text = await generate_response(
            query=chat_message.message,
            context=context,
            chat_history=[{"role": msg.role, "content": msg.content} for msg in chat_history]
        )
        
        # Save assistant message
        assistant_message = Message(
            chat_id=chat_id,
            role="assistant",
            content=response_text,
            citations=citations
        )
        db.add(assistant_message)
        await db.commit()
        
        latency = int((time.time() - start_time) * 1000)
        
        # Log query
        from models import QueryLog
        query_log = QueryLog(
            user_id=current_user.id,
            prompt=chat_message.message,
            response=response_text,
            latency_ms=latency,
            citations=citations
        )
        db.add(query_log)
        await db.commit()
        
        logger.info(f"Question answered for user {current_user.email}, latency: {latency}ms")
        
        return ChatResponse(
            response=response_text,
            citations=citations,
            latency_ms=latency
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Question failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process question")

@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a chat"""
    try:
        result = await db.execute(
            select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
        )
        chat = result.scalars().first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        await db.delete(chat)
        await db.commit()
        
        logger.info(f"Chat deleted: {chat_id} by user {current_user.email}")
        return {"message": "Chat deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Delete failed")
