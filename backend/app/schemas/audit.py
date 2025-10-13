from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ==================== Base Schemas ====================

class AccessLogBase(BaseModel):
    userId: Optional[int] = None
    portalId: Optional[int] = None
    event: str = Field(..., description="Tipo de evento: access_granted, access_denied, unknown_user, etc.")
    reason: Optional[str] = Field(None, description="Motivo da negação de acesso")
    cardValue: Optional[str] = Field(None, description="Número do cartão utilizado")


# ==================== Create Schemas ====================

class AccessLogCreate(AccessLogBase):
    timestamp: Optional[datetime] = Field(default_factory=datetime.now)


# ==================== Response Schemas ====================

class AccessLogResponse(AccessLogBase):
    id: int
    timestamp: datetime
    
    # Dados relacionados (opcional)
    userName: Optional[str] = None
    portalName: Optional[str] = None
    
    class Config:
        from_attributes = True


class AccessLogListResponse(BaseModel):
    total: int
    logs: list[AccessLogResponse]


class AccessLogWithDetails(AccessLogResponse):
    """Log de acesso com informações completas do usuário e portal"""
    user: Optional[dict] = None
    portal: Optional[dict] = None


# ==================== Statistics Schemas ====================

class AccessStatsByUser(BaseModel):
    userId: int
    userName: str
    totalAccess: int
    granted: int
    denied: int
    lastAccess: Optional[datetime] = None


class AccessStatsByPortal(BaseModel):
    portalId: int
    portalName: str
    totalAccess: int
    granted: int
    denied: int
    unknownUsers: int


class AccessStatsByEvent(BaseModel):
    event: str
    count: int
    percentage: float


class AccessStatsByHour(BaseModel):
    hour: int
    count: int


class AccessStatsByDate(BaseModel):
    date: str
    granted: int
    denied: int
    unknown: int
    total: int


class AccessStatisticsResponse(BaseModel):
    totalLogs: int
    dateRange: dict
    byEvent: list[AccessStatsByEvent]
    byHour: Optional[list[AccessStatsByHour]] = None
    byDate: Optional[list[AccessStatsByDate]] = None
    topUsers: Optional[list[AccessStatsByUser]] = None
    topPortals: Optional[list[AccessStatsByPortal]] = None


# ==================== Filter Schemas ====================

class AccessLogFilter(BaseModel):
    """Filtros para busca de logs"""
    userId: Optional[int] = None
    portalId: Optional[int] = None
    event: Optional[str] = None
    startDate: Optional[datetime] = None
    endDate: Optional[datetime] = None
    cardValue: Optional[str] = None


# ==================== Export Schemas ====================

class ExportRequest(BaseModel):
    format: str = Field("csv", description="Formato de exportação: csv, json, pdf")
    filters: Optional[AccessLogFilter] = None
    includeDetails: bool = Field(True, description="Incluir detalhes de usuário e portal")


class ExportResponse(BaseModel):
    success: bool
    message: str
    downloadUrl: Optional[str] = None
    recordCount: int