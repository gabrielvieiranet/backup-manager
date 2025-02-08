import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from api import api_router
from core.config import get_settings
from core.database import close_db, init_db
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configurações
settings = get_settings()

# Configuração de logs
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT,
    handlers=[logging.StreamHandler(), logging.FileHandler("api.log")],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Contexto de ciclo de vida da aplicação
    """
    # Startup
    logger.info("Starting application...")
    await init_db()
    settings.create_directories()
    logger.info("Application started successfully")

    yield  # A aplicação está rodando

    # Shutdown
    logger.info("Shutting down application...")
    await close_db()
    logger.info("Application shutdown complete")


# Criação da aplicação FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Sistema de Backup com interface web",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Roteadores
app.include_router(api_router, prefix=settings.API_V1_STR)


# Middleware para logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware para logging de requisições
    """
    start_time = datetime.now(timezone.utc)
    response = await call_next(request)
    end_time = datetime.now(timezone.utc)

    # Calcula tempo de resposta
    duration = (end_time - start_time).total_seconds() * 1000

    # Log da requisição
    logger.info(
        f"Method: {request.method} "
        f"Path: {request.url.path} "
        f"Status: {response.status_code} "
        f"Duration: {duration:.2f}ms"
    )

    return response


# Handlers de erro customizados
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """
    Handler customizado para erros de validação
    """
    return JSONResponse(
        status_code=422, content={"detail": exc.errors(), "body": exc.body}
    )


# Rotas de health check
@app.get("/health")
async def health_check():
    """
    Rota de verificação de saúde da aplicação
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc),
        "version": settings.VERSION,
    }


@app.get("/")
async def root():
    """
    Rota raiz da aplicação
    """
    return {
        "message": "Welcome to Backup System API",
        "docs": "/docs",
        "version": settings.VERSION,
    }


# Execução em desenvolvimento
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        workers=1,
    )
