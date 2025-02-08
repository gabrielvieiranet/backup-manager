from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import UUID4, BaseModel, Field, validator


class ExecutionStatus(str, Enum):
    """Status possíveis de uma execução"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ExecutionBase(BaseModel):
    """Schema base para execuções"""

    job_id: UUID4
    status: ExecutionStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    total_files: Optional[int] = Field(None, ge=0)
    processed_files: Optional[int] = Field(None, ge=0)
    total_size: Optional[int] = Field(None, ge=0)  # em bytes
    processed_size: Optional[int] = Field(None, ge=0)  # em bytes
    current_file: Optional[str] = None
    error_message: Optional[str] = None
    error_details: Optional[str] = None
    log_file: Optional[str] = None
    metadata: Optional[Dict] = None

    @validator("processed_files")
    def validate_processed_files(cls, v, values):
        """Valida se o número de arquivos processados não excede o total"""
        if v is not None and values.get("total_files") is not None:
            if v > values["total_files"]:
                raise ValueError("Processed files cannot exceed total files")
        return v

    @validator("processed_size")
    def validate_processed_size(cls, v, values):
        """Valida se o tamanho processado não excede o total"""
        if v is not None and values.get("total_size") is not None:
            if v > values["total_size"]:
                raise ValueError("Processed size cannot exceed total size")
        return v

    @property
    def progress_percentage(self) -> float:
        """Calcula o percentual de progresso baseado nos arquivos"""
        if not self.total_files or not self.processed_files:
            return 0.0
        return round((self.processed_files / self.total_files) * 100, 2)

    @property
    def size_percentage(self) -> float:
        """Calcula o percentual de progresso baseado no tamanho"""
        if not self.total_size or not self.processed_size:
            return 0.0
        return round((self.processed_size / self.total_size) * 100, 2)

    @property
    def duration(self) -> Optional[float]:
        """Calcula a duração em segundos"""
        if not self.end_time:
            return None
        return (self.end_time - self.start_time).total_seconds()


class ExecutionCreate(BaseModel):
    """Schema para criar uma execução"""

    job_id: UUID4
    total_files: Optional[int] = Field(None, ge=0)
    total_size: Optional[int] = Field(None, ge=0)
    metadata: Optional[Dict] = None


class ExecutionUpdate(BaseModel):
    """Schema para atualizar uma execução"""

    processed_files: Optional[int] = Field(None, ge=0)
    processed_size: Optional[int] = Field(None, ge=0)
    current_file: Optional[str] = None
    status: Optional[ExecutionStatus] = None
    error_message: Optional[str] = None
    error_details: Optional[str] = None


class ExecutionResponse(ExecutionBase):
    """Schema para resposta da API"""

    id: UUID4

    class Config:
        from_attributes = True


class ExecutionFilter(BaseModel):
    """Schema para filtrar execuções"""

    job_id: Optional[UUID4] = None
    status: Optional[ExecutionStatus] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ExecutionLogResponse(BaseModel):
    """Schema para resposta de logs de execução"""

    content: str


class ExecutionStats(BaseModel):
    """Schema para estatísticas de execuções"""

    period_days: int
    total_executions: int
    successful_executions: int
    failed_executions: int
    success_rate: float
    total_files_processed: int
    total_size_processed: int  # em bytes
    avg_execution_time: float  # em segundos

    @property
    def formatted_total_size(self) -> str:
        """Retorna o tamanho total formatado"""
        sizes = ["B", "KB", "MB", "GB", "TB"]
        size = float(self.total_size_processed)
        for unit in sizes:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"


class ExecutionSummary(BaseModel):
    """Schema para resumo diário/mensal de execuções"""

    date: datetime
    total_executions: int
    successful: int
    failed: int
    stopped: int
    total_files: int
    total_size: int  # em bytes
    avg_duration: float  # em segundos


class ExecutionLogEntry(BaseModel):
    """Schema para entrada de log de execução"""

    timestamp: datetime
    level: str
    message: str
    file: Optional[str] = None
    size: Optional[int] = None
    elapsed_time: Optional[float] = None

    def to_csv(self) -> str:
        """Converte a entrada para formato CSV"""
        return (
            f"{self.timestamp.isoformat()},{self.level},"
            f"{self.message},{self.file or ''},"
            f"{self.size or ''},0,{self.elapsed_time or ''}\n"
        )


# Exemplos de uso:
"""
# Criar uma execução
execution_data = ExecutionCreate(
    job_id="123e4567-e89b-12d3-a456-426614174000",
    total_files=1000,
    total_size=1024*1024*100  # 100 MB
)

# Atualizar progresso
update_data = ExecutionUpdate(
    processed_files=500,
    processed_size=1024*1024*50,  # 50 MB
    current_file="documents/file.txt"
)

# Registrar log
log_entry = ExecutionLogEntry(
    timestamp=datetime.utcnow(),
    level="INFO",
    message="Processing file",
    file="documents/file.txt",
    size=1024*1024,  # 1 MB
    elapsed_time=0.5
)
log_line = log_entry.to_csv()

# Filtrar execuções
filter_params = ExecutionFilter(
    status=ExecutionStatus.COMPLETED,
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)
"""
