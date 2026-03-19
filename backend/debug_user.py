import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import User
import os

async def check():
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatia_user:chatia_pass_2024@db:5432/chatia_db")
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == "administrador@hotmail.com"))
        user = result.scalars().first()
        if user:
            print(f"Email: {user.email}")
            print(f"Is Superuser: {user.is_superuser}")
            print(f"Is Active: {user.is_active}")
        else:
            print("User not found")

if __name__ == "__main__":
    asyncio.run(check())
