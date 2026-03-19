from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://user:password@localhost/db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Security
    jwt_secret_key: str = "your-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    
    # LLM
    openai_api_key: str = ""
    groq_api_key: str = ""
    deepseek_api_key: str = ""
    huggingface_token: str = ""
    default_llm_model: str = "llama-3-70b-8192"
    
    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    
    # MemoRAG
    memorag_threshold_tokens: int = 20000
    memorag_enabled: bool = True
    
    # File Upload
    max_file_size_mb: int = 50
    allowed_extensions: str = "pdf"
    
    # App
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
