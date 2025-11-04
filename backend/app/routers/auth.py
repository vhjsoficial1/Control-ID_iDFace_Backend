"""
Rotas de Autenticação - Login e Cadastro de Admins
backend/app/routers/auth.py
"""
from fastapi import APIRouter, HTTPException, Depends, status, Response
from app.database import get_db
from app.schemas.auth import (
    AdminCadastro, AdminLogin, AdminResponse,
    LoginResponse, LogoutResponse
)
from datetime import datetime
import hashlib
import secrets

router = APIRouter()


# ==================== Helper Functions ====================

def hash_password(password: str, salt: str) -> str:
    """
    Cria hash SHA256 da senha com salt
    """
    combined = f"{password}{salt}"
    return hashlib.sha256(combined.encode()).hexdigest()


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """
    Verifica se a senha está correta
    """
    check_hash = hash_password(password, salt)
    return check_hash == hashed


# ==================== CADASTRO ====================

@router.post("/cadastro", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def cadastro_admin(admin_data: AdminCadastro, db = Depends(get_db)):
    """
    Cadastra novo administrador no sistema
    
    **Validações:**
    - Username único (não pode existir outro admin com mesmo nome)
    - Mínimo 3 caracteres para username
    - Mínimo 6 caracteres para senha
    
    **Retorna:**
    - Dados do admin criado (sem a senha)
    """
    # Validar se username já existe
    existing = await db.admin.find_first(
        where={"username": admin_data.username}
    )
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Já existe um admin com o username '{admin_data.username}'"
        )
    
    # Gerar salt aleatório
    salt = secrets.token_hex(16)
    
    # Hash da senha
    hashed_password = hash_password(admin_data.password, salt)
    
    try:
        # Criar admin no banco
        new_admin = await db.admin.create(
            data={
                "username": admin_data.username,
                "password": hashed_password,
                "salt": salt,
                "active": True
            }
        )
        
        print(f"✅ Admin cadastrado: {new_admin.username} (ID: {new_admin.id})")
        
        return new_admin
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao cadastrar admin: {str(e)}"
        )


# ==================== LOGIN ====================

@router.post("/login", response_model=LoginResponse)
async def login_admin(credentials: AdminLogin, response: Response, db = Depends(get_db)):
    """
    Realiza login de administrador
    
    **Fluxo:**
    1. Busca admin por username
    2. Verifica se admin existe e está ativo
    3. Compara senha fornecida com hash armazenado
    4. Atualiza data de último login
    5. Retorna dados do admin
    
    **Retorna:**
    - success: True se login bem-sucedido
    - message: Mensagem de sucesso
    - admin: Dados do administrador
    """
    # Buscar admin por username
    admin = await db.admin.find_first(
        where={"username": credentials.username}
    )
    
    # Verificar se admin existe
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos"
        )
    
    # Verificar se admin está ativo
    if not admin.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada. Entre em contato com o administrador."
        )
    
    # Verificar senha
    if not verify_password(credentials.password, admin.password, admin.salt):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos"
        )
    
    # Atualizar último login
    try:
        admin = await db.admin.update(
            where={"id": admin.id},
            data={"lastLogin": datetime.now()}
        )
    except Exception as e:
        print(f"⚠️  Erro ao atualizar lastLogin: {e}")
    
    print(f"✅ Login bem-sucedido: {admin.username}")
    
    # Criar cookie de sessão simples (opcional)
    response.set_cookie(
        key="admin_id",
        value=str(admin.id),
        httponly=True,
        max_age=28800,  # 8 horas
        samesite="lax"
    )
    
    return LoginResponse(
        success=True,
        message=f"Bem-vindo, {admin.username}!",
        admin=admin
    )


# ==================== LOGOUT ====================

@router.post("/logout", response_model=LogoutResponse)
async def logout_admin(response: Response):
    """
    Realiza logout (remove cookie de sessão)
    """
    response.delete_cookie(key="admin_id")
    
    return LogoutResponse(
        success=True,
        message="Logout realizado com sucesso"
    )


# ==================== VERIFICAR SESSÃO ====================

@router.get("/verificar")
async def verificar_sessao(admin_id: int, db = Depends(get_db)):
    """
    Verifica se uma sessão é válida
    
    **Uso:**
    - Frontend pode chamar para verificar se admin ainda está logado
    - Passar admin_id obtido do cookie ou storage
    
    **Query Parameters:**
    - admin_id: ID do admin a verificar
    """
    admin = await db.admin.find_unique(
        where={"id": admin_id}
    )
    
    if not admin or not admin.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada"
        )
    
    return {
        "valid": True,
        "admin": AdminResponse.model_validate(admin)
    }


# ==================== LISTAR ADMINS (Protegido) ====================

@router.get("/admins", response_model=list[AdminResponse])
async def listar_admins(db = Depends(get_db)):
    """
    Lista todos os administradores cadastrados
    
    **Nota:** Em produção, esta rota deveria ser protegida
    e acessível apenas por admin master
    """
    admins = await db.admin.find_many(
        order_by={"username": "asc"}
    )
    
    return admins


# ==================== DESATIVAR ADMIN ====================

@router.patch("/admins/{admin_id}/desativar")
async def desativar_admin(admin_id: int, db = Depends(get_db)):
    """
    Desativa um administrador (não deleta, apenas inativa)
    
    **Uso:**
    - Para remover acesso sem perder histórico
    - Admin pode ser reativado depois
    """
    admin = await db.admin.find_unique(where={"id": admin_id})
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin não encontrado"
        )
    
    # Toggle active status
    updated = await db.admin.update(
        where={"id": admin_id},
        data={"active": not admin.active}
    )
    
    status_text = "ativado" if updated.active else "desativado"
    
    return {
        "success": True,
        "message": f"Admin '{updated.username}' foi {status_text}",
        "admin": updated
    }


# ==================== ALTERAR SENHA ====================

@router.post("/alterar-senha")
async def alterar_senha(
    admin_id: int,
    senha_atual: str,
    senha_nova: str,
    db = Depends(get_db)
):
    """
    Altera a senha de um administrador
    
    **Validações:**
    - Senha atual deve estar correta
    - Senha nova deve ter mínimo 6 caracteres
    """
    # Buscar admin
    admin = await db.admin.find_unique(where={"id": admin_id})
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin não encontrado"
        )
    
    # Verificar senha atual
    if not verify_password(senha_atual, admin.password, admin.salt):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha atual incorreta"
        )
    
    # Validar senha nova
    if len(senha_nova) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha nova deve ter no mínimo 6 caracteres"
        )
    
    # Gerar novo salt e hash
    new_salt = secrets.token_hex(16)
    new_hashed = hash_password(senha_nova, new_salt)
    
    # Atualizar no banco
    await db.admin.update(
        where={"id": admin_id},
        data={
            "password": new_hashed,
            "salt": new_salt
        }
    )
    
    print(f"✅ Senha alterada: {admin.username}")
    
    return {
        "success": True,
        "message": "Senha alterada com sucesso"
    }