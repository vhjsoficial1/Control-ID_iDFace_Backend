"""
Rotas de Autenticação e Gerenciamento de Admins
"""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.database import get_db
from pydantic import BaseModel
from datetime import datetime, timedelta
import hashlib
import secrets
# import jwt
from jose import jwt

router = APIRouter()
security = HTTPBearer()

# Configuração JWT
SECRET_KEY = "your-secret-key-change-in-production"  # Usar settings.API_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas


# ==================== Schemas ====================

class AdminCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"  # admin, operator, viewer


class AdminLogin(BaseModel):
    username: str
    password: str


class AdminResponse(BaseModel):
    id: int
    username: str
    role: str
    active: bool
    lastLogin: datetime | None
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin: AdminResponse


# ==================== Helper Functions ====================

def hash_password(password: str, salt: str) -> str:
    """Hash de senha com salt"""
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def create_access_token(data: dict) -> str:
    """Cria token JWT"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """Verifica e decodifica token JWT"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db = Depends(get_db)
):
    """Dependency para obter admin autenticado"""
    token = credentials.credentials
    payload = verify_token(token)
    
    admin_id = payload.get("admin_id")
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
    
    admin = await db.admin.find_unique(where={"id": admin_id})
    if not admin or not admin.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin não encontrado ou inativo"
        )
    
    return admin


# ==================== Rotas ====================

@router.post("/register", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def register_admin(admin_data: AdminCreate, db = Depends(get_db)):
    """
    Registra novo admin (apenas para primeiro setup ou por outro admin)
    """
    # Verificar se username já existe
    existing = await db.admin.find_first(where={"username": admin_data.username})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username já existe"
        )
    
    # Validar role
    valid_roles = ["admin", "operator", "viewer"]
    if admin_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role inválida. Use: {', '.join(valid_roles)}"
        )
    
    # Criar admin
    salt = secrets.token_hex(16)
    hashed_password = hash_password(admin_data.password, salt)
    
    admin = await db.admin.create(
        data={
            "username": admin_data.username,
            "password": hashed_password,
            "salt": salt,
            "role": admin_data.role
        }
    )
    
    # Auditar
    await db.auditlog.create(
        data={
            "adminId": admin.id,
            "action": "admin_created",
            "entity": "admin",
            "entityId": admin.id,
            "details": f"Admin '{admin.username}' criado com role '{admin.role}'"
        }
    )
    
    return admin


@router.post("/login", response_model=TokenResponse)
async def login(credentials: AdminLogin, db = Depends(get_db)):
    """
    Login de admin - retorna token JWT
    """
    # Buscar admin
    admin = await db.admin.find_first(where={"username": credentials.username})
    
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas"
        )
    
    # Verificar senha
    hashed_input = hash_password(credentials.password, admin.salt)
    
    if hashed_input != admin.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas"
        )
    
    # Verificar se está ativo
    if not admin.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin inativo"
        )
    
    # Atualizar último login
    await db.admin.update(
        where={"id": admin.id},
        data={"lastLogin": datetime.now()}
    )
    
    # Criar token
    token = create_access_token({
        "admin_id": admin.id,
        "username": admin.username,
        "role": admin.role
    })
    
    # Auditar
    await db.auditlog.create(
        data={
            "adminId": admin.id,
            "action": "login_success",
            "entity": "admin",
            "entityId": admin.id,
            "details": f"Admin '{admin.username}' fez login"
        }
    )
    
    return TokenResponse(
        access_token=token,
        admin=admin
    )


@router.get("/me", response_model=AdminResponse)
async def get_current_admin_info(admin = Depends(get_current_admin)):
    """
    Retorna informações do admin autenticado
    """
    return admin


@router.post("/logout")
async def logout(admin = Depends(get_current_admin), db = Depends(get_db)):
    """
    Logout (apenas registra no audit, token expira sozinho)
    """
    await db.auditlog.create(
        data={
            "adminId": admin.id,
            "action": "logout",
            "entity": "admin",
            "entityId": admin.id,
            "details": f"Admin '{admin.username}' fez logout"
        }
    )
    
    return {"message": "Logout realizado com sucesso"}


@router.get("/admins", response_model=list[AdminResponse])
async def list_admins(
    admin = Depends(get_current_admin),
    db = Depends(get_db)
):
    """
    Lista todos os admins (apenas para role 'admin')
    """
    if admin.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas admins podem listar outros admins"
        )
    
    admins = await db.admin.find_many(order_by={"username": "asc"})
    return admins


@router.patch("/admins/{admin_id}/toggle-active")
async def toggle_admin_active(
    admin_id: int,
    admin = Depends(get_current_admin),
    db = Depends(get_db)
):
    """
    Ativa/desativa um admin
    """
    if admin.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas admins podem modificar outros admins"
        )
    
    target_admin = await db.admin.find_unique(where={"id": admin_id})
    if not target_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin não encontrado"
        )
    
    # Não pode desativar a si mesmo
    if admin_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível desativar sua própria conta"
        )
    
    # Toggle
    updated = await db.admin.update(
        where={"id": admin_id},
        data={"active": not target_admin.active}
    )
    
    # Auditar
    await db.auditlog.create(
        data={
            "adminId": admin.id,
            "action": "admin_toggled",
            "entity": "admin",
            "entityId": admin_id,
            "details": f"Admin '{target_admin.username}' {'ativado' if updated.active else 'desativado'}"
        }
    )
    
    return {
        "success": True,
        "admin": updated,
        "message": f"Admin {'ativado' if updated.active else 'desativado'} com sucesso"
    }