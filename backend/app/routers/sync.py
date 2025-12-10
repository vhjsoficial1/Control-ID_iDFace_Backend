from fastapi import APIRouter, HTTPException, Depends, status, BackgroundTasks
from app.database import get_db
# Importando ambos os clientes para a fila indiana
from app.utils.idface_client import idface_client, idface_client_2
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
    Verifica status de conexão.
    NOTA: Verifica primariamente o Leitor 1 para informações detalhadas,
    mas tenta garantir que o sistema está operante.
    """
    start_time = datetime.now()
    
    try:
        # Verifica Leitor 1 (Principal)
        async with idface_client:
            device_info = await idface_client.get_system_info()
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            connection_status = DeviceConnectionStatus(
                connected=True,
                lastCheck=datetime.now(),
                responseTime=response_time,
                deviceIp=idface_client.base_url.replace("http://", ""),
                errorMessage=None
            )
            
            return DeviceSyncStatus(
                connection=connection_status,
                lastSyncTime=None, 
                pendingSync=False,
                syncInProgress=False,
                deviceInfo=device_info
            )
            
    except Exception as e:
        # Se L1 falhar, tentamos reportar erro
        connection_status = DeviceConnectionStatus(
            connected=False,
            lastCheck=datetime.now(),
            responseTime=None,
            deviceIp=idface_client.base_url.replace("http://", ""),
            errorMessage=f"Leitor 1 falhou: {str(e)}"
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
    Testa conexão com ambos os leitores
    """
    results = {}
    
    # Teste Leitor 1
    try:
        async with idface_client:
            info1 = await idface_client.get_system_info()
            results["leitor_1"] = {"success": True, "info": info1}
    except Exception as e:
        results["leitor_1"] = {"success": False, "error": str(e)}

    # Teste Leitor 2
    try:
        async with idface_client_2:
            info2 = await idface_client_2.get_system_info()
            results["leitor_2"] = {"success": True, "info": info2}
    except Exception as e:
        results["leitor_2"] = {"success": False, "error": str(e)}

    success_overall = results["leitor_1"]["success"] # Consideramos sucesso se pelo menos o principal responder ou ambos?
    
    return {
        "success": success_overall,
        "message": "Teste de conexão finalizado",
        "details": results
    }


# ==================== Single Entity Sync ====================

@router.post("/entity", response_model=SyncResponse)
async def sync_entity(
    request: SyncEntityRequest,
    background_tasks: BackgroundTasks,
    db = Depends(get_db)
):
    """
    Sincroniza uma entidade específica ou todas de um tipo (Sequencialmente nos dois leitores)
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
    Sincroniza múltiplas entidades de uma vez (Sequencialmente)
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
    Sincroniza um usuário específico para AMBOS os leitores sequencialmente.
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
        raise HTTPException(status_code=404, detail=f"Usuário {request.userId} não encontrado")
    
    results = []
    
    user_data = {
        "name": user.name,
        "registration": user.registration or "",
        "password": user.password or "",
        "salt": user.salt or ""
    }

    async def _process_single_user_sync(client, device_name):
        try:
            async with client:
                if request.direction == SyncDirection.TO_IDFACE:
                    result = await client.create_user(user_data)
                    idface_user_id = result.get("id")
                    
                    # Atualizar ID do iDFace no banco local (apenas do L1 para manter referência principal)
                    if client == idface_client:
                        await db.user.update(
                            where={"id": request.userId},
                            data={"idFaceId": idface_user_id}
                        )
                    
                    # Sincronizar imagem
                    if request.syncImage and user.image:
                        image_bytes = base64.b64decode(user.image)
                        await client.set_user_image(idface_user_id, image_bytes)
                    
                    # Sincronizar cartões
                    if request.syncCards:
                        for card in user.cards:
                            await client.create_card(card.value, idface_user_id)
                    
                    # Sincronizar regras de acesso
                    if request.syncAccessRules:
                        for uar in user.userAccessRules:
                            if uar.accessRule.idFaceId:
                                await client.create_user_access_rule(
                                    idface_user_id,
                                    uar.accessRule.idFaceId
                                )
                    return True, None
                return True, None
        except Exception as e:
            return False, f"Erro {device_name}: {str(e)}"

    # 1. Leitor 1
    success1, error1 = await _process_single_user_sync(idface_client, "Leitor 1")
    
    # 2. Leitor 2
    success2, error2 = await _process_single_user_sync(idface_client_2, "Leitor 2")

    # Consolidar resultados
    status_final = SyncStatus.COMPLETED if (success1 and success2) else SyncStatus.FAILED
    if success1 and not success2: status_final = SyncStatus.PARTIAL
    if not success1 and success2: status_final = SyncStatus.PARTIAL # Raro

    results.append(EntitySyncResult(
        entityType=SyncEntityType.USERS,
        status=status_final,
        successCount=1 if status_final == SyncStatus.COMPLETED else 0,
        errors=[e for e in [error1, error2] if e]
    ))

    end_time = datetime.now()
    return SyncResponse(
        success=status_final == SyncStatus.COMPLETED,
        message=f"Sincronização de usuário finalizada (L1: {'OK' if success1 else 'Erro'}, L2: {'OK' if success2 else 'Erro'})",
        direction=request.direction,
        startTime=start_time,
        endTime=end_time,
        results=results
    )


@router.post("/access-rule")
async def sync_access_rule(request: AccessRuleSyncRequest, db = Depends(get_db)):
    """
    Sincroniza uma regra de acesso específica para AMBOS os leitores
    """
    rule = await db.accessrule.find_unique(
        where={"id": request.accessRuleId},
        include={
            "timeZones": {"include": {"timeZone": True}}
        }
    )
    
    if not rule:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    
    rule_data = {
        "name": rule.name,
        "type": rule.type,
        "priority": rule.priority
    }
    
    results_detail = {}

    try:
        # Leitor 1
        try:
            async with idface_client:
                res1 = await idface_client.create_access_rule(rule_data)
                results_detail["leitor_1"] = "OK"
        except Exception as e:
            results_detail["leitor_1"] = f"Erro: {e}"

        # Leitor 2
        try:
            async with idface_client_2:
                res2 = await idface_client_2.create_access_rule(rule_data)
                results_detail["leitor_2"] = "OK"
        except Exception as e:
            results_detail["leitor_2"] = f"Erro: {e}"

        return {
            "success": True,
            "message": f"Regra '{rule.name}' processada",
            "details": results_detail
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro crítico: {str(e)}")


@router.post("/time-zone")
async def sync_time_zone(request: TimeZoneSyncRequest, db = Depends(get_db)):
    """
    Sincroniza um time zone específico para AMBOS os leitores
    """
    tz = await db.timezone.find_unique(
        where={"id": request.timeZoneId},
        include={"timeSpans": True}
    )
    
    if not tz:
        raise HTTPException(status_code=404, detail="Time zone não encontrado")
    
    tz_data = {"name": tz.name}
    
    async def _send_tz(client):
        result = await client.create_time_zone(tz_data)
        if request.syncTimeSpans and tz.timeSpans:
            idface_tz_id = result.get("id")
            for span in tz.timeSpans:
                span_data = {
                    "time_zone_id": idface_tz_id,
                    "start": span.start, "end": span.end,
                    "sun": 1 if span.sun else 0, "mon": 1 if span.mon else 0,
                    "tue": 1 if span.tue else 0, "wed": 1 if span.wed else 0,
                    "thu": 1 if span.thu else 0, "fri": 1 if span.fri else 0,
                    "sat": 1 if span.sat else 0,
                    "hol1": 1 if span.hol1 else 0, "hol2": 1 if span.hol2 else 0, "hol3": 1 if span.hol3 else 0
                }
                await client.create_time_span(span_data)

    results_detail = {}
    
    # Leitor 1
    try:
        async with idface_client:
            await _send_tz(idface_client)
            results_detail["leitor_1"] = "OK"
    except Exception as e:
        results_detail["leitor_1"] = str(e)

    # Leitor 2
    try:
        async with idface_client_2:
            await _send_tz(idface_client_2)
            results_detail["leitor_2"] = "OK"
    except Exception as e:
        results_detail["leitor_2"] = str(e)

    return {
        "success": True,
        "message": f"Time zone '{tz.name}' processado",
        "details": results_detail
    }


# ==================== Data Comparison ====================

@router.post("/compare", response_model=ComparisonResponse)
async def compare_data(request: ComparisonRequest, db = Depends(get_db)):
    """
    Compara dados locais com dados do iDFace (Leitor 1 como referência)
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


# ==================== Helper Functions (Internal Sync Logic) ====================

async def _sync_users(request: SyncEntityRequest, db, sync_images: bool = True) -> EntitySyncResult:
    """Sincroniza usuários sequencialmente (L1 depois L2)"""
    start_time = datetime.now()
    success_count = 0
    failed_count = 0
    errors = []
    
    # === FROM IDFACE (Importar) ===
    if request.direction == SyncDirection.FROM_IDFACE:
        # Importar do L1
        try:
            async with idface_client:
                result = await idface_client.load_users()
                users_data = result.get("users", [])
                for user_data in users_data:
                    # Lógica de salvar no DB local
                    await _save_imported_user(db, user_data)
                success_count += len(users_data)
        except Exception as e:
            failed_count += 1
            errors.append(f"Erro importação L1: {e}")

        # Importar do L2 (apenas para garantir completude, não duplica se idFaceId bater)
        try:
            async with idface_client_2:
                result = await idface_client_2.load_users()
                users_data = result.get("users", [])
                for user_data in users_data:
                    await _save_imported_user(db, user_data)
        except Exception as e:
            errors.append(f"Erro importação L2: {e}")

    # === TO IDFACE (Exportar) ===
    else: 
        users = await db.user.find_many()
        
        # Enviar para L1
        try:
            async with idface_client:
                for user in users:
                    try:
                        user_data = {"name": user.name, "registration": user.registration or ""}
                        await idface_client.create_user(user_data)
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"L1 User {user.id}: {e}")
        except Exception as e:
            errors.append(f"Falha conexão L1: {e}")

        # Enviar para L2
        try:
            async with idface_client_2:
                for user in users:
                    try:
                        user_data = {"name": user.name, "registration": user.registration or ""}
                        await idface_client_2.create_user(user_data)
                    except Exception as e:
                        errors.append(f"L2 User {user.id}: {e}")
        except Exception as e:
            errors.append(f"Falha conexão L2: {e}")

    duration = (datetime.now() - start_time).total_seconds()
    
    return EntitySyncResult(
        entityType=SyncEntityType.USERS,
        status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
        totalCount=success_count + failed_count,
        successCount=success_count,
        failedCount=failed_count,
        errors=errors[:10],
        duration=duration
    )

async def _save_imported_user(db, user_data):
    """Auxiliar para salvar usuário importado"""
    existing = await db.user.find_first(where={"idFaceId": user_data.get("id")})
    if existing:
        await db.user.update(
            where={"id": existing.id},
            data={"name": user_data.get("name"), "registration": user_data.get("registration")}
        )
    else:
        await db.user.create(
            data={"idFaceId": user_data.get("id"), "name": user_data.get("name"), "registration": user_data.get("registration")}
        )

async def _sync_access_rules(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza regras de acesso sequencialmente"""
    start_time = datetime.now()
    errors = []
    success_count = 0
    
    # Lógica simplificada para exportação (TO_IDFACE)
    if request.direction == SyncDirection.TO_IDFACE:
        rules = await db.accessrule.find_many()
        
        # L1
        async with idface_client:
            for rule in rules:
                try:
                    await idface_client.create_access_rule({
                        "name": rule.name, "type": rule.type, "priority": rule.priority
                    })
                    success_count += 1
                except Exception as e:
                    errors.append(f"L1 Rule {rule.id}: {e}")
        
        # L2
        async with idface_client_2:
            for rule in rules:
                try:
                    await idface_client_2.create_access_rule({
                        "name": rule.name, "type": rule.type, "priority": rule.priority
                    })
                except Exception as e:
                    errors.append(f"L2 Rule {rule.id}: {e}")

    # Lógica para FROM_IDFACE seria similar ao Users (Importar de L1, depois L2)
    
    duration = (datetime.now() - start_time).total_seconds()
    return EntitySyncResult(
        entityType=SyncEntityType.ACCESS_RULES,
        status=SyncStatus.COMPLETED if not errors else SyncStatus.PARTIAL,
        successCount=success_count,
        errors=errors[:5],
        duration=duration
    )


async def _sync_time_zones(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza time zones sequencialmente"""
    start_time = datetime.now()
    errors = []
    success_count = 0
    
    if request.direction == SyncDirection.TO_IDFACE:
        time_zones = await db.timezone.find_many(include={"timeSpans": True})
        
        async def _push_tzs(client):
            count = 0
            for tz in time_zones:
                try:
                    res = await client.create_time_zone({"name": tz.name})
                    id_face = res.get("id")
                    if tz.timeSpans:
                        for span in tz.timeSpans:
                            # Payload de span simplificado
                            await client.create_time_span({
                                "time_zone_id": id_face, "start": span.start, "end": span.end,
                                "sun": 1 if span.sun else 0, "mon": 1 if span.mon else 0,
                                "tue": 1 if span.tue else 0, "wed": 1 if span.wed else 0,
                                "thu": 1 if span.thu else 0, "fri": 1 if span.fri else 0,
                                "sat": 1 if span.sat else 0, "hol1": 1 if span.hol1 else 0
                            })
                    count += 1
                except Exception as e:
                    errors.append(f"Device {client.base_url} TZ {tz.name}: {e}")
            return count

        # L1
        async with idface_client:
            success_count += await _push_tzs(idface_client)
        # L2
        async with idface_client_2:
            await _push_tzs(idface_client_2)

    return EntitySyncResult(
        entityType=SyncEntityType.TIME_ZONES,
        status=SyncStatus.COMPLETED,
        successCount=success_count,
        errors=errors,
        duration=(datetime.now() - start_time).total_seconds()
    )


async def _sync_access_logs(request: SyncEntityRequest, db) -> EntitySyncResult:
    """Sincroniza logs de acesso (Fila Indiana: Importa L1 depois L2)"""
    start_time = datetime.now()
    imported = 0
    skipped = 0
    errors = []
    
    if request.direction == SyncDirection.FROM_IDFACE:
        from app.routers.audit import _process_logs_from_device
        
        # L1
        res1 = await _process_logs_from_device(idface_client, db)
        imported += res1["imported"]
        skipped += res1["skipped"]
        if res1["error"]: errors.append(f"L1: {res1['error']}")
        
        # L2
        res2 = await _process_logs_from_device(idface_client_2, db)
        imported += res2["imported"]
        skipped += res2["skipped"]
        if res2["error"]: errors.append(f"L2: {res2['error']}")

    return EntitySyncResult(
        entityType=SyncEntityType.ACCESS_LOGS,
        status=SyncStatus.COMPLETED if not errors else SyncStatus.PARTIAL,
        successCount=imported,
        skippedCount=skipped,
        errors=errors,
        duration=(datetime.now() - start_time).total_seconds()
    )


async def _compare_users(db, include_details: bool) -> DataComparison:
    """Compara usuários locais vs iDFace (Leitor 1)"""
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
    """Compara regras de acesso locais vs iDFace (Leitor 1)"""
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
    Sincroniza múltiplos itens específicos em batch.
    Estratégia Fila Indiana: Processa todos os itens no Leitor 1, depois todos no Leitor 2.
    """
    results = []
    errors = []
    processed = 0
    failed = 0
    
    async def _process_items_on_device(client):
        nonlocal processed, failed
        device_results = []
        for item in request.items:
            try:
                if item.entityType == SyncEntityType.USERS:
                    user = await db.user.find_unique(where={"id": item.entityId})
                    if user:
                        user_data = {
                            "name": user.name, "registration": user.registration or ""
                        }
                        await client.create_user(user_data)
                        device_results.append(f"User {item.entityId} OK")
                    else:
                        raise Exception(f"Usuário {item.entityId} não encontrado")
                
                elif item.entityType == SyncEntityType.ACCESS_RULES:
                    rule = await db.accessrule.find_unique(where={"id": item.entityId})
                    if rule:
                        rule_data = {
                            "name": rule.name, "type": rule.type, "priority": rule.priority
                        }
                        await client.create_access_rule(rule_data)
                        device_results.append(f"Rule {item.entityId} OK")
                    else:
                        raise Exception(f"Regra {item.entityId} não encontrada")
            except Exception as e:
                # Se falhar no L1, contabilizamos como falha geral do item
                if client == idface_client:
                    failed += 1
                    errors.append(f"Item {item.entityId} falhou no L1: {e}")
                else:
                    errors.append(f"Item {item.entityId} falhou no L2: {e}")
        return device_results

    # 1. Leitor 1
    try:
        async with idface_client:
            await _process_items_on_device(idface_client)
    except Exception as e:
        errors.append(f"Falha conexão L1 Batch: {e}")

    # 2. Leitor 2
    try:
        async with idface_client_2:
            await _process_items_on_device(idface_client_2)
    except Exception as e:
        errors.append(f"Falha conexão L2 Batch: {e}")

    # Nota: A resposta BatchSyncResponse espera uma lista de resultados por item.
    # Como dividimos a execução por dispositivo, retornamos um sucesso genérico se L1 funcionou.
    processed = len(request.items) - failed
    
    return BatchSyncResponse(
        success=failed == 0,
        totalItems=len(request.items),
        processedItems=processed,
        failedItems=failed,
        results=[], # Simplificado para não complexar a resposta com duplicatas por device
        errors=errors
    )


# ==================== Automatic Sync Configuration ====================

_sync_config = SyncConfiguration()

@router.get("/config", response_model=SyncConfigurationResponse)
async def get_sync_configuration():
    return SyncConfigurationResponse(
        configuration=_sync_config,
        nextSyncTime=None,
        lastSyncTime=None
    )


@router.post("/config")
async def update_sync_configuration(config: SyncConfiguration):
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
    Gatilho manual: Sincroniza todos os usuários locais para AMBOS os leitores
    """
    request = SyncEntityRequest(
        entityType=SyncEntityType.USERS,
        direction=SyncDirection.TO_IDFACE,
        overwrite=False
    )
    result = await _sync_users(request, db)
    return {
        "success": result.status == SyncStatus.COMPLETED,
        "message": f"Processo finalizado. Sucesso: {result.successCount}, Falhas: {result.failedCount}",
        "result": result
    }


@router.post("/trigger/access-logs-from-idface")
async def trigger_access_logs_from_idface(db = Depends(get_db)):
    """
    Gatilho manual: Importa logs de acesso de AMBOS os leitores
    """
    request = SyncEntityRequest(
        entityType=SyncEntityType.ACCESS_LOGS,
        direction=SyncDirection.FROM_IDFACE
    )
    result = await _sync_access_logs(request, db)
    return {
        "success": result.status == SyncStatus.COMPLETED,
        "message": f"Processo finalizado. Importados: {result.successCount}",
        "result": result
    }


# ==================== Summary & Statistics ====================

@router.get("/summary", response_model=SyncSummary)
async def get_sync_summary(db = Depends(get_db)):
    """
    Retorna resumo geral do estado de sincronização
    """
    users_count = await db.user.count()
    rules_count = await db.accessrule.count()
    zones_count = await db.timezone.count()
    logs_count = await db.accesslog.count()
    
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
    Sincroniza portais do dispositivo iDFace (Leitor 1 como referência)
    """
    from app.services.portal_sync_service import portal_sync_service
    result = await portal_sync_service.sync_portals_from_device()
    return result


@router.get("/portals")
async def get_synced_portals_endpoint(db = Depends(get_db)):
    from app.services.portal_sync_service import portal_sync_service
    result = await portal_sync_service.get_synced_portals()
    return result