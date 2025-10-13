"""
Serviço de lógica de negócio para gerenciamento de regras de acesso
Contém operações complexas e validações de regras de acesso
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from app.utils.idface_client import idface_client
import logging

logger = logging.getLogger(__name__)


class AccessRuleService:
    """Serviço para gerenciar regras de acesso e suas operações"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== Access Rule CRUD Operations ====================
    
    async def create_access_rule(
        self,
        name: str,
        rule_type: int = 1,
        priority: int = 0
    ) -> Dict[str, Any]:
        """
        Cria uma nova regra de acesso com validações
        """
        # Validações
        validation_errors = []
        
        if not name or len(name.strip()) == 0:
            validation_errors.append("Nome da regra é obrigatório")
        
        if len(name) > 255:
            validation_errors.append("Nome não pode ter mais de 255 caracteres")
        
        if rule_type < 0 or rule_type > 10:
            validation_errors.append("Tipo de regra deve estar entre 0 e 10")
        
        if priority < 0:
            validation_errors.append("Prioridade não pode ser negativa")
        
        # Verificar se já existe regra com mesmo nome
        existing = await self.db.accessrule.find_first(
            where={"name": name.strip()}
        )
        
        if existing:
            validation_errors.append(f"Já existe uma regra com o nome '{name}'")
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        try:
            # Criar regra
            rule = await self.db.accessrule.create(
                data={
                    "name": name.strip(),
                    "type": rule_type,
                    "priority": priority
                }
            )
            
            logger.info(f"Regra de acesso criada: ID {rule.id}, Nome: {rule.name}")
            
            return {
                "success": True,
                "rule": rule,
                "message": "Regra de acesso criada com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao criar regra de acesso: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def update_access_rule(
        self,
        rule_id: int,
        name: Optional[str] = None,
        rule_type: Optional[int] = None,
        priority: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Atualiza uma regra de acesso existente
        """
        # Verificar se regra existe
        rule = await self.db.accessrule.find_unique(where={"id": rule_id})
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        # Validações
        validation_errors = []
        update_data = {}
        
        if name is not None:
            if len(name.strip()) == 0:
                validation_errors.append("Nome não pode ser vazio")
            elif len(name) > 255:
                validation_errors.append("Nome não pode ter mais de 255 caracteres")
            else:
                # Verificar duplicata
                existing = await self.db.accessrule.find_first(
                    where={
                        "name": name.strip(),
                        "id": {"not": rule_id}
                    }
                )
                if existing:
                    validation_errors.append(f"Já existe uma regra com o nome '{name}'")
                else:
                    update_data["name"] = name.strip()
        
        if rule_type is not None:
            if rule_type < 0 or rule_type > 10:
                validation_errors.append("Tipo de regra deve estar entre 0 e 10")
            else:
                update_data["type"] = rule_type
        
        if priority is not None:
            if priority < 0:
                validation_errors.append("Prioridade não pode ser negativa")
            else:
                update_data["priority"] = priority
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        if not update_data:
            return {
                "success": True,
                "rule": rule,
                "message": "Nenhuma alteração necessária"
            }
        
        try:
            updated_rule = await self.db.accessrule.update(
                where={"id": rule_id},
                data=update_data
            )
            
            logger.info(f"Regra de acesso atualizada: ID {rule_id}")
            
            return {
                "success": True,
                "rule": updated_rule,
                "message": "Regra atualizada com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao atualizar regra {rule_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def delete_access_rule(
        self,
        rule_id: int,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Deleta uma regra de acesso
        """
        rule = await self.db.accessrule.find_unique(
            where={"id": rule_id},
            include={
                "userAccessRules": True,
                "groupAccessRules": True,
                "portalAccessRules": True,
                "timeZones": True
            }
        )
        
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        # Verificar vínculos
        related_data = {
            "users": len(rule.userAccessRules) if rule.userAccessRules else 0,
            "groups": len(rule.groupAccessRules) if rule.groupAccessRules else 0,
            "portals": len(rule.portalAccessRules) if rule.portalAccessRules else 0,
            "timeZones": len(rule.timeZones) if rule.timeZones else 0
        }
        
        total_relations = sum(related_data.values())
        
        # Se tem vínculos e não é force, avisar
        if total_relations > 0 and not force:
            return {
                "success": False,
                "errors": [
                    f"Regra possui {total_relations} vínculo(s) ativo(s). "
                    "Use force=true para forçar deleção."
                ],
                "relatedData": related_data
            }
        
        try:
            # Deletar regra (cascade automático)
            await self.db.accessrule.delete(where={"id": rule_id})
            
            logger.info(f"Regra de acesso deletada: ID {rule_id}, Nome: {rule.name}")
            
            return {
                "success": True,
                "message": f"Regra '{rule.name}' deletada com sucesso",
                "deletedRelations": related_data
            }
            
        except Exception as e:
            logger.error(f"Erro ao deletar regra {rule_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== User-Rule Linking ====================
    
    async def link_user_to_rule(
        self,
        user_id: int,
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Vincula um usuário a uma regra de acesso
        """
        # Verificar usuário
        user = await self.db.user.find_unique(where={"id": user_id})
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
            }
        
        # Verificar regra
        rule = await self.db.accessrule.find_unique(where={"id": rule_id})
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        # Verificar se já existe vínculo
        existing = await self.db.useraccessrule.find_first(
            where={
                "userId": user_id,
                "accessRuleId": rule_id
            }
        )
        
        if existing:
            return {
                "success": False,
                "errors": [f"Usuário '{user.name}' já está vinculado à regra '{rule.name}'"]
            }
        
        try:
            link = await self.db.useraccessrule.create(
                data={
                    "userId": user_id,
                    "accessRuleId": rule_id
                }
            )
            
            logger.info(f"Usuário {user_id} vinculado à regra {rule_id}")
            
            return {
                "success": True,
                "link": link,
                "message": f"Usuário '{user.name}' vinculado à regra '{rule.name}'"
            }
            
        except Exception as e:
            logger.error(f"Erro ao vincular usuário à regra: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def unlink_user_from_rule(
        self,
        user_id: int,
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Remove vínculo entre usuário e regra
        """
        link = await self.db.useraccessrule.find_first(
            where={
                "userId": user_id,
                "accessRuleId": rule_id
            }
        )
        
        if not link:
            return {
                "success": False,
                "errors": ["Vínculo não encontrado"]
            }
        
        try:
            await self.db.useraccessrule.delete(where={"id": link.id})
            
            logger.info(f"Vínculo removido: Usuário {user_id} <-> Regra {rule_id}")
            
            return {
                "success": True,
                "message": "Vínculo removido com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover vínculo: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def bulk_link_users_to_rule(
        self,
        user_ids: List[int],
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Vincula múltiplos usuários a uma regra
        """
        # Verificar regra
        rule = await self.db.accessrule.find_unique(where={"id": rule_id})
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        success_count = 0
        failed_count = 0
        errors = []
        
        for user_id in user_ids:
            result = await self.link_user_to_rule(user_id, rule_id)
            if result["success"]:
                success_count += 1
            else:
                failed_count += 1
                errors.extend(result["errors"])
        
        return {
            "success": failed_count == 0,
            "message": f"{success_count} usuário(s) vinculado(s) com sucesso",
            "successCount": success_count,
            "failedCount": failed_count,
            "errors": errors[:10]  # Limitar erros
        }
    
    # ==================== Time Zone Linking ====================
    
    async def link_time_zone_to_rule(
        self,
        time_zone_id: int,
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Vincula um time zone a uma regra de acesso
        """
        # Verificar time zone
        tz = await self.db.timezone.find_unique(where={"id": time_zone_id})
        if not tz:
            return {
                "success": False,
                "errors": [f"Time zone {time_zone_id} não encontrado"]
            }
        
        # Verificar regra
        rule = await self.db.accessrule.find_unique(where={"id": rule_id})
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        # Verificar duplicata
        existing = await self.db.accessruletimezone.find_first(
            where={
                "timeZoneId": time_zone_id,
                "accessRuleId": rule_id
            }
        )
        
        if existing:
            return {
                "success": False,
                "errors": [f"Time zone '{tz.name}' já está vinculado à regra '{rule.name}'"]
            }
        
        try:
            link = await self.db.accessruletimezone.create(
                data={
                    "timeZoneId": time_zone_id,
                    "accessRuleId": rule_id
                }
            )
            
            logger.info(f"Time zone {time_zone_id} vinculado à regra {rule_id}")
            
            return {
                "success": True,
                "link": link,
                "message": f"Time zone '{tz.name}' vinculado à regra '{rule.name}'"
            }
            
        except Exception as e:
            logger.error(f"Erro ao vincular time zone à regra: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def unlink_time_zone_from_rule(
        self,
        time_zone_id: int,
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Remove vínculo entre time zone e regra
        """
        link = await self.db.accessruletimezone.find_first(
            where={
                "timeZoneId": time_zone_id,
                "accessRuleId": rule_id
            }
        )
        
        if not link:
            return {
                "success": False,
                "errors": ["Vínculo não encontrado"]
            }
        
        try:
            await self.db.accessruletimezone.delete(where={"id": link.id})
            
            logger.info(f"Vínculo removido: Time zone {time_zone_id} <-> Regra {rule_id}")
            
            return {
                "success": True,
                "message": "Vínculo removido com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover vínculo: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Search & Query ====================
    
    async def search_access_rules(
        self,
        query: Optional[str] = None,
        rule_type: Optional[int] = None,
        min_priority: Optional[int] = None,
        max_priority: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Busca regras de acesso com filtros
        """
        where = {}
        
        # Filtro por nome
        if query:
            where["name"] = {"contains": query, "mode": "insensitive"}
        
        # Filtro por tipo
        if rule_type is not None:
            where["type"] = rule_type
        
        # Filtro por prioridade
        if min_priority is not None or max_priority is not None:
            where["priority"] = {}
            if min_priority is not None:
                where["priority"]["gte"] = min_priority
            if max_priority is not None:
                where["priority"]["lte"] = max_priority
        
        try:
            rules = await self.db.accessrule.find_many(
                where=where,
                skip=skip,
                take=limit,
                order_by={"priority": "asc"},
                include={
                    "userAccessRules": {"include": {"user": True}},
                    "timeZones": {"include": {"timeZone": True}}
                }
            )
            
            total = await self.db.accessrule.count(where=where)
            
            return {
                "success": True,
                "rules": rules,
                "total": total,
                "skip": skip,
                "limit": limit
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar regras: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def get_rule_full_details(self, rule_id: int) -> Dict[str, Any]:
        """
        Retorna detalhes completos de uma regra
        """
        try:
            rule = await self.db.accessrule.find_unique(
                where={"id": rule_id},
                include={
                    "userAccessRules": {
                        "include": {"user": True}
                    },
                    "groupAccessRules": {
                        "include": {"group": True}
                    },
                    "portalAccessRules": {
                        "include": {"portal": True}
                    },
                    "timeZones": {
                        "include": {
                            "timeZone": {
                                "include": {"timeSpans": True}
                            }
                        }
                    }
                }
            )
            
            if not rule:
                return {
                    "success": False,
                    "errors": [f"Regra {rule_id} não encontrada"]
                }
            
            return {
                "success": True,
                "rule": rule,
                "statistics": {
                    "totalUsers": len(rule.userAccessRules) if rule.userAccessRules else 0,
                    "totalGroups": len(rule.groupAccessRules) if rule.groupAccessRules else 0,
                    "totalPortals": len(rule.portalAccessRules) if rule.portalAccessRules else 0,
                    "totalTimeZones": len(rule.timeZones) if rule.timeZones else 0,
                    "syncedWithDevice": bool(rule.idFaceId)
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar detalhes da regra {rule_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def get_users_by_rule(
        self,
        rule_id: int,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Lista usuários vinculados a uma regra
        """
        try:
            links = await self.db.useraccessrule.find_many(
                where={"accessRuleId": rule_id},
                skip=skip,
                take=limit,
                include={"user": True}
            )
            
            total = await self.db.useraccessrule.count(
                where={"accessRuleId": rule_id}
            )
            
            users = [link.user for link in links if link.user]
            
            return {
                "success": True,
                "users": users,
                "total": total,
                "ruleId": rule_id
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar usuários da regra {rule_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Priority Management ====================
    
    async def reorder_priorities(
        self,
        rule_priorities: Dict[int, int]
    ) -> Dict[str, Any]:
        """
        Reordena prioridades de múltiplas regras
        rule_priorities: {rule_id: new_priority}
        """
        success_count = 0
        failed_count = 0
        errors = []
        
        for rule_id, new_priority in rule_priorities.items():
            try:
                await self.db.accessrule.update(
                    where={"id": rule_id},
                    data={"priority": new_priority}
                )
                success_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(f"Regra {rule_id}: {str(e)}")
        
        return {
            "success": failed_count == 0,
            "message": f"{success_count} prioridade(s) atualizada(s)",
            "successCount": success_count,
            "failedCount": failed_count,
            "errors": errors
        }
    
    async def get_next_available_priority(self) -> int:
        """
        Retorna a próxima prioridade disponível
        """
        try:
            highest = await self.db.accessrule.find_first(
                order_by={"priority": "desc"}
            )
            
            if highest:
                return highest.priority + 1
            
            return 0
            
        except Exception as e:
            logger.error(f"Erro ao buscar próxima prioridade: {e}")
            return 0
    
    # ==================== Statistics ====================
    
    async def get_access_rule_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas gerais de regras de acesso
        """
        try:
            total_rules = await self.db.accessrule.count()
            
            # Regras sincronizadas
            synced_rules = await self.db.accessrule.count(
                where={"idFaceId": {"not": None}}
            )
            
            # Regras por tipo
            rules_by_type = {}
            for rule_type in range(11):  # 0-10
                count = await self.db.accessrule.count(
                    where={"type": rule_type}
                )
                if count > 0:
                    rules_by_type[f"type_{rule_type}"] = count
            
            # Total de vínculos
            total_user_links = await self.db.useraccessrule.count()
            total_time_zone_links = await self.db.accessruletimezone.count()
            
            return {
                "success": True,
                "statistics": {
                    "totalRules": total_rules,
                    "syncedRules": synced_rules,
                    "totalUserLinks": total_user_links,
                    "totalTimeZoneLinks": total_time_zone_links,
                    "rulesByType": rules_by_type,
                    "percentages": {
                        "synced": round((synced_rules / total_rules * 100), 2) if total_rules > 0 else 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Validation ====================
    
    async def validate_rule_configuration(
        self,
        rule_id: int
    ) -> Dict[str, Any]:
        """
        Valida se uma regra está corretamente configurada
        """
        rule = await self.db.accessrule.find_unique(
            where={"id": rule_id},
            include={
                "userAccessRules": True,
                "timeZones": True
            }
        )
        
        if not rule:
            return {
                "valid": False,
                "errors": [f"Regra {rule_id} não encontrada"]
            }
        
        warnings = []
        errors = []
        
        # Verificar se tem usuários vinculados
        if not rule.userAccessRules or len(rule.userAccessRules) == 0:
            warnings.append("Regra não possui usuários vinculados")
        
        # Verificar se tem time zones
        if not rule.timeZones or len(rule.timeZones) == 0:
            warnings.append("Regra não possui time zones configurados")
        
        # Verificar sincronização
        if not rule.idFaceId:
            warnings.append("Regra não está sincronizada com o dispositivo")
        
        is_valid = len(errors) == 0
        
        return {
            "valid": is_valid,
            "ruleId": rule_id,
            "ruleName": rule.name,
            "errors": errors,
            "warnings": warnings,
            "status": "valid" if is_valid else "invalid"
        }