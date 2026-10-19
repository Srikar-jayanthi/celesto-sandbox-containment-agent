import re
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, field_validator
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

SANDBOX_REGEX = re.compile(r"^sbx-[a-z0-9]{8,}$")
VALID_STATES = {"created", "ready", "running", "succeeded", "failed", "deleted"}
REQUIRED_EXECUTION_TARGET = "celesto_sandbox"


class RunRecord(Base):
    __tablename__ = "runs"

    run_id = Column(String(128), primary_key=True)
    sandbox_name = Column(String(128), unique=True, nullable=False, index=True)
    problem_id = Column(String(128), nullable=False)
    state = Column(String(64), nullable=False, index=True)
    execution_target = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "sandbox_name": self.sandbox_name,
            "problem_id": self.problem_id,
            "state": self.state,
            "execution_target": self.execution_target,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RunCreateRequest(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str

    @field_validator("sandbox_name")
    @classmethod
    def validate_sandbox_name(cls, v: str) -> str:
        if not isinstance(v, str) or not SANDBOX_REGEX.match(v):
            raise ValueError(f"Invalid sandbox_name: '{v}'. Must match pattern '^sbx-[a-z0-9]{{8,}}$'")
        return v

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if v not in VALID_STATES:
            raise ValueError(f"Invalid state: '{v}'. Must be one of {sorted(list(VALID_STATES))}")
        return v

    @field_validator("execution_target")
    @classmethod
    def validate_execution_target(cls, v: str) -> str:
        if v != REQUIRED_EXECUTION_TARGET:
            raise ValueError(f"Invalid execution_target: '{v}'. Must be exactly '{REQUIRED_EXECUTION_TARGET}'")
        return v


class RunResponse(BaseModel):
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
