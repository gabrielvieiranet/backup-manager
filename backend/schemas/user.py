from datetime import datetime
from typing import Optional

from pydantic import UUID4, BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Schema base com os campos comuns a todos os schemas de usuário"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(..., min_length=3, max_length=100)
    is_active: bool = True


class UserCreate(UserBase):
    """Schema para criação de usuário"""

    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)

    def validate_passwords_match(self):
        """Valida se as senhas conferem"""
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return True


class UserUpdate(BaseModel):
    """Schema para atualização de usuário"""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=3, max_length=100)
    is_active: Optional[bool] = None


class UserUpdatePassword(BaseModel):
    """Schema para atualização de senha"""

    current_password: str = Field(..., min_length=8, max_length=100)
    new_password: str = Field(..., min_length=8, max_length=100)
    confirm_new_password: str = Field(..., min_length=8, max_length=100)

    def validate_passwords_match(self):
        """Valida se as senhas conferem"""
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match")
        return True


class UserInDBBase(UserBase):
    """Schema base para usuário no banco de dados"""

    id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserResponse(UserInDBBase):
    """Schema para resposta da API"""

    pass


class UserInDB(UserInDBBase):
    """Schema completo do usuário no banco de dados, incluindo a senha hasheada"""

    hashed_password: str

    class Config:
        from_attributes = True
        exclude = {
            "hashed_password"
        }  # Não expõe a senha hasheada nas respostas


# Exemplos de uso:
"""
# Criar usuário
user_data = {
    "username": "johndoe",
    "email": "john@example.com",
    "full_name": "John Doe",
    "password": "secretpass123",
    "confirm_password": "secretpass123"
}
user = UserCreate(**user_data)
user.validate_passwords_match()

# Atualizar usuário
update_data = {
    "full_name": "John M. Doe",
    "email": "john.doe@example.com"
}
update = UserUpdate(**update_data)

# Atualizar senha
password_update = UserUpdatePassword(
    current_password="oldpass123",
    new_password="newpass123",
    confirm_new_password="newpass123"
)
password_update.validate_passwords_match()
"""
