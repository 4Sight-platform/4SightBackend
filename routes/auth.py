"""
Authentication routes using MongoDB for 4Sight Backend.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId

from database import Database, get_db
from config import settings
from models.db_models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])

# JWT Bearer scheme
security = HTTPBearer(auto_error=False)


# Pydantic schemas
class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_db)
) -> Optional[dict]:
    """Get the current user from JWT token (returns None if not authenticated)"""
    if not credentials:
        return None
    
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        users = db.get_collection('users')
        user = users.find_one({"_id": ObjectId(user_id)})
        
        if user:
            return {
                "id": str(user["_id"]),
                "username": user["username"],
                "email": user["email"],
                "created_at": user["created_at"]
            }
        return None
    except JWTError:
        return None
    except Exception:
        return None


def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_db)
) -> dict:
    """Require authentication - raises 401 if not authenticated"""
    user = get_current_user(credentials, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/signup", response_model=Token)
def signup(user_data: UserCreate, db: Database = Depends(get_db)):
    """Register a new user"""
    users = db.get_collection('users')
    
    # Check if email already exists
    if users.find_one({"email": user_data.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    if users.find_one({"username": user_data.username}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user
    hashed_pw = hash_password(user_data.password)
    user_doc = User.create_doc(user_data.username, user_data.email, hashed_pw)
    result = users.insert_one(user_doc)
    
    # Get created user
    created_user = users.find_one({"_id": result.inserted_id})
    
    # Create token
    access_token = create_access_token({"sub": str(created_user['_id'])})
    
    return Token(
        access_token=access_token,
        user=UserResponse(
            id=str(created_user["_id"]),
            username=created_user["username"],
            email=created_user["email"],
            created_at=created_user["created_at"]
        )
    )


@router.post("/signin", response_model=Token)
def signin(credentials: UserLogin, db: Database = Depends(get_db)):
    """Sign in and get access token"""
    users = db.get_collection('users')
    
    # Find user by email
    user = users.find_one({"email": credentials.email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Verify password
    if not verify_password(credentials.password, user['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create token
    access_token = create_access_token({"sub": str(user['_id'])})
    
    return Token(
        access_token=access_token,
        user=UserResponse(
            id=str(user["_id"]),
            username=user["username"],
            email=user["email"],
            created_at=user["created_at"]
        )
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(require_auth)):
    """Get current authenticated user"""
    return UserResponse(**current_user)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(require_auth)):
    """Get current authenticated user"""
    return UserResponse(**current_user)
