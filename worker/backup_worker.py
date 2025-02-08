import asyncio
import logging
import multiprocessing
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from uuid import UUID

from core.config import get_settings
from models.execution import Execution
from models.job import Job
from services.backup_runner import BackupRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

settings = get_settings()

# Configuração do logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("backup_worker.log"),
    ],
)
logger = logging.getLogger(__name__)


class BackupWorker:
    """
    Worker para gerenciar execuções de backup em background.
    """

    def __init__(self):
        self.active_processes: Dict[UUID, multiprocessing.Process] = {}
        self.stop_event = asyncio.Event()
        self.engine = create_async_engine(settings.DATABASE_URL)
        self.SessionLocal = sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

        # Configura handlers para sinais
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handler para sinais de término"""
        logger.info(
            f"Received signal {signum}. Initiating graceful shutdown..."
        )
        asyncio.create_task(self.shutdown())

    async def start(self):
        """Inicia o worker"""
        logger.info("Starting backup worker...")

        try:
            # Inicia o loop principal
            while not self.stop_event.is_set():
                try:
                    await self._process_pending_jobs()
                    await self._cleanup_stuck_executions()
                    await asyncio.sleep(10)  # Intervalo entre verificações
                except Exception as e:
                    logger.error(f"Error in main loop: {str(e)}")
                    await asyncio.sleep(
                        30
                    )  # Espera mais tempo em caso de erro

        except Exception as e:
            logger.error(f"Critical error in worker: {str(e)}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Realiza o desligamento controlado do worker"""
        logger.info("Shutting down backup worker...")
        self.stop_event.set()

        # Para todos os processos ativos
        for job_id, process in self.active_processes.items():
            logger.info(f"Stopping process for job {job_id}")
            process.terminate()
            process.join(timeout=30)

        # Fecha conexões com o banco
        await self.engine.dispose()
        logger.info("Backup worker shutdown complete")

    async def _process_pending_jobs(self):
        """Processa jobs pendentes de execução"""
        async with self.SessionLocal() as session:
            # Busca jobs que devem ser executados
            now = datetime.utcnow()
            query = (
                select(Job)
                .where(Job.is_active == True, Job.next_run <= now)
                .order_by(Job.next_run)
            )

            result = await session.execute(query)
            pending_jobs = result.scalars().all()

            for job in pending_jobs:
                if len(self.active_processes) >= settings.MAX_CONCURRENT_JOBS:
                    break

                if job.id not in self.active_processes:
                    await self._start_job(session, job)

    async def _start_job(self, session: AsyncSession, job: Job):
        """Inicia a execução de um job"""
        try:
            # Cria o registro de execução
            execution = Execution(
                job_id=job.id, status="running", start_time=datetime.utcnow()
            )
            session.add(execution)
            await session.commit()

            # Inicia o processo
            process = multiprocessing.Process(
                target=self._run_backup, args=(str(job.id), str(execution.id))
            )
            process.start()

            # Registra o processo ativo
            self.active_processes[job.id] = {
                "process": process,
                "execution_id": execution.id,
                "start_time": datetime.utcnow(),
            }

            logger.info(f"Started backup process for job {job.id}")

            # Atualiza próxima execução do job
            job.last_run = datetime.utcnow()
            job.next_run = self._calculate_next_run(job)
            await session.commit()

        except Exception as e:
            logger.error(f"Error starting job {job.id}: {str(e)}")
            if execution:
                execution.status = "failed"
                execution.error_message = str(e)
                execution.end_time = datetime.utcnow()
                await session.commit()

    def _run_backup(self, job_id: str, execution_id: str):
        """Função executada no processo filho para realizar o backup"""
        try:
            asyncio.run(
                self._async_run_backup(UUID(job_id), UUID(execution_id))
            )
        except Exception as e:
            logger.error(f"Error in backup process {job_id}: {str(e)}")
            sys.exit(1)

    async def _async_run_backup(self, job_id: UUID, execution_id: UUID):
        """Executa o backup de forma assíncrona"""
        async with self.SessionLocal() as session:
            runner = BackupRunner(session, job_id, execution_id)
            await runner.run()

    async def _cleanup_stuck_executions(self):
        """Limpa execuções travadas"""
        async with self.SessionLocal() as session:
            # Define o limite de tempo para considerar uma execução travada
            stuck_threshold = datetime.utcnow() - timedelta(
                seconds=settings.WORKER_PROCESS_TIMEOUT
            )

            # Busca execuções potencialmente travadas
            query = select(Execution).where(
                Execution.status == "running",
                Execution.start_time <= stuck_threshold,
            )

            result = await session.execute(query)
            stuck_executions = result.scalars().all()

            for execution in stuck_executions:
                # Verifica se o processo ainda está ativo
                process_info = self.active_processes.get(execution.job_id)

                if not process_info or not process_info["process"].is_alive():
                    logger.warning(f"Found stuck execution {execution.id}")

                    # Marca como falha
                    execution.status = "failed"
                    execution.end_time = datetime.utcnow()
                    execution.error_message = "Execution timed out"

                    # Remove do controle de processos
                    if execution.job_id in self.active_processes:
                        del self.active_processes[execution.job_id]

            await session.commit()

    def _calculate_next_run(self, job: Job) -> Optional[datetime]:
        """Calcula a próxima execução do job baseado no agendamento"""
        if not job.schedule_type:
            return None

        now = datetime.utcnow()

        if job.schedule_type == "once":
            return None
        elif job.schedule_type == "daily":
            next_run = now + timedelta(days=1)
            return next_run.replace(
                hour=job.schedule_time.hour,
                minute=job.schedule_time.minute,
                second=0,
                microsecond=0,
            )
        elif job.schedule_type == "monthly":
            if now.month == 12:
                next_run = now.replace(year=now.year + 1, month=1)
            else:
                next_run = now.replace(month=now.month + 1)

            return next_run.replace(
                day=min(job.schedule_day, 28),
                hour=job.schedule_time.hour,
                minute=job.schedule_time.minute,
                second=0,
                microsecond=0,
            )


# Função principal para execução do worker
async def run_worker():
    """Função principal para executar o worker"""
    worker = BackupWorker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(run_worker())
