from fastapi import APIRouter, HTTPException, Depends, status, Query
from app.database import get_db
from app.utils.idface_client import idface_client
from app.schemas.audit import (
    AccessLogCreate, AccessLogResponse, AccessLogListResponse,
    AccessLogWithDetails, AccessLogFilter, AccessStatisticsResponse,
    AccessStatsByUser, AccessStatsByPortal, AccessStatsByEvent,
    AccessStatsByHour, AccessStatsByDate, ExportRequest, ExportResponse
)
from typing import Optional, List
from datetime import datetime, timedelta
from collections import Counter, defaultdict

router = APIRouter()


# ==================== CRUD Operations ====================

@router.post("/", response_model=AccessLogResponse, status_code=status.HTTP_201_CREATED)
async def create_access_log(log: AccessLogCreate, db = Depends(get_db)):
    """
    Cria um registro de log de acesso manualmente
    (Normalmente criado automaticamente pelo sistema)
    """
    try:
        new_log = await db.accesslog.create(
            data={
                "userId": log.userId,
                "portalId": log.portalId,
                "event": log.event,
                "reason": log.reason,
                "cardValue": log.cardValue,
                "timestamp": log.timestamp
            }
        )
        return new_log
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao criar log: {str(e)}"
        )


@router.get("/", response_model=AccessLogListResponse)
async def list_access_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    userId: Optional[int] = None,
    portalId: Optional[int] = None,
    event: Optional[str] = None,
    startDate: Optional[datetime] = None,
    endDate: Optional[datetime] = None,
    cardValue: Optional[str] = None,
    db = Depends(get_db)
):
    """
    Lista logs de acesso com filtros opcionais
    """
    # Construir filtros
    where = {}
    
    if userId:
        where["userId"] = userId
    
    if portalId:
        where["portalId"] = portalId
    
    if event:
        where["event"] = event
    
    if cardValue:
        where["cardValue"] = cardValue
    
    # Filtro de data
    if startDate or endDate:
        where["timestamp"] = {}
        if startDate:
            where["timestamp"]["gte"] = startDate
        if endDate:
            where["timestamp"]["lte"] = endDate
    
    # Buscar logs
    logs = await db.accesslog.find_many(
        where=where,
        skip=skip,
        take=limit,
        order_by={"timestamp": "desc"},
        include={
            "user": True,
            "portal": True
        }
    )
    
    # Contar total
    total = await db.accesslog.count(where=where)
    
    # Formatar resposta com nomes
    formatted_logs = []
    for log in logs:
        log_dict = {
            "id": log.id,
            "userId": log.userId,
            "portalId": log.portalId,
            "event": log.event,
            "reason": log.reason,
            "cardValue": log.cardValue,
            "timestamp": log.timestamp,
            "userName": log.user.name if log.user else None,
            "portalName": log.portal.name if log.portal else None
        }
        formatted_logs.append(AccessLogResponse(**log_dict))
    
    return AccessLogListResponse(total=total, logs=formatted_logs)


@router.get("/{log_id}", response_model=AccessLogWithDetails)
async def get_access_log(log_id: int, db = Depends(get_db)):
    """
    Busca um log específico com todos os detalhes
    """
    log = await db.accesslog.find_unique(
        where={"id": log_id},
        include={
            "user": {
                "include": {
                    "cards": True,
                    "qrcodes": True
                }
            },
            "portal": True
        }
    )
    
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log {log_id} não encontrado"
        )
    
    # Formatar resposta
    response = {
        "id": log.id,
        "userId": log.userId,
        "portalId": log.portalId,
        "event": log.event,
        "reason": log.reason,
        "cardValue": log.cardValue,
        "timestamp": log.timestamp,
        "userName": log.user.name if log.user else None,
        "portalName": log.portal.name if log.portal else None,
        "user": {
            "id": log.user.id,
            "name": log.user.name,
            "registration": log.user.registration,
            "cards": [{"id": c.id, "value": str(c.value)} for c in log.user.cards]
        } if log.user else None,
        "portal": {
            "id": log.portal.id,
            "name": log.portal.name
        } if log.portal else None
    }
    
    return AccessLogWithDetails(**response)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_log(log_id: int, db = Depends(get_db)):
    """
    Remove um log de acesso
    (Usar com cautela - pode afetar auditoria)
    """
    existing = await db.accesslog.find_unique(where={"id": log_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log {log_id} não encontrado"
        )
    
    await db.accesslog.delete(where={"id": log_id})


# ==================== Bulk Operations ====================

@router.delete("/bulk/delete")
async def bulk_delete_logs(
    startDate: Optional[datetime] = None,
    endDate: Optional[datetime] = None,
    event: Optional[str] = None,
    db = Depends(get_db)
):
    """
    Remove múltiplos logs com base em filtros
    """
    where = {}
    
    if startDate or endDate:
        where["timestamp"] = {}
        if startDate:
            where["timestamp"]["gte"] = startDate
        if endDate:
            where["timestamp"]["lte"] = endDate
    
    if event:
        where["event"] = event
    
    if not where:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pelo menos um filtro deve ser fornecido"
        )
    
    # Contar antes de deletar
    count = await db.accesslog.count(where=where)
    
    # Deletar
    await db.accesslog.delete_many(where=where)
    
    return {
        "success": True,
        "message": f"{count} logs removidos com sucesso",
        "deletedCount": count
    }


# ==================== Statistics & Reports ====================

@router.get("/stats/summary", response_model=AccessStatisticsResponse)
async def get_access_statistics(
    startDate: Optional[datetime] = None,
    endDate: Optional[datetime] = None,
    groupByHour: bool = False,
    groupByDate: bool = False,
    topUsersLimit: int = 10,
    topPortalsLimit: int = 10,
    db = Depends(get_db)
):
    """
    Retorna estatísticas agregadas dos logs de acesso
    """
    # Filtro de data
    where = {}
    if startDate or endDate:
        where["timestamp"] = {}
        if startDate:
            where["timestamp"]["gte"] = startDate
        if endDate:
            where["timestamp"]["lte"] = endDate
    
    # Buscar todos os logs no período
    logs = await db.accesslog.find_many(
        where=where,
        include={
            "user": True,
            "portal": True
        }
    )
    
    total_logs = len(logs)
    
    if total_logs == 0:
        return AccessStatisticsResponse(
            totalLogs=0,
            dateRange={},
            byEvent=[]
        )
    
    # Estatísticas por evento
    event_counts = Counter(log.event for log in logs)
    by_event = [
        AccessStatsByEvent(
            event=event,
            count=count,
            percentage=round((count / total_logs) * 100, 2)
        )
        for event, count in event_counts.most_common()
    ]
    
    # Range de datas
    timestamps = [log.timestamp for log in logs]
    date_range = {
        "start": min(timestamps).isoformat(),
        "end": max(timestamps).isoformat()
    }
    
    # Estatísticas por hora (opcional)
    by_hour = None
    if groupByHour:
        hour_counts = Counter(log.timestamp.hour for log in logs)
        by_hour = [
            AccessStatsByHour(hour=hour, count=count)
            for hour, count in sorted(hour_counts.items())
        ]
    
    # Estatísticas por data (opcional)
    by_date = None
    if groupByDate:
        date_stats = defaultdict(lambda: {"granted": 0, "denied": 0, "unknown": 0, "total": 0})
        
        for log in logs:
            date_key = log.timestamp.strftime("%Y-%m-%d")
            date_stats[date_key]["total"] += 1
            
            if log.event == "access_granted":
                date_stats[date_key]["granted"] += 1
            elif log.event == "access_denied":
                date_stats[date_key]["denied"] += 1
            elif log.event == "unknown_user":
                date_stats[date_key]["unknown"] += 1
        
        by_date = [
            AccessStatsByDate(
                date=date,
                granted=stats["granted"],
                denied=stats["denied"],
                unknown=stats["unknown"],
                total=stats["total"]
            )
            for date, stats in sorted(date_stats.items())
        ]
    
    # Top usuários
    user_stats = defaultdict(lambda: {"granted": 0, "denied": 0, "lastAccess": None})
    
    for log in logs:
        if log.userId:
            if log.event == "access_granted":
                user_stats[log.userId]["granted"] += 1
            elif log.event == "access_denied":
                user_stats[log.userId]["denied"] += 1
            
            if not user_stats[log.userId]["lastAccess"] or log.timestamp > user_stats[log.userId]["lastAccess"]:
                user_stats[log.userId]["lastAccess"] = log.timestamp
            user_stats[log.userId]["name"] = log.user.name if log.user else f"User {log.userId}"
    
    top_users = sorted(
        [
            AccessStatsByUser(
                userId=user_id,
                userName=stats["name"],
                totalAccess=stats["granted"] + stats["denied"],
                granted=stats["granted"],
                denied=stats["denied"],
                lastAccess=stats["lastAccess"]
            )
            for user_id, stats in user_stats.items()
        ],
        key=lambda x: x.totalAccess,
        reverse=True
    )[:topUsersLimit]
    
    # Top portais
    portal_stats = defaultdict(lambda: {"granted": 0, "denied": 0, "unknown": 0})
    
    for log in logs:
        if log.portalId:
            if log.event == "access_granted":
                portal_stats[log.portalId]["granted"] += 1
            elif log.event == "access_denied":
                portal_stats[log.portalId]["denied"] += 1
            elif log.event == "unknown_user":
                portal_stats[log.portalId]["unknown"] += 1
            
            portal_stats[log.portalId]["name"] = log.portal.name if log.portal else f"Portal {log.portalId}"
    
    top_portals = sorted(
        [
            AccessStatsByPortal(
                portalId=portal_id,
                portalName=stats["name"],
                totalAccess=stats["granted"] + stats["denied"] + stats["unknown"],
                granted=stats["granted"],
                denied=stats["denied"],
                unknownUsers=stats["unknown"]
            )
            for portal_id, stats in portal_stats.items()
        ],
        key=lambda x: x.totalAccess,
        reverse=True
    )[:topPortalsLimit]
    
    return AccessStatisticsResponse(
        totalLogs=total_logs,
        dateRange=date_range,
        byEvent=by_event,
        byHour=by_hour,
        byDate=by_date,
        topUsers=top_users,
        topPortals=top_portals
    )


# ==================== User-specific queries ====================

@router.get("/user/{user_id}/history", response_model=AccessLogListResponse)
async def get_user_access_history(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    startDate: Optional[datetime] = None,
    endDate: Optional[datetime] = None,
    db = Depends(get_db)
):
    """
    Retorna histórico de acessos de um usuário específico
    """
    # Verificar se usuário existe
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    where = {"userId": user_id}
    
    if startDate or endDate:
        where["timestamp"] = {}
        if startDate:
            where["timestamp"]["gte"] = startDate
        if endDate:
            where["timestamp"]["lte"] = endDate
    
    logs = await db.accesslog.find_many(
        where=where,
        skip=skip,
        take=limit,
        order_by={"timestamp": "desc"},
        include={"portal": True}
    )
    
    total = await db.accesslog.count(where=where)
    
    formatted_logs = [
        AccessLogResponse(
            id=log.id,
            userId=log.userId,
            portalId=log.portalId,
            event=log.event,
            reason=log.reason,
            cardValue=log.cardValue,
            timestamp=log.timestamp,
            userName=user.name,
            portalName=log.portal.name if log.portal else None
        )
        for log in logs
    ]
    
    return AccessLogListResponse(total=total, logs=formatted_logs)


# ==================== Portal-specific queries ====================

@router.get("/portal/{portal_id}/history", response_model=AccessLogListResponse)
async def get_portal_access_history(
    portal_id: int,
    skip: int = 0,
    limit: int = 100,
    startDate: Optional[datetime] = None,
    endDate: Optional[datetime] = None,
    db = Depends(get_db)
):
    """
    Retorna histórico de acessos de um portal específico
    """
    # Verificar se portal existe
    portal = await db.portal.find_unique(where={"id": portal_id})
    if not portal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portal {portal_id} não encontrado"
        )
    
    where = {"portalId": portal_id}
    
    if startDate or endDate:
        where["timestamp"] = {}
        if startDate:
            where["timestamp"]["gte"] = startDate
        if endDate:
            where["timestamp"]["lte"] = endDate
    
    logs = await db.accesslog.find_many(
        where=where,
        skip=skip,
        take=limit,
        order_by={"timestamp": "desc"},
        include={"user": True}
    )
    
    total = await db.accesslog.count(where=where)
    
    formatted_logs = [
        AccessLogResponse(
            id=log.id,
            userId=log.userId,
            portalId=log.portalId,
            event=log.event,
            reason=log.reason,
            cardValue=log.cardValue,
            timestamp=log.timestamp,
            userName=log.user.name if log.user else None,
            portalName=portal.name
        )
        for log in logs
    ]
    
    return AccessLogListResponse(total=total, logs=formatted_logs)


# ==================== Recent Activity ====================

@router.get("/recent/activity")
async def get_recent_activity(
    limit: int = Query(50, ge=1, le=500),
    minutes: int = Query(60, ge=1, le=1440),
    db = Depends(get_db)
):
    """
    Retorna atividade recente (últimos X minutos)
    """
    since = datetime.now() - timedelta(minutes=minutes)
    
    logs = await db.accesslog.find_many(
        where={
            "timestamp": {"gte": since}
        },
        take=limit,
        order_by={"timestamp": "desc"},
        include={
            "user": True,
            "portal": True
        }
    )
    
    formatted_logs = [
        {
            "id": log.id,
            "event": log.event,
            "userName": log.user.name if log.user else "Desconhecido",
            "portalName": log.portal.name if log.portal else "N/A",
            "timestamp": log.timestamp,
            "reason": log.reason
        }
        for log in logs
    ]
    
    return {
        "period": f"Últimos {minutes} minutos",
        "count": len(formatted_logs),
        "logs": formatted_logs
    }


# ==================== Sync with iDFace ====================

@router.post("/sync-from-idface")
async def sync_logs_from_idface(db = Depends(get_db)):
    """
    Importa logs de acesso do dispositivo iDFace
    """
    try:
        async with idface_client:
            result = await idface_client.load_access_logs()
            
            logs_data = result.get("access_logs", [])
            imported_count = 0
            
            for log_data in logs_data:
                # Verificar se já existe
                existing = await db.accesslog.find_first(
                    where={
                        "timestamp": log_data.get("timestamp"),
                        "userId": log_data.get("user_id"),
                        "portalId": log_data.get("portal_id")
                    }
                )
                
                if not existing:
                    await db.accesslog.create(
                        data={
                            "userId": log_data.get("user_id"),
                            "portalId": log_data.get("portal_id"),
                            "event": log_data.get("event", "unknown"),
                            "reason": log_data.get("reason"),
                            "cardValue": log_data.get("card_value"),
                            "timestamp": log_data.get("timestamp")
                        }
                    )
                    imported_count += 1
            
            return {
                "success": True,
                "message": f"Logs sincronizados com sucesso",
                "totalLogs": len(logs_data),
                "importedCount": imported_count,
                "skippedCount": len(logs_data) - imported_count
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar logs: {str(e)}"
        )