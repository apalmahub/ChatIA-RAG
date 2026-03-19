import bcrypt
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

def get_password_hash(password: str) -> str:
    # Manual bcrypt hash to match passlib's bcrypt
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

async def create_users():
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://chatia_user:chatia_pass_2024@db:5432/chatia_db")
    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    users = [
        {
            "email": "administrador@hotmail.com",
            "password": "administrador*",
            "is_superuser": True
        },
        {
            "email": "usuario@hotmail.com",
            "password": "123456+",
            "is_superuser": False
        }
    ]

    async with async_session() as session:
        for user_data in users:
            # Check if exists
            result = await session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_data["email"]})
            row = result.fetchone()
            if row:
                print(f"User {user_data['email']} already exists. Updating...")
                query = text("UPDATE users SET password_hash = :hash, is_superuser = :is_admin WHERE email = :email")
                await session.execute(query, {
                    "hash": get_password_hash(user_data["password"]),
                    "is_admin": user_data["is_superuser"],
                    "email": user_data["email"]
                })
            else:
                print(f"Creating user {user_data['email']}...")
                query = text("INSERT INTO users (id, email, password_hash, is_active, is_superuser) VALUES (:id, :email, :hash, true, :is_admin)")
                await session.execute(query, {
                    "id": str(uuid.uuid4()),
                    "email": user_data["email"],
                    "hash": get_password_hash(user_data["password"]),
                    "is_admin": user_data["is_superuser"]
                })
        await session.commit()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(create_users())
