"""
4Sight Backend - FastAPI Application

Production-quality API with:
- SEO Maturity Grader
- User Authentication (signup/signin)
- Blog Engagement (votes, comments)

Environment Variables:
    See config.py for complete list and descriptions.
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from config import settings, get_service_status
from models.schemas import (
    GraderRequest,
    GraderResponse,
    HealthResponse,
    ServiceStatus,
    ErrorResponse,
)
from evaluators.declared_evaluator import DeclaredEvaluator
from evaluators.observed_evaluator import ObservedEvaluator
from evaluators.scoring import generate_grader_response
from utils.url_validator import validate_url

# Import database and auth routes
from routes import auth, engagement

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Initialize MongoDB collections
    logger.info("Initializing MongoDB collections...")
    try:
        from database import initialize_collections
        initialize_collections()
        logger.info("MongoDB collections initialized successfully!")
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB: {e}")
        raise
    
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Service status: {get_service_status()}")
    yield
    logger.info("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title="4Sight Backend",
    version=settings.app_version,
    description="4Sight API - SEO Maturity Grader, Authentication, and Blog Engagement",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include auth and engagement routers
app.include_router(auth.router)
app.include_router(engagement.router)


# Error handlers
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors."""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Invalid input data",
            details={"errors": exc.errors()},
        ).model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.exception(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An unexpected error occurred. Please try again.",
        ).model_dump(),
    )


# Health endpoint
@app.get(
    "/seo/grader/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check endpoint",
)
async def health_check() -> HealthResponse:
    """
    Check API health and service configuration status.
    
    Returns basic readiness information including which
    external services are configured.
    """
    service_status = get_service_status()
    
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        services=ServiceStatus(**service_status),
    )


# Main grader endpoint
@app.post(
    "/seo/grader/submit",
    response_model=GraderResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Grader"],
    summary="Submit website for SEO maturity grading",
)
async def submit_grader(request: GraderRequest) -> GraderResponse:
    """
    Analyze a website and compute SEO maturity score.
    
    This endpoint accepts website URL, brand category, target keywords,
    and questionnaire answers. It returns a deterministic, presentation-ready
    JSON response with scores, stage label, risks, and raw signals.
    
    **Scoring Model:**
    - Questionnaire (declared): 50 points
    - Observed (website): 50 points
    - Total: 0-100
    
    **Stages:**
    - Chaotic (0-30)
    - Reactive (31-50)
    - Structured (51-70)
    - Optimised (71-85)
    - Strategic (86-100)
    """
    request_id = request.client_request_id
    logger.info(f"Grader request received [request_id={request_id}]")
    
    # Validate URL
    is_valid, normalized_url, url_error = validate_url(request.website_url)
    if not is_valid:
        logger.warning(f"Invalid URL: {url_error} [request_id={request_id}]")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid URL: {url_error}",
        )
    
    # Log warning for HTTP
    if url_error and "HTTP URL" in url_error:
        logger.warning(f"HTTP URL submitted: {normalized_url} [request_id={request_id}]")
    
    try:
        # Evaluate declared (questionnaire)
        declared_evaluator = DeclaredEvaluator()
        declared_result = declared_evaluator.evaluate(request.questionnaire_answers)
        logger.debug(f"Declared score: {declared_result.total} [request_id={request_id}]")
        
        # Evaluate observed (website)
        observed_evaluator = ObservedEvaluator()
        observed_result = await observed_evaluator.evaluate(
            url=normalized_url,
            keywords=request.target_keywords,
            brand_name=request.brand_category,  # Use category as brand hint
        )
        logger.debug(f"Observed score: {observed_result.total} [request_id={request_id}]")
        
        # Generate final response
        response = generate_grader_response(declared_result, observed_result)
        
        logger.info(
            f"Grader complete: score={response.total_score}, stage={response.stage} "
            f"[request_id={request_id}]"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Grader error: {e} [request_id={request_id}]")
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze website. Please try again.",
        )


# Root redirect
@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint."""
    return {"message": "4Sight Backend API", "docs": "/docs", "health": "/seo/grader/health"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
