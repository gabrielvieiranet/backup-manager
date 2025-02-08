from datetime import datetime, timedelta
from typing import Optional, Union

from core.config import get_settings
from core.database import get_async_session
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from models.user import User
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

settings = get_settings()

# Configuração do contexto de senha
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configuração do OAuth2
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica se a senha em texto plano corresponde ao hash.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Gera o hash de uma senha.
    """
    return pwd_context.hash(password)


def create_access_token(
    subject: Union[str, int], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Cria um token JWT.

    Args:
        subject: Identificador do usuário (normalmente username ou ID)
        expires_delta: Tempo de expiração opcional

    Returns:
        Token JWT codificado
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    return encoded_jwt


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """
    Dependency para obter o usuário atual a partir do token JWT.

    Args:
        token: Token JWT de autenticação
        session: Sessão do banco de dados

    Returns:
        Usuário autenticado

    Raises:
        HTTPException: Se o token for inválido ou o usuário não for encontrado
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decodifica o token
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Busca o usuário no banco
    result = await session.execute(
        select(User).where(User.username == username)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    return user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency para verificar se o usuário atual é um superusuário ativo.

    Args:
        current_user: Usuário atual obtido via get_current_user

    Returns:
        Usuário superusuário

    Raises:
        HTTPException: Se o usuário não for um superusuário
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_user


class SecurityUtils:
    """Classe utilitária com métodos adicionais de segurança"""

    @staticmethod
    def is_strong_password(password: str) -> bool:
        """
        Verifica se uma senha é forte o suficiente.
        Requer:
        - Mínimo 8 caracteres
        - Pelo menos 1 letra maiúscula
        - Pelo menos 1 letra minúscula
        - Pelo menos 1 número
        - Pelo menos 1 caractere especial
        """
        import re

        if len(password) < 8:
            return False
        if not re.search(r"[A-Z]", password):
            return False
        if not re.search(r"[a-z]", password):
            return False
        if not re.search(r"\d", password):
            return False
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False
        return True

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitiza um nome de arquivo para evitar path traversal.
        """
        import re
        from pathlib import Path

        # Remove caracteres não seguros
        filename = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)

        # Garante que não há tentativa de path traversal
        return Path(filename).name

    @staticmethod
    def validate_path(path: str) -> bool:
        """
        Valida se um caminho é seguro para acesso.
        Previne path traversal e acesso a diretórios sensíveis.
        """
        from pathlib import Path

        # Normaliza o caminho
        path = Path(path).resolve()

        # Lista de diretórios proibidos
        forbidden_paths = [
            "/etc",
            "/var",
            "/root",
            "/usr",
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
        ]

        # Verifica se o caminho não está em uma área proibida
        return not any(
            str(path).startswith(forbidden) for forbidden in forbidden_paths
        )


# Exemplo de uso:
"""
# Hash de senha
password = "user123"
hashed = get_password_hash(password)
is_valid = verify_password(password, hashed)

# Geração de token
token = create_access_token(subject="user@example.com")

# Uso em rotas FastAPI
@router.get("/users/me")
async def read_users_me(
    current_user: User = Depends(get_current_user)
):
    return current_user

@router.post("/admin/users")
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_active_superuser)
):
    ...

# Validação de senha forte
is_strong = SecurityUtils.is_strong_password("User123!@#")

# Sanitização de arquivo
safe_filename = SecurityUtils.sanitize_filename("../../../etc/passwd")

# Validação de caminho
is_safe = SecurityUtils.validate_path("/var/www/files")
"""
