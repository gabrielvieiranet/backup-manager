import os
from datetime import datetime, time
from enum import Enum
from typing import List, Optional

from pydantic import UUID4, BaseModel, Field, validator


class JobType(str, Enum):
    """Tipos de backup suportados"""

    FULL = "full"
    INCREMENTAL = "incremental"


class ScheduleType(str, Enum):
    """Tipos de agendamento suportados"""

    MONTHLY = "monthly"
    DAILY = "daily"
    ONCE = "once"


class DayOfWeek(str, Enum):
    """Dias da semana para agendamento"""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class JobBase(BaseModel):
    """Schema base para jobs de backup"""

    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    source_path: str = Field(
        ..., min_length=1, max_length=260
    )  # Windows MAX_PATH
    destination_path: str = Field(..., min_length=1, max_length=260)
    job_type: JobType
    schedule_type: ScheduleType
    schedule_time: time

    # Campos específicos para cada tipo de agendamento
    schedule_days: Optional[List[DayOfWeek]] = None  # Para agendamento diário
    schedule_day: Optional[int] = Field(
        None, ge=1, le=31
    )  # Para agendamento mensal
    schedule_date: Optional[datetime] = None  # Para agendamento único

    @validator("source_path")
    def validate_source_path(cls, v):
        """Valida se o caminho de origem é válido"""
        if not os.path.exists(v):
            raise ValueError(f"Source path does not exist: {v}")
        return os.path.normpath(v)

    @validator("destination_path")
    def validate_destination_path(cls, v):
        """Valida se o caminho de destino é válido"""
        return os.path.normpath(v)

    @validator("schedule_days")
    def validate_schedule_days(cls, v, values):
        """Valida os dias selecionados para agendamento diário"""
        if values.get("schedule_type") == ScheduleType.DAILY and not v:
            raise ValueError("Schedule days are required for daily schedule")
        if values.get("schedule_type") != ScheduleType.DAILY and v:
            raise ValueError(
                "Schedule days should only be set for daily schedule"
            )
        return v

    @validator("schedule_day")
    def validate_schedule_day(cls, v, values):
        """Valida o dia do mês para agendamento mensal"""
        if values.get("schedule_type") == ScheduleType.MONTHLY and v is None:
            raise ValueError("Schedule day is required for monthly schedule")
        if (
            values.get("schedule_type") != ScheduleType.MONTHLY
            and v is not None
        ):
            raise ValueError(
                "Schedule day should only be set for monthly schedule"
            )
        return v

    @validator("schedule_date")
    def validate_schedule_date(cls, v, values):
        """Valida a data para agendamento único"""
        if values.get("schedule_type") == ScheduleType.ONCE and v is None:
            raise ValueError("Schedule date is required for one-time schedule")
        if values.get("schedule_type") != ScheduleType.ONCE and v is not None:
            raise ValueError(
                "Schedule date should only be set for one-time schedule"
            )
        if v and v < datetime.now():
            raise ValueError("Schedule date cannot be in the past")
        return v


class JobCreate(JobBase):
    """Schema para criação de job"""

    pass


class JobUpdate(JobBase):
    """Schema para atualização de job"""

    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    job_type: Optional[JobType] = None
    schedule_type: Optional[ScheduleType] = None
    schedule_time: Optional[time] = None
    is_active: Optional[bool] = None


class JobInDBBase(JobBase):
    """Schema base para job no banco de dados"""

    id: UUID4
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

    class Config:
        from_attributes = True


class JobResponse(JobInDBBase):
    """Schema para resposta da API"""

    pass


class JobStatus(str, Enum):
    """Status possíveis de um job"""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class JobProgress(BaseModel):
    """Schema para progresso de execução do job"""

    job_id: UUID4
    status: JobStatus
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_files: Optional[int] = None
    processed_files: Optional[int] = None
    total_size: Optional[int] = None  # em bytes
    processed_size: Optional[int] = None  # em bytes
    current_file: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def progress_percentage(self) -> Optional[float]:
        """Calcula o percentual de progresso"""
        if self.total_files and self.processed_files:
            return round((self.processed_files / self.total_files) * 100, 2)
        return None

    @property
    def size_progress_percentage(self) -> Optional[float]:
        """Calcula o percentual de progresso em tamanho"""
        if self.total_size and self.processed_size:
            return round((self.processed_size / self.total_size) * 100, 2)
        return None


# Exemplos de uso:
"""
# Criar job diário
daily_job = JobCreate(
    name="Daily Backup",
    description="Backup diário dos documentos",
    source_path="C:\\Documents",
    destination_path="D:\\Backup",
    job_type=JobType.INCREMENTAL,
    schedule_type=ScheduleType.DAILY,
    schedule_time=time(hour=23, minute=0),
    schedule_days=[DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY, DayOfWeek.FRIDAY]
)

# Criar job mensal
monthly_job = JobCreate(
    name="Monthly Backup",
    description="Backup mensal completo",
    source_path="C:\\Documents",
    destination_path="D:\\Backup",
    job_type=JobType.FULL,
    schedule_type=ScheduleType.MONTHLY,
    schedule_time=time(hour=22, minute=0),
    schedule_day=1  # Primeiro dia do mês
)

# Criar job único
one_time_job = JobCreate(
    name="One-time Backup",
    description="Backup único para migração",
    source_path="C:\\Documents",
    destination_path="D:\\Backup",
    job_type=JobType.FULL,
    schedule_type=ScheduleType.ONCE,
    schedule_time=time(hour=15, minute=30),
    schedule_date=datetime(2024, 12, 31, 15, 30)
)
"""
