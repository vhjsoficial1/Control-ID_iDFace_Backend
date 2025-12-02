"""
Rotas da API para Backup e Restore
"""
from fastapi import APIRouter, HTTPException, Depends, status, Response, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.services.backup_service import BackupService
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import io
import base64
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Schemas ====================

class BackupCreateRequest(BaseModel):
    """Requisição para criar backup"""
    include_images: bool = Field(False, description="Incluir imagens faciais")
    include_logs: bool = Field(True, description="Incluir logs de acesso")
    compress: bool = Field(True, description="Compactar em ZIP")


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


# ==================== Funções Auxiliares ====================

async def run_backup_task(db: any, include_images: bool, include_logs: bool, compress: bool):
    """
    Executa a criação do backup em background
    """
    global _last_backup
    backup_service = BackupService(db)
    
    result = await backup_service.create_full_backup(
        include_images=include_images,
        include_logs=include_logs,
        compress=compress
    )
    
    if result.get("success"):
        backup_content = result["backup_data"]
        if isinstance(backup_content, bytes):
            backup_b64 = base64.b64encode(backup_content).decode('utf-8')
        else:
            backup_b64 = base64.b64encode(backup_content.encode('utf-8')).decode('utf-8')
        
        _last_backup = {
            "content": backup_b64,
            "format": result["format"],
            "metadata": result["metadata"],
            "created_at": datetime.now()
        }
        print(f"✅ Backup em background concluído com sucesso. Formato: {result['format']}")
    else:
        print(f"❌ Erro ao executar backup em background: {result.get('error')}")


# ==================== Endpoints ====================

@router.post("/create-async")
async def create_backup_async(
    request: BackupCreateRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Inicia a criação de um backup em background.
    
    O processo roda em segundo plano e não bloqueia a resposta.
    O resultado estará disponível para download em /backup/download assim que finalizado.
    """
    background_tasks.add_task(
        run_backup_task,
        db,
        request.include_images,
        request.include_logs,
        request.compress
    )
    return {
        "success": True,
        "message": "Criação de backup iniciada em background. Verifique o status em /backup/info."
    }


@router.post("/create", response_model=BackupResponse)
async def create_backup(
    request: BackupCreateRequest,
    db = Depends(get_db)
):
    """
    Cria um backup completo do banco de dados e aguarda o resultado.
    
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
    db: any = Depends(get_db),
    backup_file: UploadFile = File(..., description="Arquivo de backup (.json ou .zip)"),
    clear_before: bool = Form(False, description="Limpar banco de dados antes de restaurar (CUIDADO!)"),
    skip_existing: bool = Form(True, description="Pular registros que já existem"),
    restore_logs: bool = Form(False, description="Incluir restauração de logs de acesso")
):
    """
    Restaura dados a partir de um arquivo de backup
    
    - **backup_file**: Arquivo de backup (.json ou .zip)
    - **clear_before**: Limpar banco de dados antes de restaurar (CUIDADO!)
    - **skip_existing**: Pular registros que já existem
    - **restore_logs**: Incluir restauração de logs de acesso
    
    ⚠️ ATENÇÃO: Operação destrutiva se clear_before=true
    """
    backup_service = BackupService(db)
    
    # Ler conteúdo do arquivo
    backup_content = await backup_file.read()
    
    # Restaurar
    result = await backup_service.restore_from_backup(
        backup_data=backup_content,
        clear_before=clear_before,
        skip_existing=skip_existing,
        restore_logs=restore_logs
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Erro ao restaurar backup")
        )
    
    return RestoreResponse(**result)


@router.post("/validate")
async def validate_backup(
    db: any = Depends(get_db),
    backup_file: UploadFile = File(..., description="Arquivo de backup para validar (.json ou .zip)")
):
    """
    Valida a estrutura de um backup sem restaurá-lo
    
    Útil para verificar se o backup está correto antes de restaurar.
    """
    backup_service = BackupService(db)
    
    try:
        backup_content = await backup_file.read()
        
        # Tentar descompactar se for ZIP
        try:
            backup_str = backup_content.decode('utf-8')
        except UnicodeDecodeError:
            # Pode ser ZIP
            backup_str = backup_service._decompress_backup(backup_content)
        
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

# Variáveis globais para gerenciar o scheduler
_backup_scheduler = None
_scheduler_config = {
    "enabled": False,
    "interval_hours": 24,
    "include_images": False,
    "include_logs": True,
    "next_run": None,
    "last_run": None,
    "history": []
}


def get_backup_scheduler():
    """Obtém ou cria instância do scheduler"""
    global _backup_scheduler
    if _backup_scheduler is None:
        _backup_scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
        _backup_scheduler.start()
    return _backup_scheduler


async def scheduled_backup_job():
    """Job que executa o backup agendado"""
    global _scheduler_config
    
    logger.info("🔄 Executando backup agendado...")
    
    try:
        # Garantir conexão com o banco
        if not db.is_connected():
            await db.connect()
        
        backup_service = BackupService(db)
        
        # Criar backup com configurações salvas
        result = await backup_service.create_full_backup(
            include_images=_scheduler_config["include_images"],
            include_logs=_scheduler_config["include_logs"],
            compress=True
        )
        
        if result.get("success"):
            # Salvar no cache global
            backup_content = result["backup_data"]
            if isinstance(backup_content, bytes):
                backup_b64 = base64.b64encode(backup_content).decode('utf-8')
            else:
                backup_b64 = base64.b64encode(backup_content.encode('utf-8')).decode('utf-8')
            
            global _last_backup
            _last_backup = {
                "content": backup_b64,
                "format": result["format"],
                "metadata": result["metadata"],
                "created_at": datetime.now()
            }
            
            # Atualizar histórico
            _scheduler_config["last_run"] = datetime.now().isoformat()
            _scheduler_config["history"].insert(0, {
                "timestamp": datetime.now().isoformat(),
                "size_mb": result["metadata"]["size_mb"],
                "duration": result["metadata"]["duration_seconds"],
                "success": True
            })
            
            # Manter apenas últimos 10 registros
            _scheduler_config["history"] = _scheduler_config["history"][:10]
            
            logger.info(
                f"✅ Backup agendado concluído! "
                f"Tamanho: {result['metadata']['size_mb']} MB"
            )
        else:
            logger.error(f"❌ Falha no backup agendado: {result.get('error')}")
            
            _scheduler_config["history"].insert(0, {
                "timestamp": datetime.now().isoformat(),
                "error": result.get("error"),
                "success": False
            })
            
    except Exception as e:
        logger.error(f"❌ Erro crítico no backup agendado: {e}", exc_info=True)
        
        _scheduler_config["history"].insert(0, {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "success": False
        })


@router.get("/scheduler/status")
async def get_scheduler_status():
    """
    Retorna o status atual do scheduler de backup
    """
    global _scheduler_config
    
    scheduler = get_backup_scheduler()
    jobs = scheduler.get_jobs()
    
    # Buscar o job de backup
    backup_job = None
    for job in jobs:
        if job.id == "scheduled_backup":
            backup_job = job
            break
    
    next_run = None
    if backup_job and backup_job.next_run_time:
        next_run = backup_job.next_run_time.isoformat()
        _scheduler_config["next_run"] = next_run
    
    return {
        "success": True,
        "enabled": _scheduler_config["enabled"],
        "intervalHours": _scheduler_config["interval_hours"],
        "includeImages": _scheduler_config["include_images"],
        "includeLogs": _scheduler_config["include_logs"],
        "nextRun": next_run or _scheduler_config.get("next_run"),
        "lastRun": _scheduler_config.get("last_run"),
        "scheduledTime": "03:00" if _scheduler_config["interval_hours"] == 24 else None,
        "history": _scheduler_config.get("history", [])
    }


@router.post("/scheduler/enable")
async def enable_scheduler(
    interval_hours: int = 24,
    include_images: bool = False,
    include_logs: bool = True
):
    """
    Habilita o scheduler de backup automático
    
    - **interval_hours**: Intervalo em horas entre backups
    - **include_images**: Incluir imagens faciais
    - **include_logs**: Incluir logs de acesso
    """
    global _scheduler_config
    
    try:
        scheduler = get_backup_scheduler()
        
        # Remover job existente se houver
        if scheduler.get_job("scheduled_backup"):
            scheduler.remove_job("scheduled_backup")
        
        # Atualizar configurações
        _scheduler_config["enabled"] = True
        _scheduler_config["interval_hours"] = interval_hours
        _scheduler_config["include_images"] = include_images
        _scheduler_config["include_logs"] = include_logs
        
        # Criar trigger baseado no intervalo
        if interval_hours == 24:
            # Backup diário às 03:00
            trigger = CronTrigger(hour=3, minute=0, timezone="America/Sao_Paulo")
        else:
            # Intervalo personalizado
            trigger = IntervalTrigger(hours=interval_hours, timezone="America/Sao_Paulo")
        
        # Adicionar job
        job = scheduler.add_job(
            scheduled_backup_job,
            trigger=trigger,
            id="scheduled_backup",
            name="Backup Automático",
            replace_existing=True
        )
        
        next_run = job.next_run_time.isoformat() if job.next_run_time else None
        _scheduler_config["next_run"] = next_run
        
        logger.info(
            f"✅ Scheduler habilitado: "
            f"intervalo={interval_hours}h, "
            f"próxima execução={next_run}"
        )
        
        return {
            "success": True,
            "message": "Backup automático habilitado",
            "nextRun": next_run,
            "config": {
                "interval_hours": interval_hours,
                "include_images": include_images,
                "include_logs": include_logs
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao habilitar scheduler: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/scheduler/disable")
async def disable_scheduler():
    """
    Desabilita o scheduler de backup automático
    """
    global _scheduler_config
    
    try:
        scheduler = get_backup_scheduler()
        
        # Remover job
        if scheduler.get_job("scheduled_backup"):
            scheduler.remove_job("scheduled_backup")
            logger.info("✅ Scheduler desabilitado")
        
        _scheduler_config["enabled"] = False
        _scheduler_config["next_run"] = None
        
        return {
            "success": True,
            "message": "Backup automático desabilitado"
        }
        
    except Exception as e:
        logger.error(f"Erro ao desabilitar scheduler: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/scheduler/run-now")
async def run_backup_now(db = Depends(get_db)):
    """
    Executa o backup agendado imediatamente (sem esperar próximo ciclo)
    """
    try:
        logger.info("🔄 Executando backup manual via scheduler...")
        
        await scheduled_backup_job()
        
        # Buscar último backup criado
        global _last_backup
        if _last_backup:
            return {
                "success": True,
                "message": "Backup executado com sucesso",
                "size_mb": _last_backup.get("metadata", {}).get("size_mb"),
                "format": _last_backup.get("format")
            }
        
        return {
            "success": True,
            "message": "Backup executado"
        }
        
    except Exception as e:
        logger.error(f"Erro ao executar backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/scheduler/next-run")
async def get_next_run():
    """
    Retorna data/hora da próxima execução agendada
    """
    scheduler = get_backup_scheduler()
    job = scheduler.get_job("scheduled_backup")
    
    if not job:
        return {
            "success": False,
            "message": "Nenhum backup agendado"
        }
    
    return {
        "success": True,
        "nextRun": job.next_run_time.isoformat() if job.next_run_time else None,
        "jobId": job.id,
        "jobName": job.name
    }