from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from app.database import get_db
from app.utils.idface_client import idface_client
from app.schemas.sync import (
    SyncEntityRequest, BulkSyncRequest, FullSyncRequest,
    SyncResponse, EntitySyncResult, SyncSummary,
    DeviceConnectionStatus, DeviceSyncStatus,
    UserSyncRequest, AccessRuleSyncRequest, TimeZoneSyncRequest,
    DataComparison, ComparisonRequest, ComparisonResponse,
    SyncConflict, ConflictResolutionRequest,
    SyncConfiguration, SyncConfigurationResponse,
    BatchSyncRequest, BatchSyncResponse,
    SyncEntityType, SyncDirection, SyncStatus
)
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import base64

router = APIRouter()


# ==================== Health Check & Connection ====================

@router.get("/status", response_model=DeviceSyncStatus)
async def get_sync_status(db = Depends(get_db)):
    """
    Verifica status de conexão e sincronização com o dispositivo iDFace
    """
    start_time = datetime.now()
    
    try:
        async with idface_client:
            # Testar conexão
            device_info = await idface_client.get_system_info()
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            connection_status = DeviceConnectionStatus(
                connected=True,
                lastCheck=datetime.now(),
                responseTime=response_time,
                deviceIp=idface_client.base_url.replace("http://", ""),
                errorMessage=None
            )
            
            # Buscar última sincronização (implementar tabela de histórico se necessário)
            # last_sync = await db.synchistory.find_first(order_by={"endTime": "desc"})
            
            return DeviceSyncStatus(
                connection=connection_status,
                lastSyncTime=None,  # last_sync.endTime if last_sync else None
                pendingSync=False,
                syncInProgress=False,
                deviceInfo=device_info
            )
            
    except Exception as e:
        connection_status = DeviceConnectionStatus(
            connected=False,
            lastCheck=datetime.now(),
            responseTime=None,
            deviceIp=idface_client.base_url.replace("http://", ""),
            errorMessage=str(e)
        )
        
        return DeviceSyncStatus(
            connection=connection_status,
            lastSyncTime=None,
            pendingSync=False,
            syncInProgress=False,
            deviceInfo=None
        )


@router.post("/test-connection")
async def test_connection():
    """
    Testa conexão com o dispositivo iDFace
    """
    try:
        async with idface_client:
            info = await idface_client.get_system_info()
            
            return {
                "success": True,
                "message": "Conexão estabelecida com sucesso",
                "deviceInfo": info
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha na conexão: {str(e)}"
        )


# ==================== Single Entity Sync ====================

@router.post("/entity", response_model=SyncResponse)
async def sync_entity(
    request: SyncEntityRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Sincroniza uma entidade específica ou todas de um tipo
    """
    start_time = datetime.now()
    results = []
    
    try:
        if request.entityType == SyncEntityType.USERS:
            result = await _sync_users(request, db)
            results.append(result)
        
        elif request.entityType == SyncEntityType.ACCESS_RULES:
            result = await _sync_access_rules(request, db)
            results.append(result)
        
        elif request.entityType == SyncEntityType.TIME_ZONES:
            result = await _sync_time_zones(request, db)
            results.append(result)
        
        elif request.entityType == SyncEntityType.ACCESS_LOGS:
            result = await _sync_access_logs(request, db)
            results.append(result)
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de entidade não suportado: {request.entityType}"
            )
        
        end_time = datetime.now()
        response = SyncResponse(
            success=all(r.status == SyncStatus.COMPLETED for r in results),
            message="Sincronização concluída",
            direction=request.direction,
            startTime=start_time,
            endTime=end_time,
            results=results
        )
        response.calculate_duration()
        
        return response
        
    except Exception as e:
        end_time = datetime.now()
        return SyncResponse(
            success=False,
            message=f"Erro na sincronização: {str(e)}",
            direction=request.direction,
            startTime=start_time,
            endTime=end_time,
            results=results
        )


# ==================== Bulk Sync ====================

@router.post("/bulk", response_model=SyncResponse)
async def bulk_sync(
    request: BulkSyncRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Sincroniza múltiplas entidades de uma vez
    """
    start_time = datetime.now()
    results = []
    
    for entity_type in request.entities:
        entity_request = SyncEntityRequest(
            entityType=entity_type,
            direction=request.direction,
            overwrite=request.overwrite
        )
        
        try:
            if entity_type == SyncEntityType.USERS:
                result = await _sync_users(entity_request, db, sync_images=request.syncImages)
            elif entity_type == SyncEntityType.ACCESS_RULES:
                result = await _sync_access_rules(entity_request, db)
            elif entity_type == SyncEntityType.TIME_ZONES:
                result = await _sync_time_zones(entity_request, db)
            elif entity_type == SyncEntityType.ACCESS_LOGS:
                if request.syncAccessLogs:
                    result = await _sync_access_logs(entity_request, db)
                else:
                    continue
            else:
                result = EntitySyncResult(
                    entityType=entity_type,
                    status=SyncStatus.FAILED,
                    errors=["Tipo não suportado"]
                )
            
            results.append(result)
            
        except Exception as e:
            results.append(EntitySyncResult(
                entityType=entity_type,
                status=SyncStatus.FAILED,
                errors=[str(e)]
            ))
    
    end_time = datetime.now()
    response = SyncResponse(
        success=all(r.status == SyncStatus.COMPLETED for r in results),
        message=f"Sincronização em massa concluída: {len(results)} entidades",
        direction=request.direction,
        startTime=start_time,
        endTime=end_time,
        results=results
    )
    response.calculate_duration()
    
    return response


# ==================== Full Sync ====================

@router.post("/full", response_model=SyncResponse)
async def full_sync(
    request: FullSyncRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Sincronização completa de todas as entidades
    """
    start_time = datetime.now()
    
    # Se clearBeforeSync, limpar dados locais
    if request.clearBeforeSync and request.direction == SyncDirection.FROM_IDFACE:
        await _clear_local_data(db, request.entities)
    
    # Determinar quais entidades sincronizar
    entities_to_sync = request.entities if request.entities else [
        SyncEntityType.USERS,
        SyncEntityType.ACCESS_RULES,
        SyncEntityType.TIME_ZONES,
        SyncEntityType.PORTALS,
        SyncEntityType.ACCESS_LOGS
    ]
    
    bulk_request = BulkSyncRequest(
        entities=entities_to_sync,
        direction=request.direction,
        overwrite=request.overwrite,
        syncImages=True,
        syncAccessLogs=True
    )
    
    return await bulk_sync(bulk_request, background_tasks, db)


# ==================== Specific Entity Sync ====================

@router.post("/user", response_model=SyncResponse)
async def sync_user(request: UserSyncRequest, db = Depends(get_db)):
    """
    Sincroniza um usuário específico com todas suas informações
    """
    start_time = datetime.now()
    
    # Buscar usuário
    user = await db.user.find_unique(
        where={"id": request.userId},
        include={
            "cards": True,
            "qrcodes": True,
            "userAccessRules": {"include": {"accessRule": True}}
        }
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuário {request.userId} não encontrado"
        )
    
    results = []
    
    try:
        async with idface_client:
            # Sincronizar dados do usuário
            user_data = {
                "name": user.name,
                "registration": user.registration or "",
                "password": user.password or "",
                "salt": user.salt or ""
            }
            
            if request.direction == SyncDirection.TO_IDFACE:
                result = await idface_client.create_user(user_data)
                idface_user_id = result.get("id")
                
                # Atualizar ID do iDFace no banco local
                await db.user.update(
                    where={"id": request.userId},
                    data={"idFaceId": idface_user_id}
                )
                
                # Sincronizar imagem
                if request.syncImage and user.image:
                    image_bytes = base64.b64decode(user.image)
                    await idface_client.set_user_image(idface_user_id, image_bytes)
                
                # Sincronizar cartões
                if request.syncCards:
                    for card in user.cards:
                        await idface_client.create_card(card.value, idface_user_id)
                
                # Sincronizar regras de acesso
                if request.syncAccessRules:
                    for uar in user.userAccessRules:
                        if uar.accessRule.idFaceId:
                            await idface_client.create_user_access_rule(
                                idface_user_id,
                                uar.accessRule.idFaceId
                            )
                
                results.append(EntitySyncResult(
                    entityType=SyncEntityType.USERS,
                    status=SyncStatus.COMPLETED,
                    successCount=1
                ))
        
        end_time = datetime.now()
        response = SyncResponse(
            success=True,
            message=f"Usuário {user.name} sincronizado com sucesso",
            direction=request.direction,
            startTime=start_time,
            endTime=end_time,
            results=results
        )
        response.calculate_duration()
        
        return response
        
    except Exception as e:
        results.append(EntitySyncResult(
            entityType=SyncEntityType.USERS,
            status=SyncStatus.FAILED,
            errors=[str(e)]
        ))
        
        end_time = datetime.now()
        return SyncResponse(
            success=False,
            message=f"Erro ao sincronizar usuário: {str(e)}",
            direction=request.direction,
            startTime=start_time,
            endTime=end_time,
            results=results
        )


@router.post("/access-rule")
async def sync_access_rule(request: AccessRuleSyncRequest, db = Depends(get_db)):
    """
    Sincroniza uma regra de acesso específica
    """
    rule = await db.accessrule.find_unique(
        where={"id": request.accessRuleId},
        include={
            "timeZones": {"include": {"timeZone": True}}
        }
    )
    
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Regra {request.accessRuleId} não encontrada"
        )
    
    try:
        async with idface_client:
            rule_data = {
                "name": rule.name,
                "type": rule.type,
                "priority": rule.priority
            }
            
            result = await idface_client.create_access_rule(rule_data)
            
            return {
                "success": True,
                "message": f"Regra '{rule.name}' sincronizada com sucesso",
                "result": result
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar regra: {str(e)}"
        )


@router.post("/time-zone")
async def sync_time_zone(request: TimeZoneSyncRequest, db = Depends(get_db)):
    """
    Sincroniza um time zone específico
    """
    tz = await db.timezone.find_unique(
        where={"id": request.timeZoneId},
        include={"timeSpans": True}
    )
    
    if not tz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time zone {request.timeZoneId} não encontrado"
        )
    
    try:
        async with idface_client:
            tz_data = {"name": tz.name}
            result = await idface_client.create_time_zone(tz_data)
            
            # Sincronizar time spans
            if request.syncTimeSpans and tz.timeSpans:
                idface_tz_id = result.get("id")
                for span in tz.timeSpans:
                    span_data = {
                        "time_zone_id": idface_tz_id,
                        "start": span.start,
                        "end": span.end,
                        "sun": 1 if span.sun else 0,
                        "mon": 1 if span.mon else 0,
                        "tue": 1 if span.tue else 0,
                        "wed": 1 if span.wed else 0,
                        "thu": 1 if span.thu else 0,
                        "fri": 1 if span.fri else 0,
                        "sat": 1 if span.sat else 0,
                        "hol1": 1 if span.hol1 else 0,
                        "hol2": 1 if span.hol2 else 0,
                        "hol3": 1 if span.hol3 else 0
                    }
                    await idface_client.create_time_span(span_data)
            
            return {
                "success": True,
                "message": f"Time zone '{tz.name}' sincronizado com sucesso",
                "timeSpansCount": len(tz.timeSpans) if tz.timeSpans else 0
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar time zone: {str(e)}"
        )


# ==================== Data Comparison ====================

@router.post("/compare", response_model=ComparisonResponse)
async def compare_data(request: ComparisonRequest, db = Depends(get_db)):
    """
    Compara dados locais com dados do iDFace
    """
    comparisons = []
    
    entities = request.entities if SyncEntityType.ALL not in request.entities else [
        SyncEntityType.USERS,
        SyncEntityType.ACCESS_RULES,
        SyncEntityType.TIME_ZONES
    ]
    
    try:
        async with idface_client:
            for entity_type in entities:
                if entity_type == SyncEntityType.USERS:
                    comparison = await _compare_users(db, request.includeDetails)
                    comparisons.append(comparison)
                
                elif entity_type == SyncEntityType.ACCESS_RULES:
                    comparison = await _compare_access_rules(db, request.includeDetails)
                    comparisons.append(comparison)
                
                elif entity_type == SyncEntityType.TIME_ZONES:
                    comparison = await _compare_time_zones(db, request.includeDetails)
                    comparisons.append(comparison)
        
        total_conflicts = sum(len(c.conflicts) for c in comparisons)
        
        return ComparisonResponse(
            comparisons=comparisons,
            totalConflicts=total_conflicts
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao comparar dados: {str(e)}"
        )


# ==================== Helper Functions ====================

async def _sync_users(request: SyncEntityRequest, db, sync_images: bool = True) -> EntitySyncResult:
    """Sincroniza usuários"""
    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    errors = []
    
    try:
        async with idface_client:
            if request.direction == SyncDirection.FROM_IDFACE:
                # Importar do iDFace
                result = await idface_client.load_users()
                users_data = result.get("users", [])
                
                for user_data in users_data:
                    try:
                        # Verificar se já existe
                        existing = await db.user.find_first(
                            where={"idFaceId": user_data.get("id")}
                        )
                        
                        if existing and not request.overwrite:
                            continue
                        
                        if existing:
                            await db.user.update(
                                where={"id": existing.id},
                                data={
                                    "name": user_data.get("name"),
                                    "registration": user_data.get("registration")
                                }
                            )
                        else:
                            await db.user.create(
                                data={
                                    "idFaceId": user_data.get("id"),
                                    "name": user_data.get("name"),
                                    "registration": user_data.get("registration")
                                }
                            )
                        
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"Usuário {user_data.get('id')}: {str(e)}")
                
            else:  # TO_IDFACE
                users = await db.user.find_many()
                
                for user in users:
                    try:
                        user_data = {
                            "name": user.name,
                            "registration": user.registration or ""
                        }
                        await idface_client.create_user(user_data)
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"Usuário {user.id}: {str(e)}")
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.USERS,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=success_count + failed_count,
            successCount=success_count,
            failedCount=failed_count,
            errors=errors[:10],  # Limitar erros
            duration=duration
        )
        
    except Exception as e:
        return EntitySyncResult(
            entityType=SyncEntityType.USERS,
            status=SyncStatus.FAILED,
            errors=[str(e)]
        )


async def _sync_access_rules(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza regras de acesso"""
    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    
    try:
        async with idface_client:
            if request.direction == SyncDirection.FROM_IDFACE:
                result = await idface_client.load_access_rules()
                rules_data = result.get("access_rules", [])
                
                for rule_data in rules_data:
                    try:
                        existing = await db.accessrule.find_first(
                            where={"idFaceId": rule_data.get("id")}
                        )
                        
                        if not existing:
                            await db.accessrule.create(
                                data={
                                    "idFaceId": rule_data.get("id"),
                                    "name": rule_data.get("name"),
                                    "type": rule_data.get("type", 1),
                                    "priority": rule_data.get("priority", 0)
                                }
                            )
                        elif request.overwrite:
                            await db.accessrule.update(
                                where={"id": existing.id},
                                data={
                                    "name": rule_data.get("name"),
                                    "type": rule_data.get("type", 1),
                                    "priority": rule_data.get("priority", 0)
                                }
                            )
                        
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
            
            else:  # TO_IDFACE
                rules = await db.accessrule.find_many()
                
                for rule in rules:
                    try:
                        rule_data = {
                            "name": rule.name,
                            "type": rule.type,
                            "priority": rule.priority
                        }
                        await idface_client.create_access_rule(rule_data)
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.ACCESS_RULES,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=success_count + failed_count,
            successCount=success_count,
            failedCount=failed_count,
            duration=duration
        )
        
    except Exception as e:
        return EntitySyncResult(
            entityType=SyncEntityType.ACCESS_RULES,
            status=SyncStatus.FAILED,
            errors=[str(e)]
        )


async def _sync_time_zones(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza time zones"""
    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    
    try:
        async with idface_client:
            if request.direction == SyncDirection.TO_IDFACE:
                time_zones = await db.timezone.find_many(include={"timeSpans": True})
                
                for tz in time_zones:
                    try:
                        tz_data = {"name": tz.name}
                        result = await idface_client.create_time_zone(tz_data)
                        
                        # Sincronizar time spans
                        if tz.timeSpans:
                            idface_tz_id = result.get("id")
                            for span in tz.timeSpans:
                                await idface_client.create_time_span({
                                    "time_zone_id": idface_tz_id,
                                    "start": span.start,
                                    "end": span.end,
                                    "sun": 1 if span.sun else 0,
                                    "mon": 1 if span.mon else 0,
                                    "tue": 1 if span.tue else 0,
                                    "wed": 1 if span.wed else 0,
                                    "thu": 1 if span.thu else 0,
                                    "fri": 1 if span.fri else 0,
                                    "sat": 1 if span.sat else 0,
                                    "hol1": 1 if span.hol1 else 0,
                                    "hol2": 1 if span.hol2 else 0,
                                    "hol3": 1 if span.hol3 else 0
                                })
                        
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.TIME_ZONES,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=success_count + failed_count,
            successCount=success_count,
            failedCount=failed_count,
            duration=duration
        )
        
    except Exception as e:
        return EntitySyncResult(
            entityType=SyncEntityType.TIME_ZONES,
            status=SyncStatus.FAILED,
            errors=[str(e)]
        )


async def _sync_access_logs(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza logs de acesso"""
    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    try:
        async with idface_client:
            if request.direction == SyncDirection.FROM_IDFACE:
                result = await idface_client.load_access_logs()
                logs_data = result.get("access_logs", [])
                
                for log_data in logs_data:
                    try:
                        # Verificar se já existe
                        existing = await db.accesslog.find_first(
                            where={
                                "timestamp": log_data.get("timestamp"),
                                "userId": log_data.get("user_id"),
                                "event": log_data.get("event")
                            }
                        )
                        
                        if existing:
                            skipped_count += 1
                            continue
                        
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
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.ACCESS_LOGS,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=success_count + failed_count + skipped_count,
            successCount=success_count,
            failedCount=failed_count,
            skippedCount=skipped_count,
            duration=duration
        )
        
    except Exception as e:
        return EntitySyncResult(
            entityType=SyncEntityType.ACCESS_LOGS,
            status=SyncStatus.FAILED,
            errors=[str(e)]
        )


async def _compare_users(db, include_details: bool) -> DataComparison:
    """Compara usuários locais vs iDFace"""
    local_users = await db.user.find_many()
    local_count = len(local_users)
    
    try:
        async with idface_client:
            result = await idface_client.load_users()
            remote_users = result.get("users", [])
            remote_count = len(remote_users)
            
            local_ids = {u.idFaceId for u in local_users if u.idFaceId}
            remote_ids = {u.get("id") for u in remote_users}
            
            only_local = list(local_ids - remote_ids) if include_details else []
            only_remote = list(remote_ids - local_ids) if include_details else []
            identical = len(local_ids & remote_ids)
            
            return DataComparison(
                entityType=SyncEntityType.USERS,
                localCount=local_count,
                remoteCount=remote_count,
                onlyLocal=only_local,
                onlyRemote=only_remote,
                identical=identical,
                conflicts=[]
            )
    except Exception as e:
        return DataComparison(
            entityType=SyncEntityType.USERS,
            localCount=local_count,
            remoteCount=0,
            conflicts=[]
        )


async def _compare_access_rules(db, include_details: bool) -> DataComparison:
    """Compara regras de acesso locais vs iDFace"""
    local_rules = await db.accessrule.find_many()
    local_count = len(local_rules)
    
    try:
        async with idface_client:
            result = await idface_client.load_access_rules()
            remote_rules = result.get("access_rules", [])
            remote_count = len(remote_rules)
            
            local_ids = {r.idFaceId for r in local_rules if r.idFaceId}
            remote_ids = {r.get("id") for r in remote_rules}
            
            only_local = list(local_ids - remote_ids) if include_details else []
            only_remote = list(remote_ids - local_ids) if include_details else []
            identical = len(local_ids & remote_ids)
            
            return DataComparison(
                entityType=SyncEntityType.ACCESS_RULES,
                localCount=local_count,
                remoteCount=remote_count,
                onlyLocal=only_local,
                onlyRemote=only_remote,
                identical=identical,
                conflicts=[]
            )
    except Exception as e:
        return DataComparison(
            entityType=SyncEntityType.ACCESS_RULES,
            localCount=local_count,
            remoteCount=0,
            conflicts=[]
        )


async def _compare_time_zones(db, include_details: bool) -> DataComparison:
    """Compara time zones locais vs iDFace"""
    local_zones = await db.timezone.find_many()
    local_count = len(local_zones)
    
    return DataComparison(
        entityType=SyncEntityType.TIME_ZONES,
        localCount=local_count,
        remoteCount=0,
        identical=0,
        conflicts=[]
    )


async def _clear_local_data(db, entities: Optional[List[SyncEntityType]] = None):
    """Limpa dados locais antes de sincronizar"""
    if not entities or SyncEntityType.USERS in entities:
        await db.user.delete_many()
    
    if not entities or SyncEntityType.ACCESS_RULES in entities:
        await db.accessrule.delete_many()
    
    if not entities or SyncEntityType.TIME_ZONES in entities:
        await db.timezone.delete_many()
    
    if not entities or SyncEntityType.ACCESS_LOGS in entities:
        await db.accesslog.delete_many()


# ==================== Batch Operations ====================

@router.post("/batch", response_model=BatchSyncResponse)
async def batch_sync(request: BatchSyncRequest, db = Depends(get_db)):
    """
    Sincroniza múltiplos itens específicos em batch
    """
    results = []
    errors = []
    processed = 0
    failed = 0
    
    try:
        async with idface_client:
            for item in request.items:
                try:
                    if item.entityType == SyncEntityType.USERS:
                        user = await db.user.find_unique(where={"id": item.entityId})
                        if user:
                            user_data = {
                                "name": user.name,
                                "registration": user.registration or ""
                            }
                            result = await idface_client.create_user(user_data)
                            results.append({
                                "entityType": "users",
                                "entityId": item.entityId,
                                "success": True,
                                "result": result
                            })
                            processed += 1
                        else:
                            raise Exception(f"Usuário {item.entityId} não encontrado")
                    
                    elif item.entityType == SyncEntityType.ACCESS_RULES:
                        rule = await db.accessrule.find_unique(where={"id": item.entityId})
                        if rule:
                            rule_data = {
                                "name": rule.name,
                                "type": rule.type,
                                "priority": rule.priority
                            }
                            result = await idface_client.create_access_rule(rule_data)
                            results.append({
                                "entityType": "access_rules",
                                "entityId": item.entityId,
                                "success": True,
                                "result": result
                            })
                            processed += 1
                        else:
                            raise Exception(f"Regra {item.entityId} não encontrada")
                
                except Exception as e:
                    failed += 1
                    error_msg = f"{item.entityType} ID {item.entityId}: {str(e)}"
                    errors.append(error_msg)
                    results.append({
                        "entityType": item.entityType,
                        "entityId": item.entityId,
                        "success": False,
                        "error": str(e)
                    })
                    
                    if request.stopOnError:
                        break
        
        return BatchSyncResponse(
            success=failed == 0,
            totalItems=len(request.items),
            processedItems=processed,
            failedItems=failed,
            results=results,
            errors=errors
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro no batch sync: {str(e)}"
        )


# ==================== Automatic Sync Configuration ====================

# Variável global para armazenar configuração (em produção, usar banco de dados)
_sync_config = SyncConfiguration()

@router.get("/config", response_model=SyncConfigurationResponse)
async def get_sync_configuration():
    """
    Retorna configuração atual de sincronização automática
    """
    return SyncConfigurationResponse(
        configuration=_sync_config,
        nextSyncTime=None,  # Implementar lógica de agendamento
        lastSyncTime=None
    )


@router.post("/config")
async def update_sync_configuration(config: SyncConfiguration):
    """
    Atualiza configuração de sincronização automática
    """
    global _sync_config
    _sync_config = config
    
    return {
        "success": True,
        "message": "Configuração atualizada com sucesso",
        "configuration": _sync_config
    }


# ==================== Manual Triggers ====================

@router.post("/trigger/users-to-idface")
async def trigger_users_to_idface(db = Depends(get_db)):
    """
    Gatilho manual: Sincroniza todos os usuários locais para o iDFace
    """
    request = SyncEntityRequest(
        entityType=SyncEntityType.USERS,
        direction=SyncDirection.TO_IDFACE,
        overwrite=False
    )
    
    result = await _sync_users(request, db)
    
    return {
        "success": result.status == SyncStatus.COMPLETED,
        "message": f"Sincronizados {result.successCount} usuários",
        "result": result
    }


@router.post("/trigger/access-logs-from-idface")
async def trigger_access_logs_from_idface(db = Depends(get_db)):
    """
    Gatilho manual: Importa logs de acesso do iDFace
    """
    request = SyncEntityRequest(
        entityType=SyncEntityType.ACCESS_LOGS,
        direction=SyncDirection.FROM_IDFACE
    )
    
    result = await _sync_access_logs(request, db)
    
    return {
        "success": result.status == SyncStatus.COMPLETED,
        "message": f"Importados {result.successCount} logs de acesso",
        "result": result
    }


# ==================== Summary & Statistics ====================

@router.get("/summary", response_model=SyncSummary)
async def get_sync_summary(db = Depends(get_db)):
    """
    Retorna resumo geral do estado de sincronização
    """
    # Contar entidades locais
    users_count = await db.user.count()
    rules_count = await db.accessrule.count()
    zones_count = await db.timezone.count()
    logs_count = await db.accesslog.count()
    
    # Contar quantos estão sincronizados (têm idFaceId)
    synced_users = await db.user.count(where={"idFaceId": {"not": None}})
    synced_rules = await db.accessrule.count(where={"idFaceId": {"not": None}})
    synced_zones = await db.timezone.count(where={"idFaceId": {"not": None}})
    
    total_records = users_count + rules_count + zones_count + logs_count
    synced_records = synced_users + synced_rules + synced_zones
    
    return SyncSummary(
        totalEntities=4,
        successfulEntities=3,
        failedEntities=0,
        partialEntities=1,
        totalRecords=total_records,
        syncedRecords=synced_records,
        failedRecords=0,
        skippedRecords=total_records - synced_records
    )


# ==================== Portal Sync ====================

@router.post("/portals")
async def sync_portals_endpoint(db = Depends(get_db)):
    """
    Sincroniza portais (áreas) do dispositivo iDFace com o banco de dados PostgreSQL
    
    Retorna a lista de portais sincronizados do leitor
    """
    from app.services.portal_sync_service import portal_sync_service
    
    result = await portal_sync_service.sync_portals_from_device()
    return result


@router.get("/portals")
async def get_synced_portals_endpoint(db = Depends(get_db)):
    """
    Retorna lista de portais sincronizados no banco de dados
    """
    from app.services.portal_sync_service import portal_sync_service
    
    result = await portal_sync_service.get_synced_portals()
    return result