from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# Configurações e Banco de Dados
from app.config import settings
from app.database import db
from app.services.backup_service import BackupService

# Agendador
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Routers
from app.routers import users, access_rules, time_zones, audit, sync, system, backup, report, realtime, capture, auth, visitor

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================== Atividade Agendado ====================

async def job_backup_automatico():
    """
    Atividade que executa o backup automático do banco de dados.
    """
    logger.info("Executando job de backup automático...")
    try:
        # Garantir que o banco de dados está conectado
        if not db.is_connected():
            await db.connect()
            logger.info("DB conectado para o job de backup.")
        
        # Instanciar o serviço de backup
        backup_service = BackupService(db)
        
        # Criar o backup (apenas logs, sem imagens, compactado)
        result = await backup_service.create_full_backup(
            include_images=False,
            include_logs=True,
            compress=True
        )
        
        if result.get("success"):
            metadata = result.get("metadata", {})
            logger.info(
                f"✅ Backup automático concluído com sucesso! "
                f"Tamanho: {metadata.get('size_mb', 'N/A')} MB, "
                f"Duração: {metadata.get('duration_seconds', 'N/A')}s"
            )
        else:
            logger.error(f"❌ Falha no backup automático: {result.get('error', 'Erro desconhecido')}")
            
    except Exception as e:
        logger.error(f"❌ Erro crítico no job de backup automático: {e}", exc_info=True)


# ==================== Ciclo de Vida da Aplicação ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação, incluindo startup e shutdown.
    """
    # --- Startup ---
    # Conectar ao banco de dados
    await db.connect()
    logger.info("✅ Banco de dados conectado.")
    
    # Iniciar o agendador de tarefas
    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(
        job_backup_automatico,
        CronTrigger(hour=3, minute=0),  # Executa todo dia às 03:00 AM
        name="Backup Automático Diário"
    )
    scheduler.start()
    logger.info("✅ Agendador de tarefas iniciado. Job de backup programado para as 03:00.")
    
    yield
    
    # --- Shutdown ---
    # Desligar o agendador
    logger.info("Encerrando agendador de tarefas...")
    scheduler.shutdown(wait=False)
    logger.info("✅ Agendador de tarefas encerrado.")
    
    # Desconectar do banco de dados
    await db.disconnect()
    logger.info("❌ Banco de dados desconectado.")


# ==================== Instância da Aplicação ====================

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API para controle e gerenciamento do leitor facial iDFace",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health check
@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "online",
        "service": "iDFace Control System",
        "version": settings.API_VERSION
    }

# Include routers
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(visitor.router, prefix="/api/v1/visitors", tags=["Visitors"])
app.include_router(access_rules.router, prefix="/api/v1/access-rules", tags=["Access Rules"])
app.include_router(time_zones.router, prefix="/api/v1/time-zones", tags=["Time Zones"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit"])
app.include_router(sync.router, prefix="/api/v1/sync", tags=["Synchronization"])
app.include_router(system.router, prefix="/api/v1/system", tags=["System"])
app.include_router(backup.router, prefix="/api/v1/backup", tags=["Backup"])
app.include_router(report.router, prefix="/api/v1/report", tags=["Report"])
app.include_router(realtime.router, prefix="/api/v1/realtime", tags=["Realtime Monitoring"])
app.include_router(capture.router, prefix="/api/v1/capture", tags=["Face Capture"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])