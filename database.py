"""
MongoDB connection and initialization for 4Sight Backend.

This module manages MongoDB connections using pymongo.
"""

import os
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
import logging
from config import settings

load_dotenv()

logger = logging.getLogger(__name__)

# MongoDB connection string
MONGODB_URL = os.getenv("MONGODB_URL", settings.mongodb_url)
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", settings.mongodb_db_name)

# Global MongoDB client
_client = None
_db = None


def get_mongo_client():
    """Get or create MongoDB client."""
    global _client
    if _client is None:
        try:
            _client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
            # Test connection
            _client.admin.command('ping')
            logger.info("Connected to MongoDB successfully!")
        except ServerSelectionTimeoutError as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    return _client


def get_database():
    """Get MongoDB database instance."""
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[MONGODB_DB_NAME]
    return _db


def initialize_collections():
    """Initialize MongoDB collections with indexes."""
    db = get_database()
    
    try:
        # Create collections if they don't exist
        collections = db.list_collection_names()
        
        # Users collection
        if 'users' not in collections:
            db.create_collection('users')
            logger.info("Created 'users' collection")
        
        # Create unique indexes on users
        db['users'].create_index('username', unique=True)
        db['users'].create_index('email', unique=True)
        
        # Votes collection
        if 'votes' not in collections:
            db.create_collection('votes')
            logger.info("Created 'votes' collection")
        
        # Create indexes on votes
        db['votes'].create_index([('user_id', 1), ('post_slug', 1)], unique=True)
        db['votes'].create_index('post_slug')
        db['votes'].create_index('user_id')
        
        # Comments collection
        if 'comments' not in collections:
            db.create_collection('comments')
            logger.info("Created 'comments' collection")
        
        # Create indexes on comments
        db['comments'].create_index('post_slug')
        db['comments'].create_index('user_id')
        db['comments'].create_index('created_at')
        
        logger.info("MongoDB collections and indexes initialized successfully!")
    except Exception as e:
        logger.error(f"Error initializing collections: {e}")
        raise


class Database:
    """MongoDB database wrapper for dependency injection."""
    
    def __init__(self):
        self.db = get_database()
    
    def get_collection(self, collection_name: str):
        """Get a MongoDB collection."""
        return self.db[collection_name]

def get_db():
    """Dependency to get database instance."""
    return Database()