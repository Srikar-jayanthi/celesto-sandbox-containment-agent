import os
import logging
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from src.api.database import init_db, get_db
from src.api.models import RunRecord, RunCreateRequest, RunResponse

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("run_ledger.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables and seed data if needed
    init_db()
    yield


app = FastAPI(
    title="Run Ledger API",
    description="Control plane ledger recording Celesto sandbox runs",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Ensure invalid payloads (such as bad sandbox_name, invalid state, or
    non-celesto_sandbox execution_target) return HTTP 400 per specification.
    """
    errors = exc.errors()
    error_messages = [f"{err.get('loc')}: {err.get('msg')}" for err in errors]
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Validation error", "errors": error_messages},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.get("/health")
def health_check():
    """Health check endpoint requested by Docker and orchestrators."""
    return {"status": "ok"}


@app.get("/api/runs", response_model=List[RunResponse])
def get_runs(db: Session = Depends(get_db)):
    """List all recorded sandbox runs."""
    records = db.query(RunRecord).order_by(RunRecord.created_at.asc()).all()
    return [rec.to_dict() for rec in records]


@app.post("/api/runs", status_code=status.HTTP_201_CREATED, response_model=RunResponse)
def create_run(payload: RunCreateRequest, db: Session = Depends(get_db)):
    """
    Record a new or updated sandbox run in the ledger.
    Requires execution_target to be 'celesto_sandbox'.
    """
    existing = db.query(RunRecord).filter(RunRecord.sandbox_name == payload.sandbox_name).first()
    if existing:
        existing.run_id = payload.run_id
        existing.problem_id = payload.problem_id
        existing.state = payload.state
        existing.execution_target = payload.execution_target
        db.commit()
        db.refresh(existing)
        return existing.to_dict()

    new_record = RunRecord(
        run_id=payload.run_id,
        sandbox_name=payload.sandbox_name,
        problem_id=payload.problem_id,
        state=payload.state,
        execution_target=payload.execution_target,
    )
    db.add(new_record)
    try:
        db.commit()
        db.refresh(new_record)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")

    return new_record.to_dict()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port, reload=False)
