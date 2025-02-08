# models/job.py
import uuid
from datetime import datetime
from enum import Enum

from core.database import Base
from sqlalchemy import Column, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID


class JobType(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"


class ScheduleType(str, Enum):
    MONTHLY = "monthly"
    DAILY = "daily"
    ONCE = "once"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    source_path = Column(String, nullable=False)
    destination_path = Column(String, nullable=False)
    job_type = Column(SQLEnum(JobType), nullable=False)
    schedule_type = Column(SQLEnum(ScheduleType), nullable=False)
    schedule_value = Column(
        String, nullable=False
    )  # JSON string para dias/datas
    schedule_time = Column(String, nullable=False)  # formato HH:MM
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    active = Column(Boolean, default=True)


# models/execution.py
class Execution(Base):
    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    status = Column(
        String, nullable=False
    )  # running, completed, failed, stopped
    total_files = Column(Integer, nullable=True)
    total_size = Column(BigInteger, nullable=True)  # em bytes
    processed_files = Column(Integer, nullable=True)
    processed_size = Column(BigInteger, nullable=True)  # em bytes
    error_message = Column(String, nullable=True)


from datetime import datetime
from typing import Optional
from uuid import UUID

# schemas/job.py
from pydantic import BaseModel


class JobBase(BaseModel):
    name: str
    source_path: str
    destination_path: str
    job_type: JobType
    schedule_type: ScheduleType
    schedule_value: str
    schedule_time: str


class JobCreate(JobBase):
    pass


class JobUpdate(JobBase):
    active: Optional[bool] = None


class Job(JobBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    active: bool

    class Config:
        from_attributes = True
