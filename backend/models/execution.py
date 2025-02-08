import uuid
from datetime import datetime

from core.database import Base
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship


class Execution(Base):
    """
    Modelo para registrar as execuções dos jobs de backup.
    """

    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Status e timestamps
    status = Column(
        String(20), nullable=False
    )  # running, completed, failed, stopped
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)

    # Dados de progresso
    total_files = Column(Integer, nullable=True)
    processed_files = Column(Integer, nullable=True)
    total_size = Column(BigInteger, nullable=True)  # em bytes
    processed_size = Column(BigInteger, nullable=True)  # em bytes
    current_file = Column(String(500), nullable=True)

    # Informações de erro
    error_message = Column(Text, nullable=True)
    error_details = Column(Text, nullable=True)

    # Dados adicionais
    log_file = Column(String(255), nullable=True)  # caminho do arquivo de log
    metadata = Column(Text, nullable=True)  # JSON com dados adicionais

    # Relacionamentos
    job = relationship("Job", back_populates="executions")

    def __init__(self, **kwargs):
        """
        Inicializa uma nova execução.
        """
        super().__init__(**kwargs)
        if not self.status:
            self.status = "running"
        if not self.start_time:
            self.start_time = datetime.utcnow()

    @property
    def duration(self):
        """
        Calcula a duração da execução em segundos.
        """
        if not self.end_time:
            return None
        return (self.end_time - self.start_time).total_seconds()

    @property
    def progress_percentage(self):
        """
        Calcula o percentual de progresso baseado nos arquivos processados.
        """
        if not self.total_files or not self.processed_files:
            return 0
        return round((self.processed_files / self.total_files) * 100, 2)

    @property
    def size_percentage(self):
        """
        Calcula o percentual de progresso baseado no tamanho processado.
        """
        if not self.total_size or not self.processed_size:
            return 0
        return round((self.processed_size / self.total_size) * 100, 2)

    def complete(self):
        """
        Marca a execução como concluída.
        """
        self.status = "completed"
        self.end_time = datetime.utcnow()

    def fail(self, error_message: str, error_details: str = None):
        """
        Marca a execução como falha.
        """
        self.status = "failed"
        self.end_time = datetime.utcnow()
        self.error_message = error_message
        if error_details:
            self.error_details = error_details

    def stop(self):
        """
        Marca a execução como interrompida.
        """
        self.status = "stopped"
        self.end_time = datetime.utcnow()

    def update_progress(
        self,
        processed_files: int,
        processed_size: int,
        current_file: str = None,
    ):
        """
        Atualiza o progresso da execução.
        """
        self.processed_files = processed_files
        self.processed_size = processed_size
        if current_file:
            self.current_file = current_file

    def to_dict(self):
        """
        Converte a execução para um dicionário.
        """
        return {
            "id": str(self.id),
            "job_id": str(self.job_id),
            "status": self.status,
            "start_time": (
                self.start_time.isoformat() if self.start_time else None
            ),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "total_size": self.total_size,
            "processed_size": self.processed_size,
            "current_file": self.current_file,
            "error_message": self.error_message,
            "duration": self.duration,
            "progress_percentage": self.progress_percentage,
            "size_percentage": self.size_percentage,
        }

    def __repr__(self):
        return (
            f"<Execution(id={self.id}, "
            f"job_id={self.job_id}, "
            f"status={self.status}, "
            f"progress={self.progress_percentage}%)>"
        )


# Exemplo de uso:
"""
# Criar uma nova execução
execution = Execution(
    job_id=uuid.uuid4(),
    total_files=1000,
    total_size=1024*1024*100  # 100 MB
)

# Atualizar progresso
execution.update_progress(
    processed_files=500,
    processed_size=1024*1024*50,  # 50 MB
    current_file="documents/file.txt"
)

# Completar execução
execution.complete()

# Falhar execução
execution.fail(
    error_message="Access denied",
    error_details="Permission error on documents/file.txt"
)

# Parar execução
execution.stop()
"""
