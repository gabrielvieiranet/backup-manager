# services/job_manager.py
import logging
import multiprocessing
from datetime import datetime

from models.execution import Execution
from models.job import Job, JobType


class JobManager:
    def __init__(self, db_session):
        self.db_session = db_session
        self.active_processes = {}
        self.logger = logging.getLogger(__name__)

    async def create_job(self, job_data: JobCreate) -> Job:
        job = Job(**job_data.dict())
        self.db_session.add(job)
        await self.db_session.commit()
        return job

    async def get_job(self, job_id: UUID) -> Optional[Job]:
        return await self.db_session.get(Job, job_id)

    async def update_job(
        self, job_id: UUID, job_data: JobUpdate
    ) -> Optional[Job]:
        job = await self.get_job(job_id)
        if not job:
            return None

        for key, value in job_data.dict(exclude_unset=True).items():
            setattr(job, key, value)

        await self.db_session.commit()
        return job

    async def delete_job(self, job_id: UUID) -> bool:
        job = await self.get_job(job_id)
        if not job:
            return False

        await self.db_session.delete(job)
        await self.db_session.commit()
        return True

    async def start_job(self, job_id: UUID) -> Optional[Execution]:
        job = await self.get_job(job_id)
        if not job or job_id in self.active_processes:
            return None

        execution = Execution(
            job_id=job_id, start_time=datetime.utcnow(), status="running"
        )
        self.db_session.add(execution)
        await self.db_session.commit()

        # Inicia o processo de backup em background
        process = multiprocessing.Process(
            target=self._run_backup, args=(job.id, execution.id)
        )
        process.start()
        self.active_processes[job_id] = {
            "process": process,
            "execution_id": execution.id,
        }

        return execution

    async def stop_job(self, job_id: UUID) -> bool:
        if job_id not in self.active_processes:
            return False

        process_info = self.active_processes[job_id]
        process_info["process"].terminate()

        execution = await self.db_session.get(
            Execution, process_info["execution_id"]
        )
        if execution:
            execution.status = "stopped"
            execution.end_time = datetime.utcnow()
            await self.db_session.commit()

        del self.active_processes[job_id]
        return True

    def _run_backup(self, job_id: UUID, execution_id: UUID):
        """
        Processo separado para executar o backup
        """
        try:
            # Configura logging para o processo
            self._setup_process_logging(job_id)

            # Inicializa o worker de backup
            from worker.backup_worker import BackupWorker

            worker = BackupWorker(job_id, execution_id)

            # Executa o backup
            worker.run()

        except Exception as e:
            self.logger.error(
                f"Error in backup process for job {job_id}: {str(e)}"
            )
            # Atualiza o status da execução para failed
            self._update_execution_status(execution_id, "failed", str(e))

    def _setup_process_logging(self, job_id: UUID):
        """
        Configura o logging para o processo de backup
        """
        log_file = f"logs/{job_id}-{datetime.now().strftime('%Y%m%d')}.csv"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(
            logging.Formatter("%(asctime)s,%(levelname)s,%(message)s")
        )

        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


# worker/backup_worker.py
import os
import shutil
from datetime import datetime
from typing import Dict, Tuple


class BackupWorker:
    def __init__(self, job_id: UUID, execution_id: UUID):
        self.job_id = job_id
        self.execution_id = execution_id
        self.db_session = SessionLocal()
        self.logger = logging.getLogger(__name__)

    def run(self):
        try:
            job = self.db_session.get(Job, self.job_id)
            execution = self.db_session.get(Execution, self.execution_id)

            # Mapeia arquivos e calcula tamanho total
            files_info = self._map_files(job.source_path)
            total_files = len(files_info)
            total_size = sum(info["size"] for info in files_info.values())

            # Atualiza informações na execução
            execution.total_files = total_files
            execution.total_size = total_size
            self.db_session.commit()

            # Executa o backup
            processed_files = 0
            processed_size = 0

            for file_path, info in files_info.items():
                if job.job_type == JobType.FULL or self._needs_update(
                    file_path, info
                ):
                    dest_path = self._get_destination_path(
                        job.source_path, job.destination_path, file_path
                    )

                    # Cria diretórios necessários
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    # Copia o arquivo
                    shutil.copy2(file_path, dest_path)

                    processed_files += 1
                    processed_size += info["size"]

                    # Atualiza progresso
                    execution.processed_files = processed_files
                    execution.processed_size = processed_size
                    self.db_session.commit()

            # Finaliza execução
            execution.status = "completed"
            execution.end_time = datetime.utcnow()
            self.db_session.commit()

        except Exception as e:
            self.logger.error(f"Backup failed: {str(e)}")
            execution.status = "failed"
            execution.error_message = str(e)
            execution.end_time = datetime.utcnow()
            self.db_session.commit()
            raise

        finally:
            self.db_session.close()

    def _map_files(self, source_path: str) -> Dict[str, Dict]:
        """
        Mapeia todos os arquivos no diretório fonte
        Retorna um dicionário com informações de cada arquivo
        """
        files_info = {}
        for root, _, files in os.walk(source_path):
            for file in files:
                file_path = os.path.join(root, file)
                stat = os.stat(file_path)
                files_info[file_path] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
        return files_info

    def _needs_update(self, source_file: str, source_info: Dict) -> bool:
        """
        Verifica se o arquivo precisa ser atualizado (para backup incremental)
        """
        dest_file = self._get_destination_path(
            job.source_path, job.destination_path, source_file
        )

        if not os.path.exists(dest_file):
            return True

        dest_stat = os.stat(dest_file)
        return source_info["mtime"] > dest_stat.st_mtime

    def _get_destination_path(
        self, source_root: str, dest_root: str, file_path: str
    ) -> str:
        """
        Calcula o caminho de destino mantendo a estrutura de diretórios
        """
        rel_path = os.path.relpath(file_path, source_root)
        return os.path.join(dest_root, rel_path)
