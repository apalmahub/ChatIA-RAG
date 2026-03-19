from groq import AsyncGroq
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
import logging

from config import settings

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.groq_client = None
        self.openai_client = None
        self.deepseek_client = None
        
        try:
            if settings.groq_api_key and "placeholder" not in settings.groq_api_key:
                self.groq_client = AsyncGroq(api_key=settings.groq_api_key)
            
            if settings.openai_api_key and "placeholder" not in settings.openai_api_key:
                self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
                
            if settings.deepseek_api_key and "placeholder" not in settings.deepseek_api_key:
                # DeepSeek is OpenAI-compatible
                self.deepseek_client = AsyncOpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url="https://api.deepseek.com"
                )
            logger.info("LLM Clients initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing LLM clients: {str(e)}")
    
    async def generate_response(
        self,
        query: str,
        context: str = "",
        chat_history: List[Dict[str, str]] = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000
    ) -> str:
        """Generate response using available LLM"""
        try:
            if chat_history is None:
                chat_history = []
            
            # Prioritize DeepSeek as requested by user
            active_model = model or settings.default_llm_model
            
            # Prepare messages
            system_message = "You are a helpful assistant that answers questions based on the provided context. Include page references when possible."
            if context:
                system_message += f"\n\nContext:\n{context}"
            
            messages = [{"role": "system", "content": system_message}]
            messages.extend(chat_history[-10:])
            messages.append({"role": "user", "content": query})
            
            # 1. Use DeepSeek if possible (it's our primary now)
            if self.deepseek_client:
                ds_model = active_model if "deepseek" in active_model.lower() else "deepseek-chat"
                try:
                    return await self._call_deepseek(messages, ds_model, temperature, max_tokens)
                except Exception as e:
                    logger.warning(f"DeepSeek failed, falling back: {str(e)}")

            # 2. Use Groq
            if self.groq_client and "llama" in active_model.lower():
                try:
                    return await self._call_groq(messages, active_model, temperature, max_tokens)
                except Exception as e:
                    logger.warning(f"Groq failed, falling back: {str(e)}")

            # 3. Use OpenAI
            if self.openai_client:
                o_model = active_model if "gpt" in active_model.lower() else "gpt-3.5-turbo"
                return await self._call_openai(messages, o_model, temperature, max_tokens)
            
            raise Exception("No LLM client available or all fallback failed")
            
        except Exception as e:
            logger.error(f"LLM generation failed: {str(e)}")
            raise
    
    async def _call_deepseek(self, messages, model, temperature, max_tokens):
        response = await self.deepseek_client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.choices[0].message.content

    async def _call_groq(self, messages, model, temperature, max_tokens):
        response = await self.groq_client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.choices[0].message.content
    
    async def _call_openai(self, messages, model, temperature, max_tokens):
        response = await self.openai_client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.choices[0].message.content

# Create global instance
llm_service = LLMService()

# Export standalone function
async def generate_response(
    query: str,
    context: str = "",
    chat_history: List[Dict[str, str]] = None,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 2000
) -> str:
    return await llm_service.generate_response(query, context, chat_history, model, temperature, max_tokens)
