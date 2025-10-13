from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ==================== Enums ====================

class SyncDirection(str, Enum):
    """Direção da sincronização"""
    TO_IDFACE = "to_idface"      # Local -> iDFace
    FROM_IDFACE = "from_idface"  # iDFace -> Local
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(str, Enum):
    """Status da sincronização"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class SyncEntityType(str, Enum):
    """Tipos de entidades que podem ser sincronizadas"""
    USERS = "users"
    ACCESS_RULES = "access_rules"
    TIME_ZONES = "time_zones"
    PORTALS = "portals"
    GROUPS = "groups"
    CARDS = "cards"
    ACCESS_LOGS = "access_logs"
    ALL = "all"


# ==================== Sync Request Schemas ====================

class SyncEntityRequest(BaseModel):
    """Requisição para sincronizar uma entidade específica"""
    entityType: SyncEntityType
    entityId: Optional[int] = Field(None, description="ID da entidade. Se None, sincroniza todas")
    direction: SyncDirection = SyncDirection.TO_IDFACE
    overwrite: bool = Field(False, description="Sobrescrever dados existentes")
    syncRelated: bool = Field(True, description="Sincronizar entidades relacionadas")


class BulkSyncRequest(BaseModel):
    """Requisição para sincronização em massa"""
    entities: List[SyncEntityType]
    direction: SyncDirection
    overwrite: bool = False
    syncImages: bool = Field(True, description="Incluir imagens de usuários")
    syncAccessLogs: bool = Field(False, description="Incluir logs de acesso")


class FullSyncRequest(BaseModel):
    """Requisição para sincronização completa"""
    direction: SyncDirection = SyncDirection.BIDIRECTIONAL
    overwrite: bool = False
    clearBeforeSync: bool = Field(False, description="Limpar dados locais antes de sincronizar")
    entities: Optional[List[SyncEntityType]] = Field(None, description="Se None, sincroniza tudo")


# ==================== Sync Result Schemas ====================

class EntitySyncResult(BaseModel):
    """Resultado da sincronização de uma entidade"""
    entityType: SyncEntityType
    status: SyncStatus
    totalCount: int = 0
    successCount: int = 0
    failedCount: int = 0
    skippedCount: int = 0
    errors: List[str] = []
    duration: Optional[float] = Field(None, description="Duração em segundos")


class SyncResponse(BaseModel):
    """Resposta geral de sincronização"""
    success: bool
    message: str
    direction: SyncDirection
    startTime: datetime
    endTime: Optional[datetime] = None
    duration: Optional[float] = None
    results: List[EntitySyncResult] = []
    
    def calculate_duration(self):
        """Calcula duração total"""
        if self.endTime and self.startTime:
            self.duration = (self.endTime - self.startTime).total_seconds()


class SyncSummary(BaseModel):
    """Resumo de uma sincronização"""
    totalEntities: int
    successfulEntities: int
    failedEntities: int
    partialEntities: int
    totalRecords: int
    syncedRecords: int
    failedRecords: int
    skippedRecords: int


# ==================== Sync History Schemas ====================

class SyncHistoryRecord(BaseModel):
    """Registro histórico de sincronização"""
    id: int
    entityType: SyncEntityType
    direction: SyncDirection
    status: SyncStatus
    totalCount: int
    successCount: int
    failedCount: int
    startTime: datetime
    endTime: Optional[datetime]
    duration: Optional[float]
    errorMessage: Optional[str]
    
    class Config:
        from_attributes = True


class SyncHistoryResponse(BaseModel):
    """Resposta com histórico de sincronizações"""
    total: int
    history: List[SyncHistoryRecord]


# ==================== Device Status Schemas ====================

class DeviceConnectionStatus(BaseModel):
    """Status de conexão com o dispositivo"""
    connected: bool
    lastCheck: datetime
    responseTime: Optional[float] = Field(None, description="Tempo de resposta em ms")
    deviceIp: str
    errorMessage: Optional[str] = None


class DeviceSyncStatus(BaseModel):
    """Status de sincronização do dispositivo"""
    connection: DeviceConnectionStatus
    lastSyncTime: Optional[datetime] = None
    pendingSync: bool = False
    syncInProgress: bool = False
    deviceInfo: Optional[Dict[str, Any]] = None


# ==================== Conflict Resolution Schemas ====================

class SyncConflict(BaseModel):
    """Representa um conflito de sincronização"""
    entityType: SyncEntityType
    entityId: int
    localData: Dict[str, Any]
    remoteData: Dict[str, Any]
    conflictFields: List[str]
    localUpdatedAt: Optional[datetime]
    remoteUpdatedAt: Optional[datetime]


class ConflictResolution(BaseModel):
    """Resolução de conflito"""
    conflictId: str
    resolution: str = Field(..., description="keep_local, keep_remote, merge")
    mergeStrategy: Optional[Dict[str, str]] = Field(None, description="Estratégia para cada campo")


class ConflictResolutionRequest(BaseModel):
    """Requisição para resolver múltiplos conflitos"""
    resolutions: List[ConflictResolution]
    applyToAll: bool = Field(False, description="Aplicar mesma resolução a todos conflitos similares")


# ==================== Sync Configuration Schemas ====================

class SyncConfiguration(BaseModel):
    """Configuração de sincronização automática"""
    enabled: bool = True
    interval: int = Field(300, ge=60, description="Intervalo em segundos (mínimo 60)")
    entities: List[SyncEntityType] = [SyncEntityType.ACCESS_LOGS]
    direction: SyncDirection = SyncDirection.FROM_IDFACE
    overwrite: bool = False
    autoResolveConflicts: bool = Field(False, description="Resolver conflitos automaticamente")
    conflictStrategy: str = Field("keep_local", description="keep_local, keep_remote, skip")


class SyncConfigurationResponse(BaseModel):
    """Resposta com configuração de sincronização"""
    configuration: SyncConfiguration
    nextSyncTime: Optional[datetime] = None
    lastSyncTime: Optional[datetime] = None


# ==================== Manual Sync Schemas ====================

class UserSyncRequest(BaseModel):
    """Sincronizar usuário específico"""
    userId: int
    syncImage: bool = True
    syncCards: bool = True
    syncAccessRules: bool = True
    direction: SyncDirection = SyncDirection.TO_IDFACE


class AccessRuleSyncRequest(BaseModel):
    """Sincronizar regra de acesso específica"""
    accessRuleId: int
    syncTimeZones: bool = True
    syncUsers: bool = False
    direction: SyncDirection = SyncDirection.TO_IDFACE


class TimeZoneSyncRequest(BaseModel):
    """Sincronizar time zone específico"""
    timeZoneId: int
    syncTimeSpans: bool = True
    direction: SyncDirection = SyncDirection.TO_IDFACE


# ==================== Comparison Schemas ====================

class DataComparison(BaseModel):
    """Comparação entre dados locais e remotos"""
    entityType: SyncEntityType
    localCount: int
    remoteCount: int
    onlyLocal: List[int] = []
    onlyRemote: List[int] = []
    conflicts: List[SyncConflict] = []
    identical: int = 0


class ComparisonRequest(BaseModel):
    """Requisição para comparar dados"""
    entities: List[SyncEntityType] = [SyncEntityType.ALL]
    includeDetails: bool = Field(False, description="Incluir IDs de registros diferentes")


class ComparisonResponse(BaseModel):
    """Resposta com comparação de dados"""
    comparisons: List[DataComparison]
    totalConflicts: int
    timestamp: datetime = Field(default_factory=datetime.now)


# ==================== Batch Operations ====================

class BatchSyncItem(BaseModel):
    """Item individual em operação batch"""
    entityType: SyncEntityType
    entityId: int
    operation: str = Field(..., description="create, update, delete")


class BatchSyncRequest(BaseModel):
    """Requisição para sincronização em batch"""
    items: List[BatchSyncItem]
    direction: SyncDirection = SyncDirection.TO_IDFACE
    stopOnError: bool = Field(False, description="Parar ao encontrar erro")


class BatchSyncResponse(BaseModel):
    """Resposta de sincronização batch"""
    success: bool
    totalItems: int
    processedItems: int
    failedItems: int
    results: List[Dict[str, Any]]
    errors: List[str] = []