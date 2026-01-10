"""
MongoDB data models for 4Sight Backend.
"""

from datetime import datetime
from typing import Optional, List
from enum import Enum
from bson import ObjectId


class VoteType(str, Enum):
    """Vote type enumeration."""
    UP = "up"
    DOWN = "down"


class User:
    """User model for MongoDB."""
    
    @staticmethod
    def create_doc(username: str, email: str, hashed_password: str):
        """Create a user document."""
        return {
            "_id": ObjectId(),
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow(),
        }
    
    @staticmethod
    def to_response(doc: dict):
        """Convert MongoDB document to response format."""
        return {
            "id": str(doc["_id"]),
            "username": doc["username"],
            "email": doc["email"],
            "created_at": doc["created_at"],
        }


class Vote:
    """Vote model for MongoDB."""
    
    @staticmethod
    def create_doc(user_id: str, post_slug: str, vote_type: str):
        """Create a vote document."""
        return {
            "_id": ObjectId(),
            "user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id,
            "post_slug": post_slug,
            "vote_type": vote_type,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    
    @staticmethod
    def to_response(doc: dict):
        """Convert MongoDB document to response format."""
        return {
            "id": str(doc["_id"]),
            "user_id": str(doc["user_id"]),
            "post_slug": doc["post_slug"],
            "vote_type": doc["vote_type"],
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
        }


class Comment:
    """Comment model for MongoDB."""
    
    @staticmethod
    def create_doc(user_id: str, post_slug: str, text: str):
        """Create a comment document."""
        return {
            "_id": ObjectId(),
            "user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id,
            "post_slug": post_slug,
            "text": text,
            "created_at": datetime.utcnow(),
        }
    
    @staticmethod
    def to_response(doc: dict):
        """Convert MongoDB document to response format."""
        return {
            "id": str(doc["_id"]),
            "user_id": str(doc["user_id"]),
            "post_slug": doc["post_slug"],
            "text": doc["text"],
            "created_at": doc["created_at"],
        }
