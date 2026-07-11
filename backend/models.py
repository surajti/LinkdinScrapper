from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from .database import Base

class ProcessedJob(Base):
    __tablename__ = "processed_jobs"

    id = Column(Integer, primary_key=True, index=True)
    linkedin_url = Column(String, unique=True, index=True)
    job_title = Column(String)
    company = Column(String)
    location = Column(String)
    experience_text = Column(String, nullable=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

class DeletedJob(Base):
    __tablename__ = "deleted_jobs"

    id = Column(Integer, primary_key=True, index=True)
    linkedin_url = Column(String, unique=True, index=True)
    job_title = Column(String)
    company = Column(String)
    location = Column(String)
    deleted_at = Column(DateTime(timezone=True), server_default=func.now())
