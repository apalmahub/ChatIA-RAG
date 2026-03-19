from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class User(UserBase):
    id: UUID
    is_active: bool
    is_superuser: bool
    created_at: Any
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# Project schemas
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class Project(ProjectBase):
    id: UUID
    user_id: UUID
    created_at: Any
    
    class Config:
        from_attributes = True

# Document schemas
class DocumentBase(BaseModel):
    filename: str

class DocumentCreate(DocumentBase):
    project_id: UUID

class Document(DocumentBase):
    id: UUID
    project_id: UUID
    file_path: str
    num_pages: Optional[int]
    token_count: Optional[int]
    status: str
    created_at: Any
    
    class Config:
        from_attributes = True

# Chat schemas
class ChatBase(BaseModel):
    title: Optional[str] = None

class ChatCreate(ChatBase):
    project_id: Optional[UUID] = None

class Chat(ChatBase):
    id: UUID
    user_id: UUID
    project_id: Optional[UUID]
    created_at: Any
    
    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    role: str
    content: str
    citations: Optional[Dict[str, Any]] = None

class MessageCreate(MessageBase):
    chat_id: UUID

class Message(MessageBase):
    id: UUID
    chat_id: UUID
    created_at: Any
    
    class Config:
        from_attributes = True

# Chat message for API
class ChatMessage(BaseModel):
    message: str
    chat_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    use_memorag: Optional[bool] = None

class ChatResponse(BaseModel):
    response: str
    citations: List[Dict[str, Any]]
    latency_ms: int
