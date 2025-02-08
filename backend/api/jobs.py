import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from models.execution import Execution
from models.job import Job
from schemas.job import JobCreate, JobType, JobUpdate, ScheduleType
from services.backup_runner import BackupRunner
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class JobManager:
    """
    Gerenciador de jobs de backup
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.active_processes: Dict[UUID, Dict] = {}

    async def create_job(self, job_data: JobCreate, owner_id: UUID) -> Job:
        """
        Cria um novo job de backup
        """
        try:
            # Calcula a próxima execução
            next_run = self._calculate_next_run(
                job_data.schedule_type,
                job_data.schedule_value,
                job_data.schedule_time,
            )

            # Cria o job
            job = Job(**job_data.dict(), owner_id=owner_id, next_run=next_run)

            self.session.add(job)
            await self.session.commit()
            await self.session.refresh(job)

            return job

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating job: {str(e)}")
            raise

    async def get_job(self, job_id: UUID) -> Optional[Job]:
        """
        Obtém um job pelo ID
        """
        try:
            result = await self.session.execute(
                select(Job).where(Job.id == job_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {str(e)}")
            raise

    async def update_job(
        self, job_id: UUID, job_data: JobUpdate
    ) -> Optional[Job]:
        """
        Atualiza um job existente
        """
        try:
            job = await self.get_job(job_id)
            if not job:
                return None

            # Atualiza apenas os campos fornecidos
            update_data = job_data.dict(exclude_unset=True)

            # Se houver mudança no agendamento, recalcula próxima execução
            if any(
                key in update_data
                for key in ["schedule_type", "schedule_value", "schedule_time"]
            ):
                next_run = self._calculate_next_run(
                    job_data.schedule_type or job.schedule_type,
                    job_data.schedule_value or job.schedule_value,
                    job_data.schedule_time or job.schedule_time,
                )
                update_data["next_run"] = next_run

            for key, value in update_data.items():
                setattr(job, key, value)

            await self.session.commit()
            await self.session.refresh(job)

            return job

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating job {job_id}: {str(e)}")
            raise

    async def delete_job(self, job_id: UUID) -> bool:
        """
        Remove um job
        """
        try:
            job = await self.get_job(job_id)
            if not job:
                return False

            await self.session.delete(job)
            await self.session.commit()
            return True

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting job {job_id}: {str(e)}")
            raise

    async def start_job(self, job_id: UUID) -> Optional[Execution]:
        """
        Inicia a execução de um job
        """
        try:
            job = await self.get_job(job_id)
            if not job or job_id in self.active_processes:
                return None

            # Cria o registro de execução
            execution = Execution(
                job_id=job_id, status="running", start_time=datetime.utcnow()
            )
            self.session.add(execution)
            await self.session.commit()
            await self.session.refresh(execution)

            # Inicia o backup em background
            runner = BackupRunner(self.session, job_id, execution.id)
            task = asyncio.create_task(runner.run())

            # Registra o processo ativo
            self.active_processes[job_id] = {
                "task": task,
                "execution_id": execution.id,
            }

            return execution

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error starting job {job_id}: {str(e)}")
            raise

    async def stop_job(self, job_id: UUID) -> bool:
        """
        Para a execução de um job
        """
        try:
            if job_id not in self.active_processes:
                return False

            process_info = self.active_processes[job_id]

            # Cancela a task
            process_info["task"].cancel()

            # Atualiza o status da execução
            execution = await self.session.get(
                Execution, process_info["execution_id"]
            )
            if execution:
                execution.status = "stopped"
                execution.end_time = datetime.utcnow()
                await self.session.commit()

            # Remove dos processos ativos
            del self.active_processes[job_id]

            return True

        except Exception as e:
            logger.error(f"Error stopping job {job_id}: {str(e)}")
            raise

    async def get_job_progress(self, job_id: UUID) -> Optional[Dict]:
        """
        Obtém o progresso atual de um job
        """
        try:
            if job_id not in self.active_processes:
                return None

            execution_id = self.active_processes[job_id]["execution_id"]
            execution = await self.session.get(Execution, execution_id)

            if not execution:
                return None

            return {
                "status": execution.status,
                "start_time": execution.start_time,
                "end_time": execution.end_time,
                "total_files": execution.total_files,
                "processed_files": execution.processed_files,
                "total_size": execution.total_size,
                "processed_size": execution.processed_size,
                "current_file": execution.current_file,
                "progress_percentage": execution.progress_percentage,
                "size_percentage": execution.size_percentage,
            }

        except Exception as e:
            logger.error(f"Error getting job progress {job_id}: {str(e)}")
            raise

    def _calculate_next_run(
        self,
        schedule_type: ScheduleType,
        schedule_value: str,
        schedule_time: str,
    ) -> Optional[datetime]:
        """
        Calcula a próxima execução do job baseado no agendamento
        """
        now = datetime.utcnow()
        time_parts = schedule_time.split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1])

        if schedule_type == ScheduleType.ONCE:
            # Para execução única, usa a data/hora especificada
            return datetime.strptime(
                f"{schedule_value} {schedule_time}", "%Y-%m-%d %H:%M"
            )

        elif schedule_type == ScheduleType.DAILY:
            # Para execução diária, calcula próximo dia válido
            next_run = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)

            # Verifica se o dia da semana está na lista
            days = schedule_value.split(",")
            while next_run.strftime("%A").lower() not in days:
                next_run += timedelta(days=1)

            return next_run

        elif schedule_type == ScheduleType.MONTHLY:
            # Para execução mensal, usa o dia especificado
            day = int(schedule_value)
            next_run = now.replace(
                day=1, hour=hour, minute=minute, second=0, microsecond=0
            )

            # Ajusta para o dia correto do mês
            if day > 28:
                # Limita ao último dia do mês
                while True:
                    try:
                        next_run = next_run.replace(day=day)
                        break
                    except ValueError:
                        day -= 1
            else:
                next_run = next_run.replace(day=day)

            # Se já passou, move para o próximo mês
            if next_run <= now:
                if next_run.month == 12:
                    next_run = next_run.replace(
                        year=next_run.year + 1, month=1
                    )
                else:
                    next_run = next_run.replace(month=next_run.month + 1)

            return next_run

        return None

    async def cleanup_old_executions(self, older_than: datetime) -> None:
        """
        Remove execuções antigas e seus logs
        """
        try:
            # Busca execuções antigas
            result = await self.session.execute(
                select(Execution).where(Execution.start_time <= older_than)
            )
            old_executions = result.scalars().all()

            # Remove cada execução
            for execution in old_executions:
                # Remove os arquivos de log
                if execution.log_file:
                    try:
                        os.remove(execution.log_file)
                    except OSError:
                        pass

                # Remove a execução do banco
                await self.session.delete(execution)

            await self.session.commit()

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error cleaning up old executions: {str(e)}")
            raise


# Exemplo de uso:
"""
async def main():
    async with AsyncSession() as session:
        manager = JobManager(session)
        
        # Criar job
        job_data = JobCreate(
            name="Daily Backup",
            source_path="/data",
            destination_path="/backup",
            job_type=JobType.INCREMENTAL,
            schedule_type=ScheduleType.DAILY,
            schedule_value="monday,wednesday,friday",
            schedule_time="23:00"
        )
        job = await manager.create_job(job_data, owner_id)
        
        # Iniciar job
        execution = await manager.start_job(job.id)
        
        # Monitorar progresso
        while True:
            progress = await manager.get_job_progress(job.id)
            if not progress or progress['status'] in ('completed', 'failed', 'stopped'):
                break
            print(f"Progress: {progress['progress_percentage']}%")
            await asyncio.sleep(1)
"""
