import asyncio
import logging
import time
from datetime import datetime, timedelta
from statistics import mean
from typing import Dict, List, Optional
from uuid import UUID

from models.execution import Execution
from sqlalchemy.ext.asyncio import AsyncSession

from worker.file_utils import FileUtils

logger = logging.getLogger(__name__)


class ProgressTracker:
    """
    Classe para rastrear o progresso de execuções de backup.
    """

    def __init__(self, session: AsyncSession, execution_id: UUID):
        self.session = session
        self.execution_id = execution_id
        self.start_time = datetime.utcnow()
        self._processed_files = 0
        self._processed_size = 0
        self._current_file: Optional[str] = None
        self._speed_samples: List[float] = []  # bytes/segundo
        self._last_update = datetime.utcnow()
        self._is_paused = False

    @property
    def processed_files(self) -> int:
        """Retorna o número de arquivos processados"""
        return self._processed_files

    @property
    def processed_size(self) -> int:
        """Retorna o tamanho processado em bytes"""
        return self._processed_size

    @property
    def current_file(self) -> Optional[str]:
        """Retorna o arquivo atual em processamento"""
        return self._current_file

    @property
    def elapsed_time(self) -> float:
        """Retorna o tempo decorrido em segundos"""
        return (datetime.utcnow() - self.start_time).total_seconds()

    @property
    def average_speed(self) -> float:
        """Retorna a velocidade média em bytes/segundo"""
        if not self._speed_samples:
            return 0.0
        return mean(self._speed_samples[-10:])  # média das últimas 10 amostras

    def pause(self):
        """Pausa o rastreamento"""
        self._is_paused = True

    def resume(self):
        """Retoma o rastreamento"""
        self._is_paused = False
        self._last_update = datetime.utcnow()

    async def update(
        self,
        processed_files: Optional[int] = None,
        processed_size: Optional[int] = None,
        current_file: Optional[str] = None,
    ) -> None:
        """
        Atualiza o progresso da execução.

        Args:
            processed_files: Número de arquivos processados
            processed_size: Tamanho processado em bytes
            current_file: Arquivo atual em processamento
        """
        if self._is_paused:
            return

        try:
            # Atualiza contadores
            if processed_files is not None:
                self._processed_files = processed_files
            if processed_size is not None:
                # Calcula velocidade
                now = datetime.utcnow()
                time_diff = (now - self._last_update).total_seconds()
                if time_diff > 0:
                    size_diff = processed_size - self._processed_size
                    speed = size_diff / time_diff
                    self._speed_samples.append(speed)
                    # Mantém apenas as últimas 10 amostras
                    if len(self._speed_samples) > 10:
                        self._speed_samples.pop(0)

                self._processed_size = processed_size
                self._last_update = now

            if current_file is not None:
                self._current_file = current_file

            # Atualiza no banco de dados
            execution = await self.session.get(Execution, self.execution_id)
            if execution:
                execution.processed_files = self._processed_files
                execution.processed_size = self._processed_size
                execution.current_file = self._current_file
                await self.session.commit()

        except Exception as e:
            logger.error(f"Error updating progress: {str(e)}")

    def estimate_completion(self, total_size: int) -> Optional[datetime]:
        """
        Estima o tempo de conclusão baseado na velocidade média.

        Args:
            total_size: Tamanho total em bytes

        Returns:
            Data/hora estimada de conclusão ou None se não houver dados suficientes
        """
        if not self._speed_samples or self._processed_size == 0:
            return None

        avg_speed = self.average_speed
        if avg_speed <= 0:
            return None

        remaining_size = total_size - self._processed_size
        remaining_seconds = remaining_size / avg_speed

        return datetime.utcnow() + timedelta(seconds=remaining_seconds)

    def get_status(self, total_files: int, total_size: int) -> Dict:
        """
        Retorna o status atual do progresso.

        Args:
            total_files: Número total de arquivos
            total_size: Tamanho total em bytes

        Returns:
            Dicionário com informações de status
        """
        now = datetime.utcnow()
        elapsed_seconds = (now - self.start_time).total_seconds()

        # Calcula percentuais
        files_percent = (
            (self._processed_files / total_files * 100)
            if total_files > 0
            else 0
        )
        size_percent = (
            (self._processed_size / total_size * 100) if total_size > 0 else 0
        )

        # Estima tempo restante
        estimated_completion = self.estimate_completion(total_size)
        if estimated_completion:
            remaining_seconds = (estimated_completion - now).total_seconds()
        else:
            remaining_seconds = None

        return {
            "processed_files": self._processed_files,
            "total_files": total_files,
            "files_percent": round(files_percent, 2),
            "processed_size": self._processed_size,
            "total_size": total_size,
            "size_percent": round(size_percent, 2),
            "current_file": self._current_file,
            "elapsed_time": elapsed_seconds,
            "remaining_time": remaining_seconds,
            "estimated_completion": estimated_completion,
            "average_speed": self.average_speed,
            "formatted_processed_size": FileUtils.format_size(
                self._processed_size
            ),
            "formatted_total_size": FileUtils.format_size(total_size),
            "formatted_speed": f"{FileUtils.format_size(self.average_speed)}/s",
        }

    async def log_progress(self, total_files: int, total_size: int) -> None:
        """
        Registra o progresso atual no log.

        Args:
            total_files: Número total de arquivos
            total_size: Tamanho total em bytes
        """
        status = self.get_status(total_files, total_size)

        logger.info(
            f"Progress: {status['files_percent']}% of files "
            f"({status['processed_files']}/{status['total_files']}), "
            f"{status['size_percent']}% of size "
            f"({status['formatted_processed_size']}/{status['formatted_total_size']}), "
            f"Speed: {status['formatted_speed']}"
        )

        if status["current_file"]:
            logger.debug(f"Processing: {status['current_file']}")


class ProgressMonitor:
    """
    Classe para monitorar múltiplos trackers de progresso.
    """

    def __init__(self):
        self._trackers: Dict[UUID, ProgressTracker] = {}

    def add_tracker(self, execution_id: UUID, tracker: ProgressTracker):
        """Adiciona um tracker ao monitor"""
        self._trackers[execution_id] = tracker

    def remove_tracker(self, execution_id: UUID):
        """Remove um tracker do monitor"""
        self._trackers.pop(execution_id, None)

    def get_tracker(self, execution_id: UUID) -> Optional[ProgressTracker]:
        """Obtém um tracker específico"""
        return self._trackers.get(execution_id)

    def get_all_progress(self) -> Dict[UUID, Dict]:
        """Obtém o progresso de todos os trackers ativos"""
        return {
            execution_id: tracker.get_status()
            for execution_id, tracker in self._trackers.items()
        }


# Exemplo de uso:
"""
async def backup_file(tracker: ProgressTracker, file_path: str, size: int):
    # Simula o backup de um arquivo
    tracker.update(current_file=file_path)
    chunk_size = 8192
    processed = 0
    
    with open(file_path, 'rb') as f:
        while True:
            if not f.read(chunk_size):
                break
            processed += chunk_size
            await tracker.update(processed_size=processed)
            await asyncio.sleep(0.1)  # Simula processamento

async def main():
    async with AsyncSession() as session:
        tracker = ProgressTracker(session, UUID('...'))
        
        # Configura monitoramento
        monitor = ProgressMonitor()
        monitor.add_tracker(execution_id, tracker)
        
        # Processa arquivos
        total_files = 100
        total_size = 1024 * 1024 * 100  # 100 MB
        
        for i in range(total_files):
            await backup_file(tracker, f"file_{i}", 1024 * 1024)
            await tracker.update(processed_files=i+1)
            await tracker.log_progress(total_files, total_size)
            
        # Remove monitoramento
        monitor.remove_tracker(execution_id)
"""
