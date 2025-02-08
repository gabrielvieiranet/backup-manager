from typing import AsyncGenerator, Generator

from core.config import get_settings
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

settings = get_settings()

# Engine síncrona para migrações e scripts de manutenção
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Verifica conexão antes de usar
    pool_size=5,  # Tamanho do pool de conexões
    max_overflow=10,  # Máximo de conexões extras
    echo=False,  # Não exibe queries SQL no console
)

# Engine assíncrona para a aplicação
async_engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

# Sessão síncrona para migrações e scripts
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Sessão assíncrona para a aplicação
AsyncSessionLocal = async_sessionmaker(
    async_engine, autocommit=False, autoflush=False, expire_on_commit=False
)

# Classe base para os modelos
Base = declarative_base()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency para obter uma sessão assíncrona do banco de dados.
    Uso:
        @app.get("/items/")
        async def read_items(session: AsyncSession = Depends(get_async_session)):
            result = await session.execute(select(Item))
            items = result.scalars().all()
            return items
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_session() -> Generator[Session, None, None]:
    """
    Dependency para obter uma sessão síncrona do banco de dados.
    Usado principalmente em scripts e testes.
    Uso:
        @app.get("/items/")
        def read_items(session: Session = Depends(get_session)):
            items = session.query(Item).all()
            return items
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db() -> None:
    """
    Inicializa o banco de dados criando todas as tabelas.
    Deve ser chamado na inicialização da aplicação.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Fecha todas as conexões com o banco de dados.
    Deve ser chamado no shutdown da aplicação.
    """
    await async_engine.dispose()


# Função auxiliar para testes
def init_test_db():
    """
    Inicializa o banco de dados para testes.
    Cria todas as tabelas e retorna uma sessão de teste.
    """
    Base.metadata.create_all(bind=engine)
    return SessionLocal()
