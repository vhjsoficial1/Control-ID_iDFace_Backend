"""
Rotas da API para Monitoramento em Tempo Real
backend/app/routers/realtime.py
"""
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.services.realtime_service import RealtimeMonitorService
from typing import Optional

router = APIRouter()


@router.get("/alarm-status")
async def get_alarm_status(db = Depends(get_db)):
    """
    Verifica status de alarme do dispositivo
    
    Endpoint equivalente a: POST alarm_status.fcgi
    """
    service = RealtimeMonitorService(db)
    return await service.check_alarm_status()


@router.get("/new-logs")
async def get_new_logs(
    since_id: Optional[int] = Query(None, description="ID do último log processado"),
    db = Depends(get_db)
):
    """
    Busca novos logs de acesso desde o último ID
    
    Endpoint equivalente a: POST load_objects.fcgi
    
    **Parâmetros:**
    - `since_id`: ID do último log processado (opcional)
    
    **Uso no frontend:**
    - Primeira chamada: não enviar since_id
    - Chamadas seguintes: enviar o lastId retornado na resposta anterior
    """
    service = RealtimeMonitorService(db)
    return await service.get_new_access_logs(since_id)


@router.get("/log-count")
async def get_log_count(db = Depends(get_db)):
    """
    Retorna contagem total de logs no dispositivo
    
    Equivalente ao COUNT(*) que o sistema iDFace faz
    """
    service = RealtimeMonitorService(db)
    return await service.get_access_log_count()


@router.get("/recent-activity")
async def get_recent_activity(
    minutes: int = Query(5, ge=1, le=60, description="Minutos retroativos"),
    db = Depends(get_db)
):
    """
    Retorna atividade recente (últimos X minutos)
    
    **Parâmetros:**
    - `minutes`: Quantos minutos retroativos (padrão: 5, máx: 60)
    """
    service = RealtimeMonitorService(db)
    return await service.get_recent_activity(minutes)


@router.get("/monitor")
async def monitor_full_status(
    since_id: Optional[int] = Query(None, description="ID do último log processado"),
    db = Depends(get_db)
):
    """
    Retorna status completo do sistema em tempo real
    
    **Inclui:**
    - Status de alarme
    - Novos logs de acesso
    - Contagem total de logs
    - Atividade recente (últimos 5 logs)
    - Status do dispositivo
    
    **Recomendado para polling no frontend:**
    - Chamar a cada 2-5 segundos
    - Usar este endpoint único em vez de múltiplos
    """
    service = RealtimeMonitorService(db)
    return await service.monitor_full_status(since_id)