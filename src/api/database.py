import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.api.models import Base, RunRecord

logger = logging.getLogger("run_ledger.database")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ledger.db")

# Convert postgres:// to postgresql:// if needed for newer SQLAlchemy
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Ensure seed record exists if table is empty
    with SessionLocal() as db:
        seed_sandbox = "sbx-seeddemo1"
        existing = db.query(RunRecord).filter(RunRecord.sandbox_name == seed_sandbox).first()
        if not existing:
            seed_row = RunRecord(
                run_id="run-seed-demo-001",
                sandbox_name=seed_sandbox,
                problem_id="problem-detonator-01",
                state="deleted",
                execution_target="celesto_sandbox",
            )
            db.add(seed_row)
            try:
                db.commit()
                logger.info(f"Initialized seed row for {seed_sandbox}")
            except Exception as e:
                db.rollback()
                logger.warning(f"Seed row initialization note: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
