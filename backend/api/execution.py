import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from core.database import get_async_session
from core.security import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.execution import Execution
from models.job import Job
from models.user import User
from schemas.execution import (
    ExecutionLogResponse,
    ExecutionResponse,
    ExecutionStats,
)
from services.job_manager import JobManager
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("/", response_model=List[ExecutionResponse])
async def list_executions(
    job_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Lista as execuções dos jobs com opções de filtro e paginação.
    """
    # Base query
    query = select(Execution).join(Job).where(Job.owner_id == current_user.id)

    # Aplica filtros
    if job_id:
        query = query.where(Execution.job_id == job_id)
    if status:
        query = query.where(Execution.status == status)
    if start_date:
        query = query.where(Execution.start_time >= start_date)
    if end_date:
        query = query.where(Execution.start_time <= end_date)

    # Ordena por data de início decrescente
    query = query.order_by(desc(Execution.start_time))

    # Aplica paginação
    query = query.offset(skip).limit(limit)

    result = await session.execute(query)
    executions = result.scalars().all()

    return executions


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Obtém os detalhes de uma execução específica.
    """
    result = await session.execute(
        select(Execution)
        .join(Job)
        .where(Execution.id == execution_id, Job.owner_id == current_user.id)
    )
    execution = result.scalar_one_or_none()

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found"
        )

    return execution


@router.get("/{execution_id}/log", response_model=ExecutionLogResponse)
async def get_execution_log(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Obtém o log de uma execução específica.
    """
    # Verifica se a execução existe e pertence ao usuário
    result = await session.execute(
        select(Execution)
        .join(Job)
        .where(Execution.id == execution_id, Job.owner_id == current_user.id)
    )
    execution = result.scalar_one_or_none()

    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found"
        )

    # Obtém o log
    job_manager = JobManager(session)
    try:
        log_content = await job_manager.get_execution_log(execution_id)
        return {"content": log_content}
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Log file not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/stats/summary", response_model=ExecutionStats)
async def get_execution_stats(
    days: int = Query(30, ge=1, le=365),
    job_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Obtém estatísticas das execuções de jobs.
    """
    # Define o período de análise
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Base query para o período
    base_query = (
        select(Execution)
        .join(Job)
        .where(
            Job.owner_id == current_user.id,
            Execution.start_time >= start_date,
            Execution.start_time <= end_date,
        )
    )

    if job_id:
        base_query = base_query.where(Execution.job_id == job_id)

    # Obtém todas as execuções do período
    result = await session.execute(base_query)
    executions = result.scalars().all()

    # Calcula as estatísticas
    total_executions = len(executions)
    successful_executions = len(
        [e for e in executions if e.status == "completed"]
    )
    failed_executions = len([e for e in executions if e.status == "failed"])
    total_files_processed = sum(e.processed_files or 0 for e in executions)
    total_size_processed = sum(e.processed_size or 0 for e in executions)

    # Calcula o tempo médio de execução
    execution_times = [
        (e.end_time - e.start_time).total_seconds()
        for e in executions
        if e.end_time and e.start_time
    ]
    avg_execution_time = (
        sum(execution_times) / len(execution_times) if execution_times else 0
    )

    return {
        "period_days": days,
        "total_executions": total_executions,
        "successful_executions": successful_executions,
        "failed_executions": failed_executions,
        "success_rate": (
            (successful_executions / total_executions * 100)
            if total_executions > 0
            else 0
        ),
        "total_files_processed": total_files_processed,
        "total_size_processed": total_size_processed,
        "avg_execution_time": avg_execution_time,
    }


@router.delete("/cleanup", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_old_executions(
    days: int = Query(180, ge=30),  # Mínimo 30 dias, padrão 180 (6 meses)
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Remove execuções e logs antigos.
    Requer privilégios de superusuário.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can perform this operation",
        )

    # Define a data limite
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Remove as execuções antigas
    job_manager = JobManager(session)
    try:
        await job_manager.cleanup_old_executions(cutoff_date)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
