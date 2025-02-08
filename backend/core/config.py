import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseSettings


class Settings(BaseSettings):
    """
    Configurações da aplicação usando Pydantic.
    Os valores podem ser sobrescritos por variáveis de ambiente.
    """

    # Nome do Projeto
    PROJECT_NAME: str = "Backup System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # Servidor
    SERVER_HOST: str = "localhost"
    SERVER_PORT: int = 8000
    DEBUG: bool = True

    # Segurança
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas

    # Banco de Dados
    DATABASE_URL: str = "sqlite:///./backup_system.db"

    # Configurações de Backup
    BACKUP_LOG_DIR: Path = Path("logs")
    BACKUP_LOG_RETENTION_DAYS: int = 180  # 6 meses

    # Configurações do Worker
    WORKER_PROCESS_TIMEOUT: int = 3600  # 1 hora em segundos
    MAX_CONCURRENT_JOBS: int = 3

    # Configurações de Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Configurações de CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Frontend React/Next.js
        "http://localhost:8000",  # Backend
        "http://localhost",
    ]

    # Configurações de Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configurações de Email (opcional)
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None

    # Configurações Específicas do Windows
    WINDOWS_SHARE_USER: Optional[str] = None
    WINDOWS_SHARE_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True

    def configure_logging(self):
        """Configura o logging global do sistema"""
        import logging
        import sys

        # Configura o logger raiz
        logging.basicConfig(
            level=self.LOG_LEVEL,
            format=self.LOG_FORMAT,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("backup_system.log"),
            ],
        )

    def create_directories(self):
        """Cria os diretórios necessários para o sistema"""
        self.BACKUP_LOG_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna uma instância cacheada das configurações.
    Uso: settings = get_settings()
    """
    return Settings()
