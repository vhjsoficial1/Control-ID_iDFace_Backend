"""
Serviço de Backup e Restore do Banco de Dados
Exporta e importa dados completos do sistema
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json
import zipfile
import io
import logging

logger = logging.getLogger(__name__)


class BackupService:
    """Serviço para gerenciar backup e restore de dados"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== EXPORT/BACKUP ====================
    
    async def create_full_backup(
        self,
        include_images: bool = False,
        include_logs: bool = True,
        compress: bool = True
    ) -> Dict[str, Any]:
        """
        Cria backup completo do banco de dados
        
        Args:
            include_images: Incluir imagens faciais (aumenta muito o tamanho)
            include_logs: Incluir logs de acesso
            compress: Compactar em ZIP
        
        Returns:
            Dict com dados do backup e metadados
        """
        logger.info("Iniciando criação de backup completo...")
        start_time = datetime.now()
        
        backup_data = {
            "metadata": {
                "backup_date": start_time.isoformat(),
                "version": "1.0.0",
                "system": "iDFace Control System",
                "include_images": include_images,
                "include_logs": include_logs
            },
            "data": {}
        }
        
        try:
            # 1. Exportar Usuários
            users = await self._export_users(include_images)
            backup_data["data"]["users"] = users
            logger.info(f"✓ {len(users)} usuários exportados")
            
            # 2. Exportar Regras de Acesso
            access_rules = await self._export_access_rules()
            backup_data["data"]["access_rules"] = access_rules
            logger.info(f"✓ {len(access_rules)} regras de acesso exportadas")
            
            # 3. Exportar Time Zones
            time_zones = await self._export_time_zones()
            backup_data["data"]["time_zones"] = time_zones
            logger.info(f"✓ {len(time_zones)} time zones exportados")
            
            # 4. Exportar Grupos
            groups = await self._export_groups()
            backup_data["data"]["groups"] = groups
            logger.info(f"✓ {len(groups)} grupos exportados")
            
            # 5. Exportar Portais
            portals = await self._export_portals()
            backup_data["data"]["portals"] = portals
            logger.info(f"✓ {len(portals)} portais exportados")
            
            # 6. Exportar Logs de Acesso (opcional)
            if include_logs:
                access_logs = await self._export_access_logs()
                backup_data["data"]["access_logs"] = access_logs
                logger.info(f"✓ {len(access_logs)} logs exportados")
            
            # 7. Exportar Vínculos
            relationships = await self._export_relationships()
            backup_data["data"]["relationships"] = relationships
            logger.info(f"✓ Relacionamentos exportados")
            
            # Calcular estatísticas
            duration = (datetime.now() - start_time).total_seconds()
            backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
            size_bytes = len(backup_json.encode('utf-8'))
            
            backup_data["metadata"]["duration_seconds"] = duration
            backup_data["metadata"]["size_bytes"] = size_bytes
            backup_data["metadata"]["size_mb"] = round(size_bytes / 1024 / 1024, 2)
            
            # Compactar se solicitado
            if compress:
                compressed = self._compress_backup(backup_json)
                compressed_size = len(compressed)
                
                logger.info(f"✓ Backup compactado: {size_bytes} → {compressed_size} bytes")
                
                return {
                    "success": True,
                    "backup_data": compressed,
                    "format": "zip",
                    "metadata": backup_data["metadata"],
                    "compression_ratio": round((1 - compressed_size/size_bytes) * 100, 2)
                }
            
            return {
                "success": True,
                "backup_data": backup_json,
                "format": "json",
                "metadata": backup_data["metadata"]
            }
            
        except Exception as e:
            logger.error(f"Erro ao criar backup: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _export_users(self, include_images: bool) -> List[Dict]:
        """Exporta todos os usuários"""
        users = await self.db.user.find_many(
            include={
                "cards": True,
                "qrcodes": True,
                "templates": True
            }
        )
        
        exported = []
        for user in users:
            user_data = {
                "id": user.id,
                "idFaceId": user.idFaceId,
                "name": user.name,
                "registration": user.registration,
                "beginTime": user.beginTime.isoformat() if user.beginTime else None,
                "endTime": user.endTime.isoformat() if user.endTime else None,
                "cards": [{"value": str(c.value)} for c in user.cards] if user.cards else [],
                "qrcodes": [{"value": q.value} for q in user.qrcodes] if user.qrcodes else [],
                "templates": [
                    {
                        "fingerType": t.fingerType,
                        "template": t.template
                    } for t in user.templates
                ] if user.templates else []
            }
            
            # Incluir imagem apenas se solicitado
            if include_images and user.image:
                user_data["image"] = user.image
                user_data["imageTimestamp"] = user.imageTimestamp.isoformat() if user.imageTimestamp else None
            
            exported.append(user_data)
        
        return exported
    
    async def _export_access_rules(self) -> List[Dict]:
        """Exporta todas as regras de acesso"""
        rules = await self.db.accessrule.find_many()
        
        return [
            {
                "id": r.id,
                "idFaceId": r.idFaceId,
                "name": r.name,
                "type": r.type,
                "priority": r.priority
            }
            for r in rules
        ]
    
    async def _export_time_zones(self) -> List[Dict]:
        """Exporta todos os time zones com seus time spans"""
        time_zones = await self.db.timezone.find_many(
            include={"timeSpans": True}
        )
        
        return [
            {
                "id": tz.id,
                "idFaceId": tz.idFaceId,
                "name": tz.name,
                "timeSpans": [
                    {
                        "start": span.start,
                        "end": span.end,
                        "sun": span.sun,
                        "mon": span.mon,
                        "tue": span.tue,
                        "wed": span.wed,
                        "thu": span.thu,
                        "fri": span.fri,
                        "sat": span.sat,
                        "hol1": span.hol1,
                        "hol2": span.hol2,
                        "hol3": span.hol3
                    }
                    for span in tz.timeSpans
                ] if tz.timeSpans else []
            }
            for tz in time_zones
        ]
    
    async def _export_groups(self) -> List[Dict]:
        """Exporta todos os grupos"""
        groups = await self.db.group.find_many()
        
        return [
            {
                "id": g.id,
                "idFaceId": g.idFaceId,
                "name": g.name
            }
            for g in groups
        ]
    
    async def _export_portals(self) -> List[Dict]:
        """Exporta todos os portais"""
        portals = await self.db.portal.find_many()
        
        return [
            {
                "id": p.id,
                "idFaceId": p.idFaceId,
                "name": p.name
            }
            for p in portals
        ]
    
    async def _export_access_logs(self, limit: int = 10000) -> List[Dict]:
        """Exporta logs de acesso (limitado)"""
        logs = await self.db.accesslog.find_many(
            take=limit,
            order={"timestamp": "desc"}
        )
        
        return [
            {
                "userId": log.userId,
                "portalId": log.portalId,
                "event": log.event,
                "reason": log.reason,
                "cardValue": log.cardValue,
                "timestamp": log.timestamp.isoformat()
            }
            for log in logs
        ]
    
    async def _export_relationships(self) -> Dict[str, List]:
        """Exporta todos os relacionamentos entre entidades"""
        
        # User <-> AccessRule
        user_rules = await self.db.useraccessrule.find_many()
        
        # User <-> Group
        user_groups = await self.db.usergroup.find_many()
        
        # Group <-> AccessRule
        group_rules = await self.db.groupaccessrule.find_many()
        
        # AccessRule <-> TimeZone
        rule_zones = await self.db.accessruletimezone.find_many()
        
        # Portal <-> AccessRule
        portal_rules = await self.db.portalaccessrule.find_many()
        
        return {
            "user_access_rules": [
                {"userId": ur.userId, "accessRuleId": ur.accessRuleId}
                for ur in user_rules
            ],
            "user_groups": [
                {"userId": ug.userId, "groupId": ug.groupId}
                for ug in user_groups
            ],
            "group_access_rules": [
                {"groupId": gr.groupId, "accessRuleId": gr.accessRuleId}
                for gr in group_rules
            ],
            "access_rule_time_zones": [
                {"accessRuleId": rt.accessRuleId, "timeZoneId": rt.timeZoneId}
                for rt in rule_zones
            ],
            "portal_access_rules": [
                {"portalId": pr.portalId, "accessRuleId": pr.accessRuleId}
                for pr in portal_rules
            ]
        }
    
    def _compress_backup(self, json_data: str) -> bytes:
        """Compacta backup em ZIP"""
        buffer = io.BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"idface_backup_{timestamp}.json"
            zf.writestr(filename, json_data)
        
        return buffer.getvalue()
    
    # ==================== IMPORT/RESTORE ====================
    
    async def restore_from_backup(
        self,
        backup_data: str,
        clear_before: bool = False,
        skip_existing: bool = True,
        restore_logs: bool = False
    ) -> Dict[str, Any]:
        """
        Restaura dados a partir de um backup
        
        Args:
            backup_data: Dados do backup (JSON ou ZIP)
            clear_before: Limpar banco antes de restaurar
            skip_existing: Pular registros já existentes
            restore_logs: Restaurar logs de acesso
        
        Returns:
            Resultado da operação com estatísticas
        """
        logger.info("Iniciando restauração de backup...")
        start_time = datetime.now()
        
        stats = {
            "users": {"imported": 0, "skipped": 0, "failed": 0},
            "access_rules": {"imported": 0, "skipped": 0, "failed": 0},
            "time_zones": {"imported": 0, "skipped": 0, "failed": 0},
            "groups": {"imported": 0, "skipped": 0, "failed": 0},
            "portals": {"imported": 0, "skipped": 0, "failed": 0},
            "relationships": {"imported": 0, "failed": 0},
            "access_logs": {"imported": 0, "failed": 0}
        }
        
        try:
            # Parse do backup
            if isinstance(backup_data, bytes):
                backup_data = self._decompress_backup(backup_data)
            
            data = json.loads(backup_data)
            
            # Validar estrutura
            if "data" not in data:
                raise ValueError("Backup inválido: estrutura incorreta")
            
            # Limpar banco se solicitado
            if clear_before:
                await self._clear_database()
                logger.info("✓ Banco de dados limpo")
            
            # Restaurar dados
            backup_content = data["data"]
            
            # 1. Restaurar Time Zones primeiro (dependência)
            if "time_zones" in backup_content:
                result = await self._restore_time_zones(
                    backup_content["time_zones"],
                    skip_existing
                )
                stats["time_zones"].update(result)
            
            # 2. Restaurar Regras de Acesso
            if "access_rules" in backup_content:
                result = await self._restore_access_rules(
                    backup_content["access_rules"],
                    skip_existing
                )
                stats["access_rules"].update(result)
            
            # 3. Restaurar Grupos
            if "groups" in backup_content:
                result = await self._restore_groups(
                    backup_content["groups"],
                    skip_existing
                )
                stats["groups"].update(result)
            
            # 4. Restaurar Portais
            if "portals" in backup_content:
                result = await self._restore_portals(
                    backup_content["portals"],
                    skip_existing
                )
                stats["portals"].update(result)
            
            # 5. Restaurar Usuários
            if "users" in backup_content:
                result = await self._restore_users(
                    backup_content["users"],
                    skip_existing
                )
                stats["users"].update(result)
            
            # 6. Restaurar Relacionamentos
            if "relationships" in backup_content:
                result = await self._restore_relationships(
                    backup_content["relationships"]
                )
                stats["relationships"].update(result)
            
            # 7. Restaurar Logs (opcional)
            if restore_logs and "access_logs" in backup_content:
                result = await self._restore_access_logs(
                    backup_content["access_logs"]
                )
                stats["access_logs"].update(result)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": True,
                "message": "Backup restaurado com sucesso",
                "duration_seconds": duration,
                "statistics": stats
            }
            
        except Exception as e:
            logger.error(f"Erro ao restaurar backup: {e}")
            return {
                "success": False,
                "error": str(e),
                "statistics": stats
            }
    
    async def _restore_users(self, users: List[Dict], skip_existing: bool) -> Dict:
        """Restaura usuários"""
        imported = 0
        skipped = 0
        failed = 0
        
        for user_data in users:
            try:
                # Verificar se já existe
                if skip_existing and user_data.get("registration"):
                    existing = await self.db.user.find_first(
                        where={"registration": user_data["registration"]}
                    )
                    if existing:
                        skipped += 1
                        continue
                
                # Criar usuário
                user = await self.db.user.create(
                    data={
                        "idFaceId": user_data.get("idFaceId"),
                        "name": user_data["name"],
                        "registration": user_data.get("registration"),
                        "beginTime": user_data.get("beginTime"),
                        "endTime": user_data.get("endTime"),
                        "image": user_data.get("image"),
                        "imageTimestamp": user_data.get("imageTimestamp")
                    }
                )
                
                # Restaurar cartões
                for card in user_data.get("cards", []):
                    await self.db.card.create(
                        data={
                            "value": int(card["value"]),
                            "userId": user.id
                        }
                    )
                
                # Restaurar QR codes
                for qr in user_data.get("qrcodes", []):
                    await self.db.qrcode.create(
                        data={
                            "value": qr["value"],
                            "userId": user.id
                        }
                    )
                
                imported += 1
                
            except Exception as e:
                logger.error(f"Erro ao restaurar usuário: {e}")
                failed += 1
        
        return {"imported": imported, "skipped": skipped, "failed": failed}
    
    async def _restore_access_rules(self, rules: List[Dict], skip_existing: bool) -> Dict:
        """Restaura regras de acesso"""
        imported = 0
        skipped = 0
        failed = 0
        
        for rule_data in rules:
            try:
                if skip_existing:
                    existing = await self.db.accessrule.find_first(
                        where={"name": rule_data["name"]}
                    )
                    if existing:
                        skipped += 1
                        continue
                
                await self.db.accessrule.create(
                    data={
                        "idFaceId": rule_data.get("idFaceId"),
                        "name": rule_data["name"],
                        "type": rule_data["type"],
                        "priority": rule_data["priority"]
                    }
                )
                imported += 1
                
            except Exception as e:
                logger.error(f"Erro ao restaurar regra: {e}")
                failed += 1
        
        return {"imported": imported, "skipped": skipped, "failed": failed}
    
    async def _restore_time_zones(self, zones: List[Dict], skip_existing: bool) -> Dict:
        """Restaura time zones"""
        imported = 0
        skipped = 0
        failed = 0
        
        for tz_data in zones:
            try:
                if skip_existing:
                    existing = await self.db.timezone.find_first(
                        where={"name": tz_data["name"]}
                    )
                    if existing:
                        skipped += 1
                        continue
                
                tz = await self.db.timezone.create(
                    data={
                        "idFaceId": tz_data.get("idFaceId"),
                        "name": tz_data["name"]
                    }
                )
                
                # Restaurar time spans
                for span in tz_data.get("timeSpans", []):
                    await self.db.timespan.create(
                        data={
                            "timeZoneId": tz.id,
                            **span
                        }
                    )
                
                imported += 1
                
            except Exception as e:
                logger.error(f"Erro ao restaurar time zone: {e}")
                failed += 1
        
        return {"imported": imported, "skipped": skipped, "failed": failed}
    
    async def _restore_groups(self, groups: List[Dict], skip_existing: bool) -> Dict:
        """Restaura grupos"""
        imported = 0
        skipped = 0
        failed = 0
        
        for group_data in groups:
            try:
                if skip_existing:
                    existing = await self.db.group.find_first(
                        where={"name": group_data["name"]}
                    )
                    if existing:
                        skipped += 1
                        continue
                
                await self.db.group.create(
                    data={
                        "idFaceId": group_data.get("idFaceId"),
                        "name": group_data["name"]
                    }
                )
                imported += 1
                
            except Exception as e:
                logger.error(f"Erro ao restaurar grupo: {e}")
                failed += 1
        
        return {"imported": imported, "skipped": skipped, "failed": failed}
    
    async def _restore_portals(self, portals: List[Dict], skip_existing: bool) -> Dict:
        """Restaura portais"""
        imported = 0
        skipped = 0
        failed = 0
        
        for portal_data in portals:
            try:
                if skip_existing:
                    existing = await self.db.portal.find_first(
                        where={"name": portal_data["name"]}
                    )
                    if existing:
                        skipped += 1
                        continue
                
                await self.db.portal.create(
                    data={
                        "idFaceId": portal_data.get("idFaceId"),
                        "name": portal_data["name"]
                    }
                )
                imported += 1
                
            except Exception as e:
                logger.error(f"Erro ao restaurar portal: {e}")
                failed += 1
        
        return {"imported": imported, "skipped": skipped, "failed": failed}
    
    async def _restore_relationships(self, relationships: Dict) -> Dict:
        """Restaura relacionamentos entre entidades"""
        imported = 0
        failed = 0
        
        # User <-> AccessRule
        for rel in relationships.get("user_access_rules", []):
            try:
                await self.db.useraccessrule.create(data=rel)
                imported += 1
            except:
                failed += 1
        
        # User <-> Group
        for rel in relationships.get("user_groups", []):
            try:
                await self.db.usergroup.create(data=rel)
                imported += 1
            except:
                failed += 1
        
        # Group <-> AccessRule
        for rel in relationships.get("group_access_rules", []):
            try:
                await self.db.groupaccessrule.create(data=rel)
                imported += 1
            except:
                failed += 1
        
        # AccessRule <-> TimeZone
        for rel in relationships.get("access_rule_time_zones", []):
            try:
                await self.db.accessruletimezone.create(data=rel)
                imported += 1
            except:
                failed += 1
        
        # Portal <-> AccessRule
        for rel in relationships.get("portal_access_rules", []):
            try:
                await self.db.portalaccessrule.create(data=rel)
                imported += 1
            except:
                failed += 1
        
        return {"imported": imported, "failed": failed}
    
    async def _restore_access_logs(self, logs: List[Dict]) -> Dict:
        """Restaura logs de acesso"""
        imported = 0
        failed = 0
        
        for log_data in logs:
            try:
                await self.db.accesslog.create(data=log_data)
                imported += 1
            except:
                failed += 1
        
        return {"imported": imported, "failed": failed}
    
    def _decompress_backup(self, compressed_data: bytes) -> str:
        """Descompacta backup ZIP"""
        buffer = io.BytesIO(compressed_data)
        
        with zipfile.ZipFile(buffer, 'r') as zf:
            # Pegar primeiro arquivo JSON
            json_files = [f for f in zf.namelist() if f.endswith('.json')]
            if not json_files:
                raise ValueError("Nenhum arquivo JSON encontrado no ZIP")
            
            return zf.read(json_files[0]).decode('utf-8')
    
    async def _clear_database(self):
        """Limpa todas as tabelas do banco"""
        # Ordem importante por causa das foreign keys
        await self.db.accesslog.delete_many()
        await self.db.useraccessrule.delete_many()
        await self.db.usergroup.delete_many()
        await self.db.groupaccessrule.delete_many()
        await self.db.accessruletimezone.delete_many()
        await self.db.portalaccessrule.delete_many()
        
        await self.db.card.delete_many()
        await self.db.qrcode.delete_many()
        await self.db.template.delete_many()
        await self.db.timespan.delete_many()
        
        await self.db.user.delete_many()
        await self.db.accessrule.delete_many()
        await self.db.timezone.delete_many()
        await self.db.group.delete_many()
        await self.db.portal.delete_many()
    
    # ==================== UTILITIES ====================
    
    async def list_backups(self, backup_dir: Path) -> List[Dict]:
        """Lista backups disponíveis em um diretório"""
        if not backup_dir.exists():
            return []
        
        backups = []
        for file in backup_dir.glob("idface_backup_*.json"):
            stat = file.stat()
            backups.append({
                "filename": file.name,
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        
        return sorted(backups, key=lambda x: x["created_at"], reverse=True)
    
    async def validate_backup(self, backup_data: str) -> Dict[str, Any]:
        """Valida estrutura de um backup"""
        try:
            data = json.loads(backup_data)
            
            required_fields = ["metadata", "data"]
            missing_fields = [f for f in required_fields if f not in data]
            
            if missing_fields:
                return {
                    "valid": False,
                    "errors": [f"Campo obrigatório ausente: {f}" for f in missing_fields]
                }
            
            metadata = data["metadata"]
            data_content = data["data"]
            
            # Contar registros
            counts = {
                "users": len(data_content.get("users", [])),
                "access_rules": len(data_content.get("access_rules", [])),
                "time_zones": len(data_content.get("time_zones", [])),
                "groups": len(data_content.get("groups", [])),
                "portals": len(data_content.get("portals", []))
            }
            
            return {
                "valid": True,
                "metadata": metadata,
                "record_counts": counts
            }
            
        except json.JSONDecodeError:
            return {
                "valid": False,
                "errors": ["JSON inválido"]
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)]
            }