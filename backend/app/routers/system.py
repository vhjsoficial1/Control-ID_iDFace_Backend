from fastapi import APIRouter, HTTPException, Depends, status
from app.database import get_db
from app.utils.idface_client import idface_client
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

router = APIRouter()


# ==================== Schemas ====================

class SystemInformation(BaseModel):
    """Informações gerais do sistema iDFace"""
    deviceId: Optional[str] = None
    version: Optional[str] = None
    model: Optional[str] = None
    serialNumber: Optional[str] = None
    online: bool = False
    uptime: Optional[Dict[str, int]] = None


class NetworkConfiguration(BaseModel):
    """Configuração de rede do dispositivo"""
    ip: str
    gateway: Optional[str] = None
    netmask: Optional[str] = None
    mac: Optional[str] = None
    dhcp: bool = False


class StorageInformation(BaseModel):
    """Informações de armazenamento"""
    totalSpace: Optional[int] = Field(None, description="Espaço total em bytes")
    usedSpace: Optional[int] = Field(None, description="Espaço usado em bytes")
    freeSpace: Optional[int] = Field(None, description="Espaço livre em bytes")
    usagePercentage: Optional[float] = Field(None, description="Percentual de uso")


class DeviceCapacity(BaseModel):
    """Capacidade do dispositivo"""
    maxUsers: Optional[int] = None
    currentUsers: Optional[int] = None
    maxFaces: Optional[int] = None
    currentFaces: Optional[int] = None
    maxCards: Optional[int] = None
    currentCards: Optional[int] = None
    maxAccessLogs: Optional[int] = None
    currentAccessLogs: Optional[int] = None


class DeviceStatus(BaseModel):
    """Status completo do dispositivo"""
    connected: bool
    systemInfo: Optional[SystemInformation] = None
    network: Optional[NetworkConfiguration] = None
    storage: Optional[StorageInformation] = None
    capacity: Optional[DeviceCapacity] = None
    lastCheck: datetime = Field(default_factory=datetime.now)


class TimeConfiguration(BaseModel):
    """Configuração de data/hora do dispositivo"""
    currentTime: datetime
    timezone: Optional[str] = None
    ntpEnabled: bool = False
    ntpServer: Optional[str] = None


class ActionRequest(BaseModel):
    """Requisição para executar ação no dispositivo"""
    action: str = Field(..., description="Tipo de ação: open_door, alarm_on, alarm_off, etc")
    portalId: Optional[int] = Field(None, description="ID do portal (porta)")
    duration: Optional[int] = Field(None, description="Duração em segundos")
    parameters: Optional[Dict[str, Any]] = None


class ActionResponse(BaseModel):
    """Resposta de execução de ação"""
    success: bool
    action: str
    message: str
    executedAt: datetime = Field(default_factory=datetime.now)


class RebootRequest(BaseModel):
    """Requisição para reiniciar dispositivo"""
    force: bool = Field(False, description="Forçar reinicialização imediata")
    delay: int = Field(0, ge=0, le=300, description="Atraso em segundos")


class BackupRequest(BaseModel):
    """Requisição para backup de configurações"""
    includeUsers: bool = True
    includeAccessRules: bool = True
    includeTimeZones: bool = True
    includeLogs: bool = False


class BackupResponse(BaseModel):
    """Resposta de backup"""
    success: bool
    message: str
    backupSize: Optional[int] = None
    backupUrl: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.now)


class RestoreRequest(BaseModel):
    """Requisição para restaurar configurações"""
    backupData: str = Field(..., description="Dados do backup em base64")
    clearBefore: bool = Field(False, description="Limpar dados antes de restaurar")


class FirmwareInfo(BaseModel):
    """Informações de firmware"""
    currentVersion: str
    latestVersion: Optional[str] = None
    updateAvailable: bool = False
    releaseDate: Optional[datetime] = None
    releaseNotes: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Resposta de health check"""
    status: str = Field(..., description="healthy, degraded, unhealthy")
    checks: Dict[str, bool]
    responseTime: float = Field(..., description="Tempo de resposta em ms")
    timestamp: datetime = Field(default_factory=datetime.now)


# ==================== System Information ====================

@router.get("/info", response_model=DeviceStatus)
async def get_system_information():
    """
    Retorna informações completas do sistema iDFace
    """
    try:
        async with idface_client:
            start_time = datetime.now()
            info = await idface_client.get_system_info()
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Processar informações do sistema
            system_info = SystemInformation(
                deviceId=info.get("device_id"),
                version=info.get("version"),
                model=info.get("model"),
                serialNumber=info.get("serial_number"),
                online=info.get("online", True),
                uptime=info.get("uptime")
            )
            
            # Informações de rede
            network_data = info.get("network", {})
            network = NetworkConfiguration(
                ip=network_data.get("ip", ""),
                gateway=network_data.get("gateway"),
                netmask=network_data.get("netmask"),
                mac=network_data.get("mac"),
                dhcp=network_data.get("dhcp", False)
            )
            
            # Informações de armazenamento
            storage_data = info.get("storage", {})
            if storage_data:
                total = storage_data.get("total", 0)
                used = storage_data.get("used", 0)
                free = total - used if total > 0 else 0
                usage_pct = (used / total * 100) if total > 0 else 0
                
                storage = StorageInformation(
                    totalSpace=total,
                    usedSpace=used,
                    freeSpace=free,
                    usagePercentage=round(usage_pct, 2)
                )
            else:
                storage = None
            
            # Capacidades do dispositivo
            capacity_data = info.get("capacity", {})
            capacity = DeviceCapacity(
                maxUsers=capacity_data.get("max_users"),
                currentUsers=capacity_data.get("current_users"),
                maxFaces=capacity_data.get("max_faces"),
                currentFaces=capacity_data.get("current_faces"),
                maxCards=capacity_data.get("max_cards"),
                currentCards=capacity_data.get("current_cards"),
                maxAccessLogs=capacity_data.get("max_access_logs"),
                currentAccessLogs=capacity_data.get("current_access_logs")
            )
            
            return DeviceStatus(
                connected=True,
                systemInfo=system_info,
                network=network,
                storage=storage,
                capacity=capacity,
                lastCheck=datetime.now()
            )
            
    except Exception as e:
        # Retornar status offline se falhar
        return DeviceStatus(
            connected=False,
            systemInfo=None,
            network=None,
            storage=None,
            capacity=None,
            lastCheck=datetime.now()
        )
        


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Verifica saúde geral do sistema (health check)
    """
    start_time = datetime.now()
    checks = {
        "connection": False,
        "authentication": False,
        "storage": False,
        "network": False
    }
    
    try:
        async with idface_client:
            # Teste de conexão
            checks["connection"] = True
            checks["authentication"] = True
            
            # Obter informações do sistema
            info = await idface_client.get_system_info()
            
            # Verificar armazenamento
            storage = info.get("storage", {})
            if storage:
                usage_pct = (storage.get("used", 0) / storage.get("total", 1)) * 100
                checks["storage"] = usage_pct < 90  # Healthy se menos de 90% usado
            
            # Verificar rede
            network = info.get("network", {})
            checks["network"] = bool(network.get("ip"))
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Determinar status geral
            healthy_checks = sum(checks.values())
            total_checks = len(checks)
            
            if healthy_checks == total_checks:
                status = "healthy"
            elif healthy_checks >= total_checks / 2:
                status = "degraded"
            else:
                status = "unhealthy"
            
            return HealthCheckResponse(
                status=status,
                checks=checks,
                responseTime=response_time
            )
            
    except Exception as e:
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return HealthCheckResponse(
            status="unhealthy",
            checks=checks,
            responseTime=response_time
        )


# ==================== Network Configuration ====================

@router.get("/network")
async def get_network_configuration():
    """
    Retorna configuração de rede do dispositivo
    """
    try:
        async with idface_client:
            info = await idface_client.get_system_info()
            network_data = info.get("network", {})
            
            return NetworkConfiguration(
                ip=network_data.get("ip", ""),
                gateway=network_data.get("gateway"),
                netmask=network_data.get("netmask"),
                mac=network_data.get("mac"),
                dhcp=network_data.get("dhcp", False)
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Erro ao obter configuração de rede: {str(e)}"
        )


# ==================== Time Configuration ====================

@router.get("/time")
async def get_time_configuration():
    """
    Retorna configuração de data/hora do dispositivo
    """
    try:
        async with idface_client:
            info = await idface_client.get_system_info()
            time_data = info.get("time", {})
            
            return TimeConfiguration(
                currentTime=datetime.fromtimestamp(time_data.get("timestamp", datetime.now().timestamp())),
                timezone=time_data.get("timezone"),
                ntpEnabled=time_data.get("ntp_enabled", False),
                ntpServer=time_data.get("ntp_server")
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Erro ao obter configuração de tempo: {str(e)}"
        )


# ==================== Device Actions ====================

class ActionRequest(BaseModel):
    """Requisição para executar ação no dispositivo"""
    action: str = Field(..., description="Tipo de ação: door, sec_box, etc")
    parameters: str = Field(..., description="Parâmetros da ação, ex: 'door=1,timeout=3000'")


class ActionResponse(BaseModel):
    """Resposta de execução de ação"""
    success: bool
    action: str
    message: str
    executedAt: datetime = Field(default_factory=datetime.now)


@router.post("/actions/execute", response_model=ActionResponse)
async def execute_action(request: ActionRequest):
    """
    Executa uma ação genérica no dispositivo.
    Use esta rota para ações que não possuem um atalho específico.
    """
    try:
        async with idface_client:
            action_data = {
                "action": request.action,
                "parameters": request.parameters
            }
            
            result = await idface_client.execute_actions([action_data])
            
            # A API do iDFace retorna uma lista de ações com status
            if result and "actions" in result and result["actions"]:
                action_result = result["actions"][0]
                if action_result.get("status") == "allowed":
                    return ActionResponse(
                        success=True,
                        action=request.action,
                        message=f"Ação '{request.action}' executada com sucesso."
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action=request.action,
                        message=f"Ação '{request.action}' negada pelo dispositivo. Status: {action_result.get('status')}"
                    )
            
            return ActionResponse(
                success=False,
                action=request.action,
                message=f"Resposta inesperada do dispositivo: {result}"
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar ação: {str(e)}"
        )


@router.post("/actions/open-secbox", response_model=ActionResponse)
async def open_secbox(secbox_id: int = 65793, reason: int = 3, timeout: int = 3):
    """
    Aciona um sec_box (relé), geralmente para abrir uma porta.
    - **secbox_id**: ID do sec_box a ser acionado (padrão: 65793).
    - **reason**: Motivo do acionamento (padrão: 3).
    - **timeout**: Duração em segundos para manter o relé acionado (padrão: 3).
                   Use 0 para manter acionado indefinidamente.
    """
    # Constrói a string de parâmetros
    params = f"id={secbox_id},reason={reason}"
    if timeout >= 0:
        # O timeout é em milissegundos
        params += f",timeout={timeout * 1000}"
        
    # Cria a requisição e chama o endpoint genérico
    request = ActionRequest(action="sec_box", parameters=params)
    
    return await execute_action(request)


# ==================== Device Control ====================

@router.post("/reboot")
async def reboot_device(request: RebootRequest):
    """
    Reinicia o dispositivo iDFace
    """
    try:
        async with idface_client:
            await idface_client.reboot()
            
            return {
                "success": True,
                "message": "Dispositivo reiniciando...",
                "delay": request.delay
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao reiniciar dispositivo: {str(e)}"
        )


@router.post("/reset-factory")
async def factory_reset():
    """
    Restaura o dispositivo para configurações de fábrica
    ATENÇÃO: Esta operação apaga TODOS os dados!
    """
    # TODO: Implementar reset de fábrica com confirmação adicional
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Reset de fábrica não implementado por segurança. Implementar com confirmação adicional."
    )


# ==================== Backup & Restore ====================

@router.post("/backup", response_model=BackupResponse)
async def create_backup(request: BackupRequest, db = Depends(get_db)):
    """
    Cria backup das configurações e dados
    """
    try:
        backup_data = {}
        
        # Backup de usuários
        if request.includeUsers:
            users = await db.user.find_many(
                include={
                    "cards": True,
                    "qrcodes": True
                }
            )
            backup_data["users"] = [
                {
                    "name": u.name,
                    "registration": u.registration,
                    "cards": [c.value for c in u.cards],
                    "qrcodes": [q.value for q in u.qrcodes]
                }
                for u in users
            ]
        
        # Backup de regras de acesso
        if request.includeAccessRules:
            rules = await db.accessrule.find_many()
            backup_data["access_rules"] = [
                {
                    "name": r.name,
                    "type": r.type,
                    "priority": r.priority
                }
                for r in rules
            ]
        
        # Backup de time zones
        if request.includeTimeZones:
            zones = await db.timezone.find_many(include={"timeSpans": True})
            backup_data["time_zones"] = [
                {
                    "name": z.name,
                    "timeSpans": [
                        {
                            "start": s.start,
                            "end": s.end,
                            "sun": s.sun,
                            "mon": s.mon,
                            "tue": s.tue,
                            "wed": s.wed,
                            "thu": s.thu,
                            "fri": s.fri,
                            "sat": s.sat
                        }
                        for s in z.timeSpans
                    ] if z.timeSpans else []
                }
                for z in zones
            ]
        
        # Backup de logs
        if request.includeLogs:
            logs = await db.accesslog.find_many()
            backup_data["access_logs"] = [
                {
                    "userId": l.userId,
                    "portalId": l.portalId,
                    "event": l.event,
                    "timestamp": l.timestamp.isoformat()
                }
                for l in logs
            ]
        
        # Serializar e calcular tamanho
        import json
        backup_json = json.dumps(backup_data)
        backup_size = len(backup_json.encode('utf-8'))
        
        return BackupResponse(
            success=True,
            message="Backup criado com sucesso",
            backupSize=backup_size,
            backupUrl=None  # TODO: Gerar URL para download
        )
        
    except Exception as e:
        return BackupResponse(
            success=False,
            message=f"Erro ao criar backup: {str(e)}"
        )


@router.post("/restore")
async def restore_backup(request: RestoreRequest, db = Depends(get_db)):
    """
    Restaura backup de configurações e dados
    """
    try:
        import json
        import base64
        
        # Decodificar backup
        backup_json = base64.b64decode(request.backupData).decode('utf-8')
        backup_data = json.loads(backup_json)
        
        # Limpar dados se solicitado
        if request.clearBefore:
            await db.user.delete_many()
            await db.accessrule.delete_many()
            await db.timezone.delete_many()
        
        # Restaurar usuários
        if "users" in backup_data:
            for user_data in backup_data["users"]:
                user = await db.user.create(
                    data={
                        "name": user_data["name"],
                        "registration": user_data.get("registration")
                    }
                )
                
                # Restaurar cartões
                for card_value in user_data.get("cards", []):
                    await db.card.create(
                        data={
                            "value": card_value,
                            "userId": user.id
                        }
                    )
        
        # Restaurar regras de acesso
        if "access_rules" in backup_data:
            for rule_data in backup_data["access_rules"]:
                await db.accessrule.create(data=rule_data)
        
        # Restaurar time zones
        if "time_zones" in backup_data:
            for tz_data in backup_data["time_zones"]:
                spans = tz_data.pop("timeSpans", [])
                tz = await db.timezone.create(
                    data={"name": tz_data["name"]}
                )
                
                for span_data in spans:
                    span_data["timeZoneId"] = tz.id
                    await db.timespan.create(data=span_data)
        
        return {
            "success": True,
            "message": "Backup restaurado com sucesso"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao restaurar backup: {str(e)}"
        )


# ==================== Firmware & Updates ====================

@router.get("/firmware", response_model=FirmwareInfo)
async def get_firmware_info():
    """
    Retorna informações sobre firmware do dispositivo
    """
    try:
        async with idface_client:
            info = await idface_client.get_system_info()
            
            current_version = info.get("version", "unknown")
            
            return FirmwareInfo(
                currentVersion=current_version,
                latestVersion=None,  # TODO: Verificar versão mais recente
                updateAvailable=False
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Erro ao obter informações de firmware: {str(e)}"
        )


# ==================== Statistics ====================

@router.get("/statistics")
async def get_system_statistics(db = Depends(get_db)):
    """
    Retorna estatísticas gerais do sistema
    """
    try:
        # Estatísticas locais
        total_users = await db.user.count()
        total_rules = await db.accessrule.count()
        total_zones = await db.timezone.count()
        total_logs = await db.accesslog.count()
        
        # Estatísticas do dispositivo
        try:
            async with idface_client:
                device_info = await idface_client.get_system_info()
                capacity = device_info.get("capacity", {})
        except:
            capacity = {}
        
        return {
            "local": {
                "users": total_users,
                "accessRules": total_rules,
                "timeZones": total_zones,
                "accessLogs": total_logs
            },
            "device": {
                "maxUsers": capacity.get("max_users"),
                "currentUsers": capacity.get("current_users"),
                "maxFaces": capacity.get("max_faces"),
                "currentFaces": capacity.get("current_faces"),
                "usagePercentage": round(
                    (capacity.get("current_users", 0) / capacity.get("max_users", 1)) * 100, 2
                ) if capacity.get("max_users") else 0
            },
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter estatísticas: {str(e)}"
        )


# ==================== Diagnostics ====================

@router.get("/diagnostics")
async def run_diagnostics(db = Depends(get_db)):
    """
    Executa diagnóstico completo do sistema
    """
    results = {
        "timestamp": datetime.now(),
        "tests": {}
    }
    
    # Teste 1: Conexão com dispositivo
    try:
        async with idface_client:
            await idface_client.get_system_info()
            results["tests"]["device_connection"] = {
                "status": "pass",
                "message": "Conexão estabelecida com sucesso"
            }
    except Exception as e:
        results["tests"]["device_connection"] = {
            "status": "fail",
            "message": str(e)
        }
    
    # Teste 2: Banco de dados
    try:
        await db.user.count()
        results["tests"]["database"] = {
            "status": "pass",
            "message": "Banco de dados acessível"
        }
    except Exception as e:
        results["tests"]["database"] = {
            "status": "fail",
            "message": str(e)
        }
    
    # Teste 3: Sincronização
    try:
        synced_users = await db.user.count(where={"idFaceId": {"not": None}})
        total_users = await db.user.count()
        sync_percentage = (synced_users / total_users * 100) if total_users > 0 else 100
        
        results["tests"]["synchronization"] = {
            "status": "pass" if sync_percentage > 50 else "warning",
            "message": f"{sync_percentage:.1f}% dos usuários sincronizados",
            "syncedUsers": synced_users,
            "totalUsers": total_users
        }
    except Exception as e:
        results["tests"]["synchronization"] = {
            "status": "fail",
            "message": str(e)
        }
    
    # Resumo geral
    passed = sum(1 for t in results["tests"].values() if t["status"] == "pass")
    total = len(results["tests"])
    
    results["summary"] = {
        "overall": "healthy" if passed == total else "degraded" if passed > 0 else "unhealthy",
        "passed": passed,
        "total": total
    }
    
    return results