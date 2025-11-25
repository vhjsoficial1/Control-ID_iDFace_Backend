"""
Serviço de Monitoramento em Tempo Real
Captura eventos do leitor iDFace continuamente
backend/app/services/realtime_service.py
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.utils.idface_client import idface_client
import logging

logger = logging.getLogger(__name__)


class RealtimeMonitorService:
    """Serviço para monitorar eventos em tempo real do iDFace"""
    
    def __init__(self, db):
        self.db = db
        self.last_alarm_check = None
        self.last_log_id = None
    
    async def check_alarm_status(self) -> Dict[str, Any]:
        """
        Verifica status de alarme do dispositivo
        Equivalente a: POST alarm_status.fcgi
        
        Returns:
            {"active": bool, "cause": int}
        """
        try:
            async with idface_client:
                result = await idface_client.request(
                    "POST",
                    "alarm_status.fcgi"
                )
                
                self.last_alarm_check = datetime.now()
                
                return {
                    "success": True,
                    "active": result.get("active", False),
                    "cause": result.get("cause", 0),
                    "timestamp": self.last_alarm_check.isoformat()
                }
                
        except Exception as e:
            logger.error(f"Erro ao verificar alarme: {e}")
            return {
                "success": False,
                "error": str(e),
                "active": False,
                "cause": 0
            }
    
    async def get_new_access_logs(self, since_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Busca novos logs de acesso desde o último ID conhecido.
        Segue o padrão EXATO da API iDFace conforme capturas de rede real.
        
        Args:
            since_id: ID do último log processado no nosso banco
        
        Returns:
            Dict com novos logs, contagem e último ID processado
        """
        try:
            # 1. Determinar timestamp de corte
            since_timestamp = 0
            if since_id:
                last_log = await self.db.accesslog.find_unique(
                    where={"id": since_id}
                )
                if last_log:
                    # ⚠️ IMPORTANTE: Subtrair 1 segundo porque a API iDFace retorna
                    # logs com timestamp > since_timestamp (não >=)
                    # Se não subtrairmos, não retorna novos logs com timestamp igual
                    since_timestamp = int(last_log.timestamp.timestamp()) - 1
                    logger.info(f"🔍 Buscando logs desde ID {since_id} (timestamp: {since_timestamp})")
            else:
                logger.info(f"🔍 Primeira busca: buscando TODOS os logs (since_timestamp=0)")
            
            # 2. Buscar logs filtrados do dispositivo
            logger.info(f"📡 Chamando load_access_logs_filtered(since_timestamp={since_timestamp})")
            async with idface_client:
                result = await idface_client.load_access_logs_filtered(
                    since_timestamp=since_timestamp,
                    limit=7  # ✅ Conforme frontend real
                )
                
                device_logs = result.get("access_logs", [])
            
            logger.info(f"📊 Device retornou {len(device_logs)} logs")
            if device_logs:
                logger.info(f"   Primeiros logs: {[l.get('id') for l in device_logs[:3]]}")
            
            # 3. Enriquecer cada log com dados do usuário e área
            enriched_logs = []
            for log_data in device_logs:
                log_id_device = log_data.get("id")
                if not log_id_device:
                    continue
                
                # Verificar duplicata
                existing = await self.db.accesslog.find_unique(
                    where={"idFaceLogId": log_id_device}
                )
                if existing:
                    continue
                
                # ✅ Buscar dados do usuário
                if log_data.get("user_id"):
                    try:
                        async with idface_client:
                            user_result = await idface_client.load_users_by_id(log_data["user_id"])
                            user_data = user_result.get("users", [{}])[0]
                            log_data["user_name"] = user_data.get("name", "Desconhecido")
                            log_data["registration"] = user_data.get("registration", "")
                    except Exception as e:
                        logger.warning(f"Erro ao buscar usuário {log_data.get('user_id')}: {e}")
                        log_data["user_name"] = "Desconhecido"
                        log_data["registration"] = ""
                
                # ✅ Buscar dados da área/portal
                if log_data.get("portal_id"):
                    try:
                        async with idface_client:
                            area_result = await idface_client.load_areas(
                                where_field="id",
                                where_value=log_data["portal_id"]  # ID do portal/área
                            )
                            area_data = area_result.get("areas", [{}])[0]
                            log_data["area_name"] = area_data.get("name", "Entrada")
                    except Exception as e:
                        logger.warning(f"Erro ao buscar área: {e}")
                        log_data["area_name"] = "Entrada"
                
                enriched_logs.append(log_data)
            
            # 4. Processar e salvar logs novos
            saved_logs = []
            for log_data in enriched_logs:
                saved_log = await self._process_and_save_log(log_data)
                if saved_log:
                    saved_logs.append(saved_log)
            
            # 5. Retornar último ID
            last_id = None
            if saved_logs:
                latest = await self.db.accesslog.find_first(
                    order={"id": "desc"}
                )
                if latest:
                    last_id = latest.id
            elif since_id:
                last_id = since_id
            
            return {
                "success": True,
                "newLogs": saved_logs,
                "count": len(saved_logs),
                "lastId": last_id,
                "timestamp": datetime.now().isoformat()
            }
                
        except Exception as e:
            logger.error(f"Erro ao buscar novos logs: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "newLogs": [],
                "count": 0,
                "lastId": since_id
            }
    
    async def _process_and_save_log(self, log_data: Dict) -> Optional[Dict]:
        """
        Processa e salva log no banco local
        Evita duplicatas usando idFaceLogId
        ✅ Corrigido para validar foreign keys antes de criar
        """
        try:
            log_id_device = log_data.get("id")
            if not log_id_device:
                logger.warning("Log sem ID recebido")
                return None
            
            logger.info(f"📝 Processando log #{log_id_device} do device")
            
            # Verificar se já existe
            existing = await self.db.accesslog.find_unique(
                where={"idFaceLogId": log_id_device}
            )
            if existing:
                logger.debug(f"   ⏭️  Log #{log_id_device} já existe no banco")
                return None
            
            # Mapear evento
            event = self._map_event_type(log_data)
            logger.info(f"   📊 Evento: {event}")
            
            # ✅ Converter timestamp Unix para datetime
            unix_timestamp = log_data.get("time", 0)
            if unix_timestamp:
                timestamp = datetime.fromtimestamp(unix_timestamp)
            else:
                timestamp = datetime.now()
            logger.info(f"   🕐 Timestamp: {timestamp.isoformat()}")
            
            # ✅ VALIDAR FOREIGN KEYS: Verificar se usuário existe
            user_id_device = log_data.get("user_id")
            user_id_db = None
            user = None
            
            if user_id_device:
                # Procurar usuário pelo idFaceId
                user = await self.db.user.find_unique(
                    where={"idFaceId": user_id_device}
                )
                if user:
                    user_id_db = user.id
                    logger.info(f"   👤 Usuário encontrado: {user.name} (iDFace #{user_id_device} → DB #{user_id_db})")
                else:
                    # Usuário não existe no banco - deixar como null
                    logger.warning(f"   ⚠️  Usuário iDFace #{user_id_device} não cadastrado no banco")
                    user_id_db = None
            
            # ✅ VALIDAR FOREIGN KEYS: Verificar se portal existe
            portal_id_device = log_data.get("portal_id")
            portal_id_db = None
            portal = None
            
            if portal_id_device:
                # Procurar portal pelo idFaceId
                portal = await self.db.portal.find_unique(
                    where={"idFaceId": portal_id_device}
                )
                if portal:
                    portal_id_db = portal.id
                    logger.info(f"   🚪 Portal encontrado: {portal.name} (iDFace #{portal_id_device} → DB #{portal_id_db})")
                else:
                    # Portal não existe no banco - deixar como null
                    logger.warning(f"   ⚠️  Portal iDFace #{portal_id_device} não cadastrado no banco")
                    portal_id_db = None
            
            # Criar log no banco (userId e portalId podem ser null)
            new_log = await self.db.accesslog.create(
                data={
                    "idFaceLogId": log_id_device,
                    "userId": user_id_db,  # ✅ Pode ser null
                    "portalId": portal_id_db,  # ✅ Pode ser null
                    "event": event,
                    "reason": None,
                    "cardValue": None,
                    "timestamp": timestamp
                }
            )
            
            logger.info(f"   ✅ Log salvo com sucesso! ID no banco: {new_log.id}")
            
            # Retornar formatado
            return {
                "id": new_log.id,
                "idFaceLogId": new_log.idFaceLogId,
                "userId": new_log.userId,
                "userName": user.name if user else log_data.get("user_name", "Desconhecido"),
                "portalId": new_log.portalId,
                "portalName": portal.name if portal else log_data.get("area_name", "Entrada"),
                "event": new_log.event,
                "timestamp": new_log.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar log: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _map_event_type(self, log_data: Dict) -> str:
        """
        Mapeia tipo de evento do iDFace para nosso sistema
        ✅ Baseado em dados REAIS do frontend:
        - event = 7: Acesso normal/autorizado
        - event = 0: Acesso negado
        - log_type_id = -1: Tipo genérico
        """
        event_code = log_data.get("event", 0)
        
        # ✅ Mapear baseado em dados reais
        if event_code == 7:
            return "access_granted"
        elif event_code == 0:
            return "access_denied"
        elif event_code == 1:
            return "access_denied"
        else:
            return "unknown"
    
    async def get_access_log_count(self) -> Dict[str, Any]:
        """
        Conta total de logs de acesso no dispositivo
        Equivalente ao COUNT(*) que o frontend faz
        """
        try:
            async with idface_client:
                result = await idface_client.request(
                    "POST",
                    "load_objects.fcgi",
                    json={
                        "join": "LEFT",
                        "object": "access_logs",
                        "fields": ["COUNT(*)"],
                        "where": [],
                        "order": ["id"],
                        "offset": 0
                    }
                )
                
                count = result.get("count", 0)
                
                return {
                    "success": True,
                    "count": count,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Erro ao contar logs: {e}")
            return {
                "success": False,
                "error": str(e),
                "count": 0
            }
    
    async def get_recent_activity(self, minutes: int = 5) -> Dict[str, Any]:
        """
        Retorna atividade recente (últimos X minutos)
        Combina dados do banco local
        """
        since = datetime.now() - timedelta(minutes=minutes)
        
        try:
            logs = await self.db.accesslog.find_many(
                where={
                    "timestamp": {"gte": since}
                },
                include={
                    "user": True,
                    "portal": True
                },
                order={"timestamp": "desc"}
            )
            
            formatted_logs = [
                {
                    "id": log.id,
                    "event": log.event,
                    "userName": log.user.name if log.user else "Desconhecido",
                    "portalName": log.portal.name if log.portal else "N/A",
                    "timestamp": log.timestamp.isoformat(),
                    "reason": log.reason
                }
                for log in logs
            ]
            
            return {
                "success": True,
                "logs": formatted_logs,
                "count": len(formatted_logs),
                "period": f"Últimos {minutes} minutos"
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar atividade recente: {e}")
            return {
                "success": False,
                "error": str(e),
                "logs": [],
                "count": 0
            }
    
    async def monitor_full_status(self, since_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Retorna status completo do sistema em tempo real
        Combina alarme + logs recentes + estatísticas
        """
        # Buscar dados em paralelo
        alarm_status = await self.check_alarm_status()
        new_logs = await self.get_new_access_logs(since_id)
        log_count = await self.get_access_log_count()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "alarm": {
                "active": alarm_status.get("active", False),
                "cause": alarm_status.get("cause", 0)
            },
            "logs": {
                "newCount": new_logs.get("count", 0),
                "totalCount": log_count.get("count", 0),
                "lastId": new_logs.get("lastId"),
                "newlyFound": new_logs.get("newLogs", [])
            },
            "deviceStatus": "online" if alarm_status.get("success") else "offline"
        }