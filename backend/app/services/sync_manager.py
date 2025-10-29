"""
Gerenciador de Sincronização Bidirecional
Mantém consistência entre BD Local e Leitor iDFace
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SyncManager:
    """
    Gerencia sincronização bidirecional entre BD Local e Leitor iDFace
    Garante que dados sejam criados em ambos e mantém IDs sincronizados
    """
    
    def __init__(self, db, idface_client):
        self.db = db
        self.idface = idface_client
    
    # ==================== TIME ZONES ====================
    
    async def sync_time_zone_bidirectional(
        self,
        name: str,
        time_spans: List[Dict]
    ) -> Dict[str, Any]:
        """
        Cria TimeZone no BD Local e iDFace, mantendo ambos sincronizados
        
        Fluxo:
        1. Cria no BD Local (gera id_local)
        2. Cria no iDFace (gera id_idface)
        3. Atualiza BD Local com id_idface
        4. Retorna ambos os IDs
        """
        try:
            # 1. Criar no BD Local
            local_tz = await self.db.timezone.create(
                data={"name": name}
            )
            logger.info(f"TimeZone criado localmente: ID {local_tz.id}")
            
            # 2. Criar no iDFace
            async with self.idface:
                idface_result = await self.idface.create_time_zone({
                    "name": name
                })
                idface_tz_id = idface_result.get("id")
                
                if not idface_tz_id:
                    raise ValueError("iDFace não retornou ID do TimeZone")
                
                logger.info(f"TimeZone criado no iDFace: ID {idface_tz_id}")
                
                # 3. Criar TimeSpans no iDFace
                for span in time_spans:
                    await self.idface.create_time_span({
                        "time_zone_id": idface_tz_id,
                        **span
                    })
            
            # 4. Atualizar BD Local com idFaceId
            updated_tz = await self.db.timezone.update(
                where={"id": local_tz.id},
                data={"idFaceId": idface_tz_id}
            )
            
            # 5. Criar TimeSpans no BD Local
            for span in time_spans:
                await self.db.timespan.create(
                    data={
                        "timeZoneId": local_tz.id,
                        **span
                    }
                )
            
            # 6. Auditar
            await self._audit_creation(
                entity="time_zone",
                entity_id=local_tz.id,
                action="time_zone_created",
                details={
                    "name": name,
                    "local_id": local_tz.id,
                    "idface_id": idface_tz_id,
                    "spans_count": len(time_spans)
                }
            )
            
            return {
                "success": True,
                "local_id": local_tz.id,
                "idface_id": idface_tz_id,
                "timezone": updated_tz,
                "message": "TimeZone criado e sincronizado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro na sincronização de TimeZone: {e}")
            
            # Rollback: tentar deletar do BD Local se criou
            if 'local_tz' in locals():
                try:
                    await self.db.timezone.delete(where={"id": local_tz.id})
                except:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "message": "Erro ao criar TimeZone"
            }
    
    # ==================== ACCESS RULES ====================
    
    async def sync_access_rule_bidirectional(
        self,
        name: str,
        rule_type: int = 1,
        priority: int = 0,
        time_zone_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Cria AccessRule no BD Local e iDFace, mantendo ambos sincronizados
        """
        try:
            # 1. Criar no BD Local
            local_rule = await self.db.accessrule.create(
                data={
                    "name": name,
                    "type": rule_type,
                    "priority": priority
                }
            )
            logger.info(f"AccessRule criada localmente: ID {local_rule.id}")
            
            # 2. Criar no iDFace
            async with self.idface:
                idface_result = await self.idface.create_access_rule({
                    "name": name,
                    "type": rule_type,
                    "priority": priority
                })
                idface_rule_id = idface_result.get("id")
                
                if not idface_rule_id:
                    raise ValueError("iDFace não retornou ID da AccessRule")
                
                logger.info(f"AccessRule criada no iDFace: ID {idface_rule_id}")
            
            # 3. Atualizar BD Local com idFaceId
            updated_rule = await self.db.accessrule.update(
                where={"id": local_rule.id},
                data={"idFaceId": idface_rule_id}
            )
            
            # 4. Vincular TimeZones se fornecidos
            if time_zone_ids:
                for tz_id in time_zone_ids:
                    await self.db.accessruletimezone.create(
                        data={
                            "accessRuleId": local_rule.id,
                            "timeZoneId": tz_id
                        }
                    )
            
            # 5. Auditar
            await self._audit_creation(
                entity="access_rule",
                entity_id=local_rule.id,
                action="access_rule_created",
                details={
                    "name": name,
                    "type": rule_type,
                    "priority": priority,
                    "local_id": local_rule.id,
                    "idface_id": idface_rule_id
                }
            )
            
            return {
                "success": True,
                "local_id": local_rule.id,
                "idface_id": idface_rule_id,
                "rule": updated_rule,
                "message": "AccessRule criada e sincronizada com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro na sincronização de AccessRule: {e}")
            
            # Rollback
            if 'local_rule' in locals():
                try:
                    await self.db.accessrule.delete(where={"id": local_rule.id})
                except:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "message": "Erro ao criar AccessRule"
            }
    
    # ==================== USERS ====================
    
    async def sync_user_bidirectional(
        self,
        name: str,
        registration: Optional[str] = None,
        password: Optional[str] = None,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        image: Optional[str] = None,
        cards: Optional[List[int]] = None,
        access_rule_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Cria User no BD Local e iDFace, mantendo ambos sincronizados
        """
        try:
            # 1. Criar no BD Local
            local_user = await self.db.user.create(
                data={
                    "name": name,
                    "registration": registration,
                    "password": password,
                    "beginTime": begin_time,
                    "endTime": end_time,
                    "image": image
                }
            )
            logger.info(f"User criado localmente: ID {local_user.id}")
            
            # 2. Criar no iDFace
            async with self.idface:
                idface_result = await self.idface.create_user({
                    "name": name,
                    "registration": registration or "",
                    "password": password or "",
                    "salt": ""
                })
                idface_user_id = idface_result.get("id")
                
                if not idface_user_id:
                    raise ValueError("iDFace não retornou ID do User")
                
                logger.info(f"User criado no iDFace: ID {idface_user_id}")
                
                # 3. Upload de imagem se fornecida
                if image:
                    import base64
                    image_bytes = base64.b64decode(image)
                    await self.idface.set_user_image(
                        idface_user_id,
                        image_bytes,
                        match=True
                    )
                    logger.info(f"Imagem facial enviada para iDFace")
                
                # 4. Criar cartões no iDFace
                if cards:
                    for card_value in cards:
                        await self.idface.create_card(card_value, idface_user_id)
            
            # 5. Atualizar BD Local com idFaceId
            updated_user = await self.db.user.update(
                where={"id": local_user.id},
                data={"idFaceId": idface_user_id}
            )
            
            # 6. Criar cartões no BD Local
            if cards:
                for card_value in cards:
                    await self.db.card.create(
                        data={
                            "value": card_value,
                            "userId": local_user.id
                        }
                    )
            
            # 7. Vincular Access Rules
            if access_rule_ids:
                for rule_id in access_rule_ids:
                    await self.db.useraccessrule.create(
                        data={
                            "userId": local_user.id,
                            "accessRuleId": rule_id
                        }
                    )
            
            # 8. Auditar
            await self._audit_creation(
                entity="user",
                entity_id=local_user.id,
                action="user_created",
                details={
                    "name": name,
                    "registration": registration,
                    "local_id": local_user.id,
                    "idface_id": idface_user_id,
                    "has_image": bool(image),
                    "cards_count": len(cards) if cards else 0
                }
            )
            
            return {
                "success": True,
                "local_id": local_user.id,
                "idface_id": idface_user_id,
                "user": updated_user,
                "message": "User criado e sincronizado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro na sincronização de User: {e}")
            
            # Rollback
            if 'local_user' in locals():
                try:
                    await self.db.user.delete(where={"id": local_user.id})
                except:
                    pass
            
            return {
                "success": False,
                "error": str(e),
                "message": "Erro ao criar User"
            }
    
    # ==================== VERIFICATION ====================
    
    async def verify_sync_integrity(self, entity_type: str) -> Dict[str, Any]:
        """
        Verifica se dados do BD Local estão sincronizados com iDFace
        Retorna lista de inconsistências
        """
        inconsistencies = []
        
        try:
            if entity_type == "time_zones":
                # Buscar do BD Local
                local_zones = await self.db.timezone.find_many()
                
                # Buscar do iDFace
                async with self.idface:
                    idface_result = await self.idface.request(
                        "POST",
                        "load_objects.fcgi",
                        json={"object": "time_zones"}
                    )
                    idface_zones = idface_result.get("time_zones", [])
                
                # Comparar
                idface_ids = {z.get("id") for z in idface_zones}
                
                for local_zone in local_zones:
                    if local_zone.idFaceId not in idface_ids:
                        inconsistencies.append({
                            "entity": "time_zone",
                            "local_id": local_zone.id,
                            "idface_id": local_zone.idFaceId,
                            "issue": "Existe no BD Local mas não no iDFace",
                            "name": local_zone.name
                        })
            
            elif entity_type == "access_rules":
                local_rules = await self.db.accessrule.find_many()
                
                async with self.idface:
                    idface_result = await self.idface.load_access_rules()
                    idface_rules = idface_result.get("access_rules", [])
                
                idface_ids = {r.get("id") for r in idface_rules}
                
                for local_rule in local_rules:
                    if local_rule.idFaceId not in idface_ids:
                        inconsistencies.append({
                            "entity": "access_rule",
                            "local_id": local_rule.id,
                            "idface_id": local_rule.idFaceId,
                            "issue": "Existe no BD Local mas não no iDFace",
                            "name": local_rule.name
                        })
            
            elif entity_type == "users":
                local_users = await self.db.user.find_many()
                
                async with self.idface:
                    idface_result = await self.idface.load_users()
                    idface_users = idface_result.get("users", [])
                
                idface_ids = {u.get("id") for u in idface_users}
                
                for local_user in local_users:
                    if local_user.idFaceId not in idface_ids:
                        inconsistencies.append({
                            "entity": "user",
                            "local_id": local_user.id,
                            "idface_id": local_user.idFaceId,
                            "issue": "Existe no BD Local mas não no iDFace",
                            "name": local_user.name
                        })
            
            return {
                "success": True,
                "entity_type": entity_type,
                "inconsistencies_count": len(inconsistencies),
                "inconsistencies": inconsistencies,
                "synced": len(inconsistencies) == 0
            }
            
        except Exception as e:
            logger.error(f"Erro ao verificar integridade: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== AUDIT ====================
    
    async def _audit_creation(
        self,
        entity: str,
        entity_id: int,
        action: str,
        details: Dict[str, Any],
        admin_id: Optional[int] = None
    ):
        """
        Registra ação no log de auditoria
        """
        try:
            await self.db.auditlog.create(
                data={
                    "adminId": admin_id,
                    "action": action,
                    "entity": entity,
                    "entityId": entity_id,
                    "details": str(details),  # JSON como string
                    "timestamp": datetime.now()
                }
            )
        except Exception as e:
            logger.error(f"Erro ao auditar: {e}")
    
    async def audit_door_action(
        self,
        portal_id: int,
        action: str,
        admin_id: Optional[int] = None
    ):
        """
        Registra abertura de porta por admin
        """
        await self._audit_creation(
            entity="portal",
            entity_id=portal_id,
            action=f"door_{action}",
            details={
                "portal_id": portal_id,
                "action": action,
                "triggered_by": "admin_button"
            },
            admin_id=admin_id
        )
    
    async def audit_access_log(
        self,
        user_id: Optional[int],
        portal_id: Optional[int],
        event: str,
        granted: bool
    ):
        """
        Registra acesso detectado pelo leitor
        """
        await self._audit_creation(
            entity="access_log",
            entity_id=0,
            action=f"access_{'granted' if granted else 'denied'}",
            details={
                "user_id": user_id,
                "portal_id": portal_id,
                "event": event
            }
        )