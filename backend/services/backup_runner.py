import asyncio
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from uuid import UUID

from models.execution import Execution
from models.job import Job
from schemas.execution import ExecutionLogEntry, ExecutionStatus
from schemas.job import JobType
from sqlalchemy.ext.asyncio import AsyncSession


class BackupRunner:
    """Classe responsável por executar os jobs de backup"""

    def __init__(
        self, session: AsyncSession, job_id: UUID, execution_id: UUID
    ):
        self.session = session
        self.job_id = job_id
        self.execution_id = execution_id
        self.logger = self._setup_logger()
        self._stop_requested = False
        self.current_file = None
        self.processed_files = 0
        self.processed_size = 0

    async def run(self) -> None:
        """Executa o job de backup"""
        try:
            # Carrega o job e a execução
            job = await self._get_job()
            execution = await self._get_execution()

            # Mapeia arquivos
            files_info = await self._map_files(job.source_path)
            total_files = len(files_info)
            total_size = sum(info["size"] for info in files_info.values())

            # Atualiza informações na execução
            execution.total_files = total_files
            execution.total_size = total_size
            await self.session.commit()

            # Executa o backup
            await self._process_files(job, files_info)

            # Finaliza a execução se não foi parada
            if not self._stop_requested:
                execution.complete()
                await self.session.commit()

        except Exception as e:
            self._log_error(f"Backup failed: {str(e)}")
            await self._handle_error(str(e))
            raise

    async def stop(self) -> None:
        """Solicita a parada do backup"""
        self._stop_requested = True
        execution = await self._get_execution()
        execution.stop()
        await self.session.commit()

    def _setup_logger(self) -> logging.Logger:
        """Configura o logger para o job"""
        logger = logging.getLogger(f"backup_job_{self.job_id}")
        logger.setLevel(logging.INFO)

        # Cria o diretório de logs se não existir
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Configura o handler de arquivo
        log_file = (
            log_dir / f"{self.job_id}-{datetime.now().strftime('%Y%m%d')}.csv"
        )
        handler = logging.FileHandler(log_file)
        handler.setFormatter(
            logging.Formatter("%(asctime)s,%(levelname)s,%(message)s")
        )
        logger.addHandler(handler)

        return logger

    async def _get_job(self) -> Job:
        """Obtém o job do banco de dados"""
        job = await self.session.get(Job, self.job_id)
        if not job:
            raise ValueError(f"Job {self.job_id} not found")
        return job

    async def _get_execution(self) -> Execution:
        """Obtém a execução do banco de dados"""
        execution = await self.session.get(Execution, self.execution_id)
        if not execution:
            raise ValueError(f"Execution {self.execution_id} not found")
        return execution

    async def _map_files(self, source_path: str) -> Dict[str, Dict]:
        """
        Mapeia todos os arquivos no diretório fonte
        Retorna um dicionário com informações de cada arquivo
        """
        files_info = {}
        try:
            for root, _, files in os.walk(source_path):
                for file in files:
                    if self._stop_requested:
                        break

                    file_path = os.path.join(root, file)
                    try:
                        stat = os.stat(file_path)
                        files_info[file_path] = {
                            "size": stat.st_size,
                            "mtime": stat.st_mtime,
                        }
                    except OSError as e:
                        self._log_error(
                            f"Error accessing file {file_path}: {str(e)}"
                        )

        except OSError as e:
            self._log_error(f"Error mapping directory {source_path}: {str(e)}")
            raise

        return files_info

    async def _process_files(
        self, job: Job, files_info: Dict[str, Dict]
    ) -> None:
        """Processa os arquivos conforme o tipo de backup"""
        for source_file, info in files_info.items():
            if self._stop_requested:
                break

            try:
                # Determina se o arquivo precisa ser copiado
                needs_copy = await self._needs_copy(job, source_file, info)
                if needs_copy:
                    await self._copy_file(job, source_file, info["size"])

            except Exception as e:
                self._log_error(f"Error processing {source_file}: {str(e)}")
                if job.stop_on_error:
                    raise

    async def _needs_copy(
        self, job: Job, source_file: str, source_info: Dict
    ) -> bool:
        """Verifica se o arquivo precisa ser copiado baseado no tipo de backup"""
        if job.job_type == JobType.FULL:
            return True

        # Para backup incremental, verifica a data de modificação
        dest_file = self._get_destination_path(
            job.source_path, job.destination_path, source_file
        )

        try:
            if not os.path.exists(dest_file):
                return True

            dest_stat = os.stat(dest_file)
            return source_info["mtime"] > dest_stat.st_mtime

        except OSError:
            # Se houver erro ao acessar o arquivo de destino, copia novamente
            return True

    async def _copy_file(
        self, job: Job, source_file: str, file_size: int
    ) -> None:
        """Copia um arquivo mantendo a estrutura de diretórios"""
        dest_file = self._get_destination_path(
            job.source_path, job.destination_path, source_file
        )

        # Cria os diretórios necessários
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)

        try:
            # Registra início da cópia
            start_time = datetime.now()
            self.current_file = source_file
            await self._update_progress(source_file)

            # Copia o arquivo
            shutil.copy2(source_file, dest_file)

            # Atualiza progresso
            self.processed_files += 1
            self.processed_size += file_size

            # Registra conclusão
            elapsed = (datetime.now() - start_time).total_seconds()
            self._log_info(
                f"Copied {source_file} to {dest_file}",
                file=source_file,
                size=file_size,
                elapsed_time=elapsed,
            )

        except Exception as e:
            self._log_error(
                f"Error copying {source_file}: {str(e)}", file=source_file
            )
            raise

    def _get_destination_path(
        self, source_root: str, dest_root: str, file_path: str
    ) -> str:
        """Calcula o caminho de destino mantendo a estrutura de diretórios"""
        rel_path = os.path.relpath(file_path, source_root)
        return os.path.join(dest_root, rel_path)

    async def _update_progress(
        self, current_file: Optional[str] = None
    ) -> None:
        """Atualiza o progresso na execução"""
        execution = await self._get_execution()
        execution.update_progress(
            processed_files=self.processed_files,
            processed_size=self.processed_size,
            current_file=current_file,
        )
        await self.session.commit()

    async def _handle_error(self, error_message: str) -> None:
        """Trata erro na execução"""
        execution = await self._get_execution()
        execution.fail(error_message)
        await self.session.commit()

    def _log_info(
        self,
        message: str,
        file: Optional[str] = None,
        size: Optional[int] = None,
        elapsed_time: Optional[float] = None,
    ) -> None:
        """Registra uma mensagem de log"""
        entry = ExecutionLogEntry(
            timestamp=datetime.utcnow(),
            level="INFO",
            message=message,
            file=file,
            size=size,
            elapsed_time=elapsed_time,
        )
        self.logger.info(entry.to_csv().strip())

    def _log_error(self, message: str, file: Optional[str] = None) -> None:
        """Registra um erro no log"""
        entry = ExecutionLogEntry(
            timestamp=datetime.utcnow(),
            level="ERROR",
            message=message,
            file=file,
        )
        self.logger.error(entry.to_csv().strip())


# Exemplo de uso:
"""
async def execute_backup(job_id: UUID, execution_id: UUID):
    async with AsyncSession() as session:
        runner = BackupRunner(session, job_id, execution_id)
        await runner.run()

# Em outro contexto, para parar o backup:
async def stop_backup(job_id: UUID, execution_id: UUID):
    async with AsyncSession() as session:
        runner = BackupRunner(session, job_id, execution_id)
        await runner.stop()
"""
