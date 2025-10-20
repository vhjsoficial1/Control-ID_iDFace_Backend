"""
Rotas da API para Geração de Relatórios
"""
from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from fastapi.responses import StreamingResponse
from app.database import get_db
from app.services.report_service import ReportService
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import io

router = APIRouter()


# ==================== Schemas ====================

class UserReportRequest(BaseModel):
    """Requisição para relatório de usuários"""
    start_date: Optional[datetime] = Field(None, description="Data inicial (por createdAt)")
    end_date: Optional[datetime] = Field(None, description="Data final (por createdAt)")
    status_filter: Optional[str] = Field(None, description="active, expired, pending, all")
    with_image: Optional[bool] = Field(None, description="Filtrar por usuários com imagem")
    synced_only: bool = Field(False, description="Apenas sincronizados")
    include_cards: bool = Field(True, description="Incluir informações de cartões")
    include_access_rules: bool = Field(True, description="Incluir regras de acesso")
    format: str = Field("json", description="json, csv, excel")


class AccessReportRequest(BaseModel):
    """Requisição para relatório de acessos"""
    start_date: datetime = Field(..., description="Data/hora inicial")
    end_date: datetime = Field(..., description="Data/hora final")
    user_ids: Optional[List[int]] = Field(None, description="Filtrar por usuários")
    portal_ids: Optional[List[int]] = Field(None, description="Filtrar por portais")
    events: Optional[List[str]] = Field(None, description="Filtrar por eventos")
    group_by: str = Field("day", description="day, hour, user, portal, event")
    include_details: bool = Field(True, description="Incluir logs detalhados")
    format: str = Field("json", description="json, csv, excel")


# ==================== RELATÓRIOS DE USUÁRIOS ====================

@router.post("/users")
async def generate_users_report(
    request: UserReportRequest,
    db = Depends(get_db)
):
    """
    Gera relatório completo de usuários
    
    **Filtros disponíveis:**
    - `start_date` / `end_date`: Período de criação dos usuários
    - `status_filter`: active, expired, pending, all
    - `with_image`: true (apenas com imagem), false (sem imagem), null (todos)
    - `synced_only`: apenas usuários sincronizados com iDFace
    
    **Formatos:**
    - `json`: Retorna JSON estruturado
    - `csv`: Retorna CSV para download
    - `excel`: Retorna XLSX para download (requer openpyxl)
    """
    report_service = ReportService(db)
    
    result = await report_service.generate_users_report(
        start_date=request.start_date,
        end_date=request.end_date,
        status_filter=request.status_filter,
        with_image=request.with_image,
        synced_only=request.synced_only,
        include_cards=request.include_cards,
        include_access_rules=request.include_access_rules,
        format_type=request.format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Erro ao gerar relatório")
        )
    
    # Se for CSV ou Excel, retornar como download
    if request.format in ["csv", "excel"]:
        content = result["content"]
        filename = result["filename"]
        
        if request.format == "csv":
            media_type = "text/csv"
        else:
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return Response(
            content=content if isinstance(content, bytes) else content.encode('utf-8'),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    # JSON
    return result


@router.get("/users/quick")
async def quick_users_summary(db = Depends(get_db)):
    """
    Resumo rápido de usuários (sem filtros)
    
    Retorna estatísticas gerais dos usuários.
    """
    report_service = ReportService(db)
    
    result = await report_service.generate_users_report(
        format_type="json"
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar resumo"
        )
    
    # Retornar apenas estatísticas
    return {
        "success": True,
        "statistics": result["data"]["statistics"],
        "generated_at": result["data"]["generated_at"]
    }


# ==================== RELATÓRIOS DE ACESSOS ====================

@router.post("/access")
async def generate_access_report(
    request: AccessReportRequest,
    db = Depends(get_db)
):
    """
    Gera relatório de acessos (logs)
    
    **Obrigatório:**
    - `start_date`: Data/hora inicial do período
    - `end_date`: Data/hora final do período
    
    **Filtros opcionais:**
    - `user_ids`: Lista de IDs de usuários
    - `portal_ids`: Lista de IDs de portais
    - `events`: Lista de eventos (access_granted, access_denied, etc)
    
    **Agrupamento:**
    - `day`: Agrupa por dia
    - `hour`: Agrupa por hora
    - `user`: Agrupa por usuário
    - `portal`: Agrupa por portal
    - `event`: Agrupa por tipo de evento
    
    **Formatos:**
    - `json`: Retorna JSON com estatísticas e logs
    - `csv`: CSV para download
    - `excel`: XLSX para download com múltiplas abas
    """
    # Validar período
    if request.end_date < request.start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data final deve ser posterior à data inicial"
        )
    
    # Limitar período máximo (opcional)
    max_days = 90
    if (request.end_date - request.start_date).days > max_days:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Período máximo: {max_days} dias"
        )
    
    report_service = ReportService(db)
    
    result = await report_service.generate_access_report(
        start_date=request.start_date,
        end_date=request.end_date,
        user_ids=request.user_ids,
        portal_ids=request.portal_ids,
        events=request.events,
        group_by=request.group_by,
        include_details=request.include_details,
        format_type=request.format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Erro ao gerar relatório")
        )
    
    # Download para CSV/Excel
    if request.format in ["csv", "excel"]:
        content = result["content"]
        filename = result["filename"]
        
        if request.format == "csv":
            media_type = "text/csv"
        else:
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return Response(
            content=content if isinstance(content, bytes) else content.encode('utf-8'),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    
    return result


# ==================== RELATÓRIOS RÁPIDOS ====================

@router.get("/access/today")
async def today_access_report(db = Depends(get_db)):
    """
    Relatório de acessos de hoje
    
    Retorna estatísticas e logs do dia atual.
    """
    report_service = ReportService(db)
    result = await report_service.quick_daily_report()
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    return result


@router.get("/access/week")
async def week_access_report(db = Depends(get_db)):
    """
    Relatório de acessos da semana atual
    
    Retorna estatísticas da semana (segunda a hoje).
    """
    report_service = ReportService(db)
    result = await report_service.quick_weekly_report()
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    return result


@router.get("/access/month")
async def month_access_report(db = Depends(get_db)):
    """
    Relatório de acessos do mês atual
    
    Retorna estatísticas do mês (dia 1 até hoje).
    """
    report_service = ReportService(db)
    result = await report_service.quick_monthly_report()
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    return result


# ==================== RELATÓRIOS POR PARÂMETROS ====================

@router.get("/access/by-date")
async def access_report_by_date(
    date: str = Query(..., description="Data no formato YYYY-MM-DD"),
    format: str = Query("json", description="json, csv, excel"),
    db = Depends(get_db)
):
    """
    Relatório de acessos de uma data específica
    
    **Exemplo:** `/reports/access/by-date?date=2024-12-25&format=csv`
    """
    try:
        report_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de data inválido. Use YYYY-MM-DD"
        )
    
    start_of_day = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = report_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    report_service = ReportService(db)
    
    result = await report_service.generate_access_report(
        start_date=start_of_day,
        end_date=end_of_day,
        format_type=format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    if format in ["csv", "excel"]:
        content = result["content"]
        filename = result["filename"]
        
        media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return Response(
            content=content if isinstance(content, bytes) else content.encode('utf-8'),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    return result


@router.get("/access/by-period")
async def access_report_by_period(
    start_date: str = Query(..., description="Data inicial YYYY-MM-DD"),
    end_date: str = Query(..., description="Data final YYYY-MM-DD"),
    format: str = Query("json", description="json, csv, excel"),
    db = Depends(get_db)
):
    """
    Relatório de acessos por período personalizado
    
    **Exemplo:** `/reports/access/by-period?start_date=2024-12-01&end_date=2024-12-31&format=excel`
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de data inválido. Use YYYY-MM-DD"
        )
    
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    report_service = ReportService(db)
    
    result = await report_service.generate_access_report(
        start_date=start,
        end_date=end,
        format_type=format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    if format in ["csv", "excel"]:
        content = result["content"]
        filename = result["filename"]
        
        media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        return Response(
            content=content if isinstance(content, bytes) else content.encode('utf-8'),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    return result


# ==================== RELATÓRIOS POR USUÁRIO ====================

@router.get("/access/by-user/{user_id}")
async def access_report_by_user(
    user_id: int,
    days: int = Query(30, ge=1, le=365, description="Número de dias retroativos"),
    format: str = Query("json", description="json, csv"),
    db = Depends(get_db)
):
    """
    Relatório de acessos de um usuário específico
    
    Retorna todos os acessos do usuário nos últimos X dias.
    """
    # Verificar se usuário existe
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {user_id} não encontrado"
        )
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    report_service = ReportService(db)
    
    result = await report_service.generate_access_report(
        start_date=start_date,
        end_date=end_date,
        user_ids=[user_id],
        format_type=format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    if format == "csv":
        content = result["content"]
        filename = f"acessos_usuario_{user_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        return Response(
            content=content.encode('utf-8'),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    # Adicionar informações do usuário
    result["data"]["user"] = {
        "id": user.id,
        "name": user.name,
        "registration": user.registration
    }
    
    return result


# ==================== RELATÓRIOS POR PORTAL ====================

@router.get("/access/by-portal/{portal_id}")
async def access_report_by_portal(
    portal_id: int,
    days: int = Query(30, ge=1, le=365),
    format: str = Query("json"),
    db = Depends(get_db)
):
    """
    Relatório de acessos de um portal específico
    
    Retorna todos os acessos do portal nos últimos X dias.
    """
    # Verificar se portal existe
    portal = await db.portal.find_unique(where={"id": portal_id})
    if not portal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Portal {portal_id} não encontrado"
        )
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    report_service = ReportService(db)
    
    result = await report_service.generate_access_report(
        start_date=start_date,
        end_date=end_date,
        portal_ids=[portal_id],
        format_type=format
    )
    
    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar relatório"
        )
    
    if format == "csv":
        content = result["content"]
        filename = f"acessos_portal_{portal_id}_{datetime.now().strftime('%Y%m%d')}.csv"
        
        return Response(
            content=content.encode('utf-8'),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    # Adicionar informações do portal
    result["data"]["portal"] = {
        "id": portal.id,
        "name": portal.name
    }
    
    return result


# ==================== ESTATÍSTICAS GERAIS ====================

@router.get("/statistics")
async def get_general_statistics(db = Depends(get_db)):
    """
    Retorna estatísticas gerais do sistema
    
    Dashboard com números consolidados.
    """
    # Usuários
    total_users = await db.user.count()
    users_with_image = await db.user.count(where={"image": {"not": None}})
    synced_users = await db.user.count(where={"idFaceId": {"not": None}})
    
    # Acessos (últimos 30 dias)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_logs = await db.accesslog.count(
        where={"timestamp": {"gte": thirty_days_ago}}
    )
    
    granted = await db.accesslog.count(
        where={
            "timestamp": {"gte": thirty_days_ago},
            "event": "access_granted"
        }
    )
    
    denied = await db.accesslog.count(
        where={
            "timestamp": {"gte": thirty_days_ago},
            "event": "access_denied"
        }
    )
    
    # Outros
    total_rules = await db.accessrule.count()
    total_portals = await db.portal.count()
    total_cards = await db.card.count()
    
    return {
        "success": True,
        "generated_at": datetime.now().isoformat(),
        "statistics": {
            "users": {
                "total": total_users,
                "with_image": users_with_image,
                "synced": synced_users,
                "percentage_with_image": round((users_with_image / total_users * 100), 2) if total_users > 0 else 0
            },
            "access_logs": {
                "last_30_days": recent_logs,
                "granted": granted,
                "denied": denied,
                "success_rate": round((granted / (granted + denied) * 100), 2) if (granted + denied) > 0 else 0
            },
            "system": {
                "access_rules": total_rules,
                "portals": total_portals,
                "cards": total_cards
            }
        }
    }