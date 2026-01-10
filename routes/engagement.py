"""
Blog engagement routes (votes, comments) using MongoDB for 4Sight Backend.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from bson import ObjectId

from database import Database, get_db
from routes.auth import get_current_user, require_auth
from models.db_models import Vote, Comment

router = APIRouter(prefix="/posts", tags=["Engagement"])


# Pydantic schemas
class VoteCreate(BaseModel):
    vote_type: str  # "up" or "down"


class VoteResponse(BaseModel):
    upvotes: int
    downvotes: int
    user_vote: Optional[str] = None


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    id: str
    username: str
    text: str
    created_at: datetime
    is_own: bool = False


# ============ VOTES ============

@router.get("/{slug}/votes", response_model=VoteResponse)
def get_votes(
    slug: str,
    db: Database = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """Get vote counts for a post"""
    votes = db.get_collection('votes')
    
    # Count upvotes
    upvotes = votes.count_documents({"post_slug": slug, "vote_type": "up"})
    
    # Count downvotes
    downvotes = votes.count_documents({"post_slug": slug, "vote_type": "down"})
    
    # Get current user's vote if authenticated
    user_vote = None
    if current_user:
        user_vote_doc = votes.find_one({
            "post_slug": slug,
            "user_id": ObjectId(current_user['id'])
        })
        if user_vote_doc:
            user_vote = user_vote_doc['vote_type']
    
    return VoteResponse(upvotes=upvotes, downvotes=downvotes, user_vote=user_vote)


@router.post("/{slug}/votes", response_model=VoteResponse)
def submit_vote(
    slug: str,
    vote_data: VoteCreate,
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """Submit or update a vote for a post"""
    votes = db.get_collection('votes')
    vote_type = vote_data.vote_type
    
    if vote_type not in ('up', 'down'):
        raise HTTPException(status_code=400, detail="Vote type must be 'up' or 'down'")
    
    user_id = ObjectId(current_user['id'])
    
    # Check if user already voted
    existing_vote = votes.find_one({
        "post_slug": slug,
        "user_id": user_id
    })
    
    if existing_vote:
        if existing_vote['vote_type'] == vote_type:
            # Same vote type - remove the vote (toggle off)
            votes.delete_one({"_id": existing_vote['_id']})
        else:
            # Different vote type - update the vote
            votes.update_one(
                {"_id": existing_vote['_id']},
                {"$set": {"vote_type": vote_type, "updated_at": datetime.utcnow()}}
            )
    else:
        # New vote
        vote_doc = Vote.create_doc(str(user_id), slug, vote_type)
        votes.insert_one(vote_doc)
    
    # Return updated counts
    return get_votes(slug, db, current_user)


# ============ COMMENTS ============

@router.get("/{slug}/comments", response_model=List[CommentResponse])
def get_comments(
    slug: str,
    db: Database = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user)
):
    """Get all comments for a post"""
    comments_coll = db.get_collection('comments')
    users_coll = db.get_collection('users')
    
    comments = comments_coll.find({"post_slug": slug}).sort("created_at", -1)
    
    result = []
    for comment in comments:
        user = users_coll.find_one({"_id": comment['user_id']})
        username = user['username'] if user else "Unknown"
        
        result.append(CommentResponse(
            id=str(comment['_id']),
            username=username,
            text=comment['text'],
            created_at=comment['created_at'],
            is_own=current_user is not None and str(comment['user_id']) == current_user['id']
        ))
    
    return result


@router.post("/{slug}/comments", response_model=CommentResponse)
def add_comment(
    slug: str,
    comment_data: CommentCreate,
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """Add a comment to a post"""
    comments_coll = db.get_collection('comments')
    
    comment_doc = Comment.create_doc(current_user['id'], slug, comment_data.text)
    result = comments_coll.insert_one(comment_doc)
    
    created_comment = comments_coll.find_one({"_id": result.inserted_id})
    
    return CommentResponse(
        id=str(created_comment['_id']),
        username=current_user['username'],
        text=created_comment['text'],
        created_at=created_comment['created_at'],
        is_own=True
    )


@router.delete("/{slug}/comments/{comment_id}")
def delete_comment(
    slug: str,
    comment_id: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    """Delete a comment (only the author can delete)"""
    comments_coll = db.get_collection('comments')
    
    comment = comments_coll.find_one({"_id": ObjectId(comment_id)})
    
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    
    if str(comment['user_id']) != current_user['id']:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own comments")
    
    comments_coll.delete_one({"_id": ObjectId(comment_id)})
    return {"message": "Comment deleted"}
