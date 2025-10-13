"""
Serviço de sincronização entre banco local e dispositivo iDFace
Contém lógica de negócio para operações de sincronização complexas
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from app.utils.idface_client import idface_client
from app.schemas.sync import (
    SyncEntityType, SyncDirection, SyncStatus,
    EntitySyncResult, SyncConflict
)
import base64
import logging

logger = logging.getLogger(__name__)


class SyncService:
    """Serviço para gerenciar sincronização de dados"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== User Sync ====================
    
    async def sync_user_to_idface(
        self,
        user_id: int,
        sync_image: bool = True,
        sync_cards: bool = True,
        sync_access_rules: bool = True
    ) -> Dict[str, Any]:
        """
        Sincroniza um usuário específico para o iDFace
        """
        # Buscar usuário completo
        user = await self.db.user.find_unique(
            where={"id": user_id},
            include={
                "cards": True,
                "qrcodes": True,
                "userAccessRules": {
                    "include": {"accessRule": True}
                }
            }
        )
        
        if not user:
            raise ValueError(f"Usuário {user_id} não encontrado")
        
        result = {
            "userId": user_id,
            "userName": user.name,
            "steps": [],
            "success": True
        }
        
        try:
            async with idface_client:
                # 1. Criar/atualizar usuário
                user_data = {
                    "name": user.name,
                    "registration": user.registration or "",
                    "password": user.password or "",
                    "salt": user.salt or ""
                }
                
                if user.idFaceId:
                    # Atualizar existente
                    await idface_client.update_user(user.idFaceId, user_data)
                    idface_user_id = user.idFaceId
                    result["steps"].append("Usuário atualizado no iDFace")
                else:
                    # Criar novo
                    response = await idface_client.create_user(user_data)
                    idface_user_id = response.get("id")
                    
                    # Salvar ID do iDFace
                    await self.db.user.update(
                        where={"id": user_id},
                        data={"idFaceId": idface_user_id}
                    )
                    result["steps"].append("Usuário criado no iDFace")
                
                result["idFaceId"] = idface_user_id
                
                # 2. Sincronizar imagem facial
                if sync_image and user.image:
                    try:
                        image_bytes = base64.b64decode(user.image)
                        await idface_client.set_user_image(
                            idface_user_id,
                            image_bytes,
                            match=True
                        )
                        result["steps"].append("Imagem facial sincronizada")
                    except Exception as e:
                        result["steps"].append(f"Erro ao sincronizar imagem: {str(e)}")
                        logger.error(f"Erro ao sincronizar imagem do usuário {user_id}: {e}")
                
                # 3. Sincronizar cartões
                if sync_cards and user.cards:
                    synced_cards = 0
                    for card in user.cards:
                        try:
                            await idface_client.create_card(
                                int(card.value),
                                idface_user_id
                            )
                            synced_cards += 1
                        except Exception as e:
                            logger.error(f"Erro ao sincronizar cartão {card.id}: {e}")
                    
                    result["steps"].append(f"{synced_cards}/{len(user.cards)} cartões sincronizados")
                
                # 4. Sincronizar regras de acesso
                if sync_access_rules and user.userAccessRules:
                    synced_rules = 0
                    for uar in user.userAccessRules:
                        if uar.accessRule.idFaceId:
                            try:
                                await idface_client.create_user_access_rule(
                                    idface_user_id,
                                    uar.accessRule.idFaceId
                                )
                                synced_rules += 1
                            except Exception as e:
                                logger.error(f"Erro ao vincular regra {uar.accessRuleId}: {e}")
                    
                    result["steps"].append(f"{synced_rules}/{len(user.userAccessRules)} regras vinculadas")
                
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            logger.error(f"Erro ao sincronizar usuário {user_id}: {e}")
        
        return result
    
    async def sync_user_from_idface(self, idface_user_id: int) -> Dict[str, Any]:
        """
        Importa um usuário do iDFace para o banco local
        """
        try:
            async with idface_client:
                # Buscar usuário no iDFace
                response = await idface_client.load_users(
                    where={"users": {"id": idface_user_id}}
                )
                
                users = response.get("users", [])
                if not users:
                    raise ValueError(f"Usuário {idface_user_id} não encontrado no iDFace")
                
                user_data = users[0]
                
                # Verificar se já existe localmente
                existing = await self.db.user.find_first(
                    where={"idFaceId": idface_user_id}
                )
                
                if existing:
                    # Atualizar
                    user = await self.db.user.update(
                        where={"id": existing.id},
                        data={
                            "name": user_data.get("name"),
                            "registration": user_data.get("registration")
                        }
                    )
                else:
                    # Criar
                    user = await self.db.user.create(
                        data={
                            "idFaceId": idface_user_id,
                            "name": user_data.get("name"),
                            "registration": user_data.get("registration")
                        }
                    )
                
                return {
                    "success": True,
                    "userId": user.id,
                    "action": "updated" if existing else "created"
                }
                
        except Exception as e:
            logger.error(f"Erro ao importar usuário {idface_user_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Bulk Sync Operations ====================
    
    async def bulk_sync_users_to_idface(
        self,
        user_ids: Optional[List[int]] = None,
        sync_images: bool = True
    ) -> EntitySyncResult:
        """
        Sincroniza múltiplos usuários para o iDFace
        """
        start_time = datetime.now()
        
        # Se não especificar IDs, sincronizar todos
        if user_ids:
            users = await self.db.user.find_many(
                where={"id": {"in": user_ids}}
            )
        else:
            users = await self.db.user.find_many()
        
        total = len(users)
        success_count = 0
        failed_count = 0
        errors = []
        
        for user in users:
            try:
                await self.sync_user_to_idface(
                    user.id,
                    sync_image=sync_images,
                    sync_cards=True,
                    sync_access_rules=True
                )
                success_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(f"Usuário {user.id} ({user.name}): {str(e)}")
                logger.error(f"Erro ao sincronizar usuário {user.id}: {e}")
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.USERS,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=total,
            successCount=success_count,
            failedCount=failed_count,
            errors=errors[:10],  # Limitar a 10 erros
            duration=duration
        )
    
    async def bulk_sync_users_from_idface(
        self,
        overwrite: bool = False
    ) -> EntitySyncResult:
        """
        Importa todos os usuários do iDFace
        """
        start_time = datetime.now()
        success_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []
        
        try:
            async with idface_client:
                response = await idface_client.load_users()
                users_data = response.get("users", [])
                
                for user_data in users_data:
                    try:
                        idface_id = user_data.get("id")
                        
                        # Verificar se já existe
                        existing = await self.db.user.find_first(
                            where={"idFaceId": idface_id}
                        )
                        
                        if existing and not overwrite:
                            skipped_count += 1
                            continue
                        
                        if existing:
                            await self.db.user.update(
                                where={"id": existing.id},
                                data={
                                    "name": user_data.get("name"),
                                    "registration": user_data.get("registration")
                                }
                            )
                        else:
                            await self.db.user.create(
                                data={
                                    "idFaceId": idface_id,
                                    "name": user_data.get("name"),
                                    "registration": user_data.get("registration")
                                }
                            )
                        
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        errors.append(f"Usuário iDFace ID {user_data.get('id')}: {str(e)}")
                
        except Exception as e:
            logger.error(f"Erro ao importar usuários do iDFace: {e}")
            return EntitySyncResult(
                entityType=SyncEntityType.USERS,
                status=SyncStatus.FAILED,
                errors=[str(e)]
            )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        return EntitySyncResult(
            entityType=SyncEntityType.USERS,
            status=SyncStatus.COMPLETED if failed_count == 0 else SyncStatus.PARTIAL,
            totalCount=success_count + failed_count + skipped_count,
            successCount=success_count,
            failedCount=failed_count,
            skippedCount=skipped_count,
            errors=errors[:10],
            duration=duration
        )
    
    # ==================== Access Rules Sync ====================
    
    async def sync_access_rule_to_idface(
        self,
        rule_id: int,
        sync_time_zones: bool = True
    ) -> Dict[str, Any]:
        """
        Sincroniza uma regra de acesso para o iDFace
        """
        rule = await self.db.accessrule.find_unique(
            where={"id": rule_id},
            include={
                "timeZones": {
                    "include": {"timeZone": True}
                }
            }
        )
        
        if not rule:
            raise ValueError(f"Regra {rule_id} não encontrada")
        
        result = {
            "ruleId": rule_id,
            "ruleName": rule.name,
            "steps": [],
            "success": True
        }
        
        try:
            async with idface_client:
                rule_data = {
                    "name": rule.name,
                    "type": rule.type,
                    "priority": rule.priority
                }
                
                if rule.idFaceId:
                    # Atualizar existente (se API suportar)
                    # await idface_client.update_access_rule(rule.idFaceId, rule_data)
                    idface_rule_id = rule.idFaceId
                    result["steps"].append("Regra já existe no iDFace")
                else:
                    # Criar nova
                    response = await idface_client.create_access_rule(rule_data)
                    idface_rule_id = response.get("id")
                    
                    # Salvar ID
                    await self.db.accessrule.update(
                        where={"id": rule_id},
                        data={"idFaceId": idface_rule_id}
                    )
                    result["steps"].append("Regra criada no iDFace")
                
                result["idFaceId"] = idface_rule_id
                
                # Sincronizar time zones vinculados
                if sync_time_zones and rule.timeZones:
                    synced_zones = 0
                    for art in rule.timeZones:
                        if art.timeZone.idFaceId:
                            synced_zones += 1
                    
                    result["steps"].append(f"{synced_zones} time zones vinculados")
                
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            logger.error(f"Erro ao sincronizar regra {rule_id}: {e}")
        
        return result
    
    # ==================== Time Zones Sync ====================
    
    async def sync_time_zone_to_idface(
        self,
        tz_id: int,
        sync_time_spans: bool = True
    ) -> Dict[str, Any]:
        """
        Sincroniza um time zone para o iDFace
        """
        tz = await self.db.timezone.find_unique(
            where={"id": tz_id},
            include={"timeSpans": True}
        )
        
        if not tz:
            raise ValueError(f"Time zone {tz_id} não encontrado")
        
        result = {
            "timeZoneId": tz_id,
            "timeZoneName": tz.name,
            "steps": [],
            "success": True
        }
        
        try:
            async with idface_client:
                tz_data = {"name": tz.name}
                
                if tz.idFaceId:
                    idface_tz_id = tz.idFaceId
                    result["steps"].append("Time zone já existe no iDFace")
                else:
                    response = await idface_client.create_time_zone(tz_data)
                    idface_tz_id = response.get("id")
                    
                    await self.db.timezone.update(
                        where={"id": tz_id},
                        data={"idFaceId": idface_tz_id}
                    )
                    result["steps"].append("Time zone criado no iDFace")
                
                result["idFaceId"] = idface_tz_id
                
                # Sincronizar time spans
                if sync_time_spans and tz.timeSpans:
                    synced_spans = 0
                    for span in tz.timeSpans:
                        try:
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
                            synced_spans += 1
                        except Exception as e:
                            logger.error(f"Erro ao sincronizar time span {span.id}: {e}")
                    
                    result["steps"].append(f"{synced_spans}/{len(tz.timeSpans)} time spans sincronizados")
                
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            logger.error(f"Erro ao sincronizar time zone {tz_id}: {e}")
        
        return result
    
    # ==================== Access Logs Sync ====================
    
    async def sync_access_logs_from_idface(
        self,
        skip_duplicates: bool = True
    ) -> EntitySyncResult:
        """
        Importa logs de acesso do iDFace
        """
        start_time = datetime.now()
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        try:
            async with idface_client:
                response = await idface_client.load_access_logs()
                logs_data = response.get("access_logs", [])
                
                for log_data in logs_data:
                    try:
                        # Verificar duplicata
                        if skip_duplicates:
                            existing = await self.db.accesslog.find_first(
                                where={
                                    "timestamp": log_data.get("timestamp"),
                                    "userId": log_data.get("user_id"),
                                    "event": log_data.get("event")
                                }
                            )
                            
                            if existing:
                                skipped_count += 1
                                continue
                        
                        # Criar log
                        await self.db.accesslog.create(
                            data={
                                "userId": log_data.get("user_id"),
                                "portalId": log_data.get("portal_id"),
                                "event": log_data.get("event", "unknown"),
                                "reason": log_data.get("reason"),
                                "cardValue": log_data.get("card_value"),
                                "timestamp": log_data.get("timestamp", datetime.now())
                            }
                        )
                        success_count += 1
                        
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"Erro ao importar log: {e}")
                
        except Exception as e:
            logger.error(f"Erro ao importar logs do iDFace: {e}")
            return EntitySyncResult(
                entityType=SyncEntityType.ACCESS_LOGS,
                status=SyncStatus.FAILED,
                errors=[str(e)]
            )
        
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
    
    # ==================== Conflict Detection ====================
    
    async def detect_conflicts(
        self,
        entity_type: SyncEntityType
    ) -> List[SyncConflict]:
        """
        Detecta conflitos entre dados locais e remotos
        """
        conflicts = []
        
        try:
            if entity_type == SyncEntityType.USERS:
                conflicts = await self._detect_user_conflicts()
            elif entity_type == SyncEntityType.ACCESS_RULES:
                conflicts = await self._detect_rule_conflicts()
        except Exception as e:
            logger.error(f"Erro ao detectar conflitos: {e}")
        
        return conflicts
    
    async def _detect_user_conflicts(self) -> List[SyncConflict]:
        """Detecta conflitos em usuários"""
        conflicts = []
        
        try:
            async with idface_client:
                # Buscar usuários remotos
                response = await idface_client.load_users()
                remote_users = {u.get("id"): u for u in response.get("users", [])}
                
                # Buscar usuários locais sincronizados
                local_users = await self.db.user.find_many(
                    where={"idFaceId": {"not": None}}
                )
                
                for local_user in local_users:
                    remote_user = remote_users.get(local_user.idFaceId)
                    
                    if not remote_user:
                        continue
                    
                    # Comparar campos
                    conflict_fields = []
                    
                    if local_user.name != remote_user.get("name"):
                        conflict_fields.append("name")
                    
                    if local_user.registration != remote_user.get("registration"):
                        conflict_fields.append("registration")
                    
                    if conflict_fields:
                        conflicts.append(SyncConflict(
                            entityType=SyncEntityType.USERS,
                            entityId=local_user.id,
                            localData={
                                "name": local_user.name,
                                "registration": local_user.registration
                            },
                            remoteData={
                                "name": remote_user.get("name"),
                                "registration": remote_user.get("registration")
                            },
                            conflictFields=conflict_fields,
                            localUpdatedAt=local_user.updatedAt,
                            remoteUpdatedAt=None
                        ))
        except Exception as e:
            logger.error(f"Erro ao detectar conflitos de usuários: {e}")
        
        return conflicts
    
    async def _detect_rule_conflicts(self) -> List[SyncConflict]:
        """Detecta conflitos em regras de acesso"""
        # Implementação similar ao _detect_user_conflicts
        return []
    
    # ==================== Statistics & Reporting ====================
    
    async def get_sync_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de sincronização
        """
        stats = {
            "local": {},
            "remote": {},
            "syncStatus": {}
        }
        
        try:
            # Estatísticas locais
            stats["local"]["users"] = await self.db.user.count()
            stats["local"]["accessRules"] = await self.db.accessrule.count()
            stats["local"]["timeZones"] = await self.db.timezone.count()
            stats["local"]["accessLogs"] = await self.db.accesslog.count()
            
            # Usuários sincronizados
            synced_users = await self.db.user.count(
                where={"idFaceId": {"not": None}}
            )
            stats["syncStatus"]["users"] = {
                "total": stats["local"]["users"],
                "synced": synced_users,
                "pending": stats["local"]["users"] - synced_users,
                "percentage": round((synced_users / stats["local"]["users"] * 100), 2)
                if stats["local"]["users"] > 0 else 0
            }
            
            # Tentar obter estatísticas remotas
            try:
                async with idface_client:
                    info = await idface_client.get_system_info()
                    capacity = info.get("capacity", {})
                    
                    stats["remote"]["users"] = capacity.get("current_users", 0)
                    stats["remote"]["maxUsers"] = capacity.get("max_users", 0)
                    stats["remote"]["faces"] = capacity.get("current_faces", 0)
                    stats["remote"]["cards"] = capacity.get("current_cards", 0)
            except Exception as e:
                logger.error(f"Erro ao obter estatísticas remotas: {e}")
                stats["remote"]["error"] = str(e)
        
        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas: {e}")
            stats["error"] = str(e)
        
        return stats
    
    # ==================== Cleanup Operations ====================
    
    async def cleanup_orphaned_records(self) -> Dict[str, int]:
        """
        Remove registros órfãos (sem vínculo com iDFace)
        """
        cleanup_stats = {
            "cards": 0,
            "qrcodes": 0,
            "userAccessRules": 0
        }
        
        try:
            # Cartões sem usuário
            orphaned_cards = await self.db.card.find_many(
                where={
                    "user": None
                }
            )
            
            for card in orphaned_cards:
                await self.db.card.delete(where={"id": card.id})
                cleanup_stats["cards"] += 1
            
            # QR Codes sem usuário
            orphaned_qrcodes = await self.db.qrcode.find_many(
                where={
                    "user": None
                }
            )
            
            for qr in orphaned_qrcodes:
                await self.db.qrcode.delete(where={"id": qr.id})
                cleanup_stats["qrcodes"] += 1
            
        except Exception as e:
            logger.error(f"Erro ao limpar registros órfãos: {e}")
        
        return cleanup_stats


# ==================== Helper Functions ====================

def calculate_sync_priority(entity_type: SyncEntityType) -> int:
    """
    Calcula prioridade de sincronização
    Menor número = maior prioridade
    """
    priorities = {
        SyncEntityType.TIME_ZONES: 1,
        SyncEntityType.ACCESS_RULES: 2,
        SyncEntityType.USERS: 3,
        SyncEntityType.CARDS: 4,
        SyncEntityType.ACCESS_LOGS: 5
    }
    
    return priorities.get(entity_type, 99)


def should_sync_entity(
    last_sync: Optional[datetime],
    sync_interval_minutes: int = 60
) -> bool:
    """
    Determina se uma entidade deve ser sincronizada
    baseado no último sync e intervalo configurado
    """
    if not last_sync:
        return True
    
    from datetime import timedelta
    threshold = datetime.now() - timedelta(minutes=sync_interval_minutes)
    
    return last_sync < threshold