from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from database import get_db
from models import User as UserModel
from schemas import UserCreate, User as UserSchema, Token, UserLogin
from auth import get_password_hash, verify_password, create_access_token, get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/register", response_model=UserSchema)
async def register(user: UserCreate, db: AsyncSession = Depends(get_db)):
    """Register a new user"""
    try:
        # Check if user exists
        result = await db.execute(select(UserModel).where(UserModel.email == user.email))
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create new user
        hashed_password = get_password_hash(user.password)
        db_user = UserModel(email=user.email, password_hash=hashed_password)
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        logger.info(f"User registered: {user.email}")
        return db_user
    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Registration failed")

@router.post("/login", response_model=Token)
async def login(user_credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """Login user and return access token"""
    try:
        result = await db.execute(select(UserModel).where(UserModel.email == user_credentials.email))
        user_obj = result.scalars().first()
        
        if not user_obj or not verify_password(user_credentials.password, user_obj.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user_obj.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")
        
        access_token = create_access_token(data={"sub": user_obj.email})
        
        logger.info(f"User logged in: {user_obj.email}")
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Login failed")

@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: UserModel = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user

@router.put("/me", response_model=UserSchema)
async def update_user(
    email: str = None,
    password: str = None,
    current_user: UserModel = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user information"""
    try:
        if email:
            # Check if email is already taken
            result = await db.execute(select(UserModel).where(UserModel.email == email))
            existing_user = result.scalars().first()
            if existing_user and existing_user.id != current_user.id:
                raise HTTPException(status_code=400, detail="Email already taken")
            current_user.email = email
        
        if password:
            current_user.password_hash = get_password_hash(password)
        
        await db.commit()
        await db.refresh(current_user)
        
        logger.info(f"User updated: {current_user.email}")
        return current_user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User update failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Update failed")
