"""
Rotas da API para Backup e Restore
"""
from fastapi import APIRouter, HTTPException, Depends, status, Response
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.services.backup_service import BackupService
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import io
import base64

router = APIRouter()


# ==================== Schemas ====================

class BackupCreateRequest(BaseModel):
    """Requisição para criar backup"""
    include_images: bool = Field(False, description="Incluir imagens faciais")
    include_logs: bool = Field(True, description="Incluir logs de acesso")
    compress: bool = Field(True, description="Compactar em ZIP")


class BackupRestoreRequest(BaseModel):
    """Requisição para restaurar backup"""
    backup_data: str = Field(..., description="Dados do backup em base64")
    clear_before: bool = Field(False, description="Limpar banco antes")
    skip_existing: bool = Field(True, description="Pular registros existentes")
    restore_logs: bool = Field(False, description="Restaurar logs de acesso")


class BackupMetadata(BaseModel):
    """Metadados de um backup"""
    backup_date: str
    version: str
    system: str
    include_images: bool
    include_logs: bool
    size_bytes: int
    size_mb: float
    duration_seconds: float


class BackupResponse(BaseModel):
    """Resposta de criação de backup"""
    success: bool
    format: str
    metadata: BackupMetadata
    download_ready: bool = True
    message: Optional[str] = None


class RestoreResponse(BaseModel):
    """Resposta de restauração"""
    success: bool
    message: str
    duration_seconds: float
    statistics: dict


# ==================== Endpoints ====================

@router.post("/create", response_model=BackupResponse)
async def create_backup(
    request: BackupCreateRequest,
    db = Depends(get_db)
):
    """
    Cria um backup completo do banco de dados
    
    - **include_images**: Incluir imagens faciais (aumenta muito o tamanho)
    - **include_logs**: Incluir logs de acesso históricos
    - **compress**: Compactar resultado em ZIP
    
    Retorna metadados do backup. Use /backup/download para baixar.
    """
    backup_service = BackupService(db)
    
    result = await backup_service.create_full_backup(
        include_images=request.include_images,
        include_logs=request.include_logs,
        compress=request.compress
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Erro ao criar backup")
        )
    
    # Armazenar backup temporariamente (em produção, salvar em S3/storage)
    # Por enquanto, retornar base64 na resposta
    backup_content = result["backup_data"]
    
    if isinstance(backup_content, bytes):
        backup_b64 = base64.b64encode(backup_content).decode('utf-8')
    else:
        backup_b64 = base64.b64encode(backup_content.encode('utf-8')).decode('utf-8')
    
    # Salvar em "cache" temporário (em produção, usar Redis ou S3)
    # Aqui apenas para demonstração
    global _last_backup
    _last_backup = {
        "content": backup_b64,
        "format": result["format"],
        "metadata": result["metadata"],
        "created_at": datetime.now()
    }
    
    return BackupResponse(
        success=True,
        format=result["format"],
        metadata=BackupMetadata(**result["metadata"]),
        message="Backup criado com sucesso. Use /backup/download para baixar."
    )


@router.get("/download")
async def download_backup():
    """
    Baixa o último backup criado
    
    Retorna o arquivo de backup para download.
    """
    global _last_backup
    
    if not _last_backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum backup disponível. Crie um backup primeiro."
        )
    
    # Decodificar base64
    backup_bytes = base64.b64decode(_last_backup["content"])
    
    # Definir nome do arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if _last_backup["format"] == "zip":
        filename = f"idface_backup_{timestamp}.zip"
        media_type = "application/zip"
    else:
        filename = f"idface_backup_{timestamp}.json"
        media_type = "application/json"
    
    # Retornar como download
    return Response(
        content=backup_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/restore", response_model=RestoreResponse)
async def restore_backup(
    request: BackupRestoreRequest,
    db = Depends(get_db)
):
    """
    Restaura dados a partir de um backup
    
    - **backup_data**: Dados do backup em base64 (JSON ou ZIP)
    - **clear_before**: Limpar banco de dados antes de restaurar (CUIDADO!)
    - **skip_existing**: Pular registros que já existem
    - **restore_logs**: Incluir restauração de logs de acesso
    
    ⚠️ ATENÇÃO: Operação destrutiva se clear_before=true
    """
    backup_service = BackupService(db)
    
    # Decodificar backup
    try:
        backup_decoded = base64.b64decode(request.backup_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao decodificar backup: {str(e)}"
        )
    
    # Restaurar
    result = await backup_service.restore_from_backup(
        backup_data=backup_decoded,
        clear_before=request.clear_before,
        skip_existing=request.skip_existing,
        restore_logs=request.restore_logs
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Erro ao restaurar backup")
        )
    
    return RestoreResponse(**result)


@router.post("/validate")
async def validate_backup(
    backup_data: str,
    db = Depends(get_db)
):
    """
    Valida a estrutura de um backup sem restaurá-lo
    
    Útil para verificar se o backup está correto antes de restaurar.
    """
    backup_service = BackupService(db)
    
    try:
        backup_decoded = base64.b64decode(backup_data)
        
        # Tentar descompactar se for ZIP
        try:
            backup_str = backup_decoded.decode('utf-8')
        except:
            # Pode ser ZIP
            backup_str = backup_service._decompress_backup(backup_decoded)
        
        result = await backup_service.validate_backup(backup_str)
        
        return result
        
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)]
        }


@router.get("/info")
async def get_backup_info():
    """
    Retorna informações sobre o último backup criado
    """
    global _last_backup
    
    if not _last_backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum backup disponível"
        )
    
    return {
        "format": _last_backup["format"],
        "metadata": _last_backup["metadata"],
        "created_at": _last_backup["created_at"].isoformat(),
        "available": True
    }


@router.delete("/clear")
async def clear_backup_cache():
    """
    Limpa o backup em cache
    """
    global _last_backup
    _last_backup = None
    
    return {
        "success": True,
        "message": "Cache de backup limpo"
    }


# ==================== Backup Automático ====================

@router.post("/schedule")
async def schedule_automatic_backup(
    interval_hours: int = 24,
    include_images: bool = False,
    include_logs: bool = True
):
    """
    Agenda backup automático (futuro)
    
    Por enquanto, apenas retorna configuração.
    Em produção, usar Celery ou similar.
    """
    return {
        "success": True,
        "message": "Backup automático agendado (funcionalidade futura)",
        "configuration": {
            "interval_hours": interval_hours,
            "include_images": include_images,
            "include_logs": include_logs,
            "next_run": "N/A"
        }
    }


# ==================== Estatísticas do Banco ====================

@router.get("/database-stats")
async def get_database_statistics(db = Depends(get_db)):
    """
    Retorna estatísticas do banco de dados atual
    
    Útil para saber o tamanho antes de fazer backup.
    """
    stats = {
        "users": await db.user.count(),
        "access_rules": await db.accessrule.count(),
        "time_zones": await db.timezone.count(),
        "groups": await db.group.count(),
        "portals": await db.portal.count(),
        "access_logs": await db.accesslog.count(),
        "cards": await db.card.count(),
        "qrcodes": await db.qrcode.count(),
        "templates": await db.template.count()
    }
    
    # Calcular estimativa de tamanho
    users_with_image = await db.user.count(where={"image": {"not": None}})
    
    # Estimativa: 1MB por imagem + 1KB por registro
    estimated_size_mb = (
        (users_with_image * 1.0) +  # Imagens
        (stats["users"] * 0.001) +   # Usuários
        (stats["access_logs"] * 0.0005)  # Logs
    )
    
    stats["users_with_image"] = users_with_image
    stats["estimated_backup_size_mb"] = round(estimated_size_mb, 2)
    
    return {
        "success": True,
        "statistics": stats,
        "timestamp": datetime.now().isoformat()
    }


# ==================== Cache Global (Temporário) ====================
# Em produção, usar Redis ou storage persistente
_last_backup = None