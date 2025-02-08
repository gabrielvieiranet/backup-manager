import uuid
from datetime import datetime

from core.database import Base
from core.security import get_password_hash, verify_password
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

# Tabela de associação para grupos de usuários (caso queira implementar mais tarde)
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id")),
    Column("group_id", UUID(as_uuid=True), ForeignKey("groups.id")),
)


class User(Base):
    """
    Modelo de usuário do sistema
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_login = Column(DateTime, nullable=True)

    # Relacionamentos (caso queira implementar mais tarde)
    jobs = relationship("Job", back_populates="owner")
    groups = relationship(
        "Group", secondary=user_groups, back_populates="users"
    )

    def __init__(self, **kwargs):
        """
        Inicializa um novo usuário.
        Se a senha for fornecida, faz o hash antes de salvar.
        """
        if "password" in kwargs:
            kwargs["hashed_password"] = get_password_hash(
                kwargs.pop("password")
            )
        super().__init__(**kwargs)

    def verify_password(self, password: str) -> bool:
        """
        Verifica se a senha fornecida corresponde ao hash armazenado
        """
        return verify_password(password, self.hashed_password)

    def update_password(self, new_password: str) -> None:
        """
        Atualiza a senha do usuário
        """
        self.hashed_password = get_password_hash(new_password)
        self.updated_at = datetime.utcnow()

    def update_last_login(self) -> None:
        """
        Atualiza o timestamp do último login
        """
        self.last_login = datetime.utcnow()

    def to_dict(self) -> dict:
        """
        Converte o usuário em um dicionário, excluindo dados sensíveis
        """
        return {
            "id": str(self.id),
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
            "last_login": (
                self.last_login.isoformat() if self.last_login else None
            ),
        }

    def __repr__(self) -> str:
        """
        Representação em string do usuário
        """
        return f"<User {self.username}>"


# Opcional: Modelo de Grupo (caso queira implementar mais tarde)
class Group(Base):
    """
    Modelo de grupo de usuários
    """

    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relacionamentos
    users = relationship(
        "User", secondary=user_groups, back_populates="groups"
    )

    def __repr__(self) -> str:
        return f"<Group {self.name}>"


# Exemplo de uso:
"""
# Criar um novo usuário
new_user = User(
    username="john_doe",
    email="john@example.com",
    full_name="John Doe",
    password="secure_password123"  # Será convertido automaticamente em hash
)

# Verificar senha
is_valid = new_user.verify_password("secure_password123")

# Atualizar senha
new_user.update_password("new_secure_password456")

# Registrar login
new_user.update_last_login()

# Converter para dicionário
user_dict = new_user.to_dict()
"""
