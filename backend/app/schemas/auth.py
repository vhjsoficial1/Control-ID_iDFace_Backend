"""
Schemas para Autenticação de Admins
backend/app/schemas/auth.py
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AdminCadastro(BaseModel):
    """Schema para cadastro de novo admin"""
    username: str = Field(..., min_length=3, max_length=50, description="Nome de usuário único")
    password: str = Field(..., min_length=6, description="Senha (mínimo 6 caracteres)")


class AdminLogin(BaseModel):
    """Schema para login de admin"""
    username: str = Field(..., description="Nome de usuário")
    password: str = Field(..., description="Senha")


class AdminResponse(BaseModel):
    """Schema de resposta com dados do admin
    
    **Atributo isMaster:**
    - True: Admin master com acesso a todas as funcionalidades (Cadastros, Horários, Regras, Abrir Porta, Backup)
    - False: Admin comum (visitante) com acesso limitado (apenas Cadastro de Visitante)
    """
    id: int
    username: str
    active: bool
    isMaster: bool
    createdAt: datetime
    lastLogin: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Schema de resposta após login bem-sucedido"""
    success: bool
    message: str
    admin: AdminResponse


class LogoutResponse(BaseModel):
    """Schema de resposta após logout"""
    success: bool
    message: str