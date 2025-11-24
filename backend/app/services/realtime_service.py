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
        Segue o padrão EXATO da API iDFace conforme documentação oficial.
        
        Args:
            since_id: ID do último log processado no nosso banco
        
        Returns:
            Dict com novos logs, contagem e último ID processado
        """
        try:
            async with idface_client:
                # Carregar todos os logs do dispositivo
                result = await idface_client.load_access_logs()
                all_logs = result.get("access_logs", [])
                
                # Filtrar logs novos baseado no since_id
                new_logs = []
                if since_id is None:
                    # Primeira chamada: retornar vazio
                    new_logs = []
                else:
                    # Filtrar logs que foram salvos após o since_id
                    last_log_in_db = await self.db.accesslog.find_unique(where={"id": since_id})
                    if last_log_in_db:
                        # Retornar apenas logs posteriores ao timestamp do último processado
                        for log in all_logs:
                            try:
                                log_timestamp = log.get("time", 0)
                                if log_timestamp > last_log_in_db.timestamp.timestamp():
                                    new_logs.append(log)
                            except Exception as e:
                                logger.warning(f"Erro ao processar timestamp do log: {e}")
                                continue
                
                # Processar e salvar logs novos
                saved_logs = []
                for log_data in new_logs:
                    saved_log = await self._process_and_save_log(log_data)
                    if saved_log:
                        saved_logs.append(saved_log)
                
                # Atualizar o último ID processado
                if saved_logs:
                    last_saved = await self.db.accesslog.find_first(
                        order={"id": "desc"}
                    )
                    if last_saved:
                        self.last_log_id = last_saved.id
                
                return {
                    "success": True,
                    "newLogs": saved_logs,
                    "count": len(saved_logs),
                    "totalCount": len(all_logs),
                    "lastId": self.last_log_id,
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
                "count": 0
            }
    
    async def _process_and_save_log(self, log_data: Dict) -> Optional[Dict]:
        """
        Processa e salva log no banco local
        Evita duplicatas usando o ID do log do dispositivo
        """
        try:
            log_id_from_device = log_data.get("id")
            if not log_id_from_device:
                return None # Ignorar se não houver ID

            # Verificar se o log do dispositivo já existe
            existing = await self.db.accesslog.find_unique(
                where={"idFaceLogId": log_id_from_device}
            )
            
            if existing:
                return None  # Já existe
            
            # Determinar evento baseado nos dados do iDFace
            event = self._map_event_type(log_data)
            
            # Criar log
            new_log = await self.db.accesslog.create(
                data={
                    "idFaceLogId": log_id_from_device,
                    "userId": log_data.get("user_id"),
                    "portalId": log_data.get("portal_id"),
                    "event": event,
                    "reason": log_data.get("reason"),
                    "cardValue": str(log_data.get("card_value")) if log_data.get("card_value") else None,
                    "timestamp": log_data.get("time", datetime.now())
                }
            )
            
            # Retornar log formatado para o frontend
            user = await self.db.user.find_unique(where={"id": new_log.userId}) if new_log.userId else None
            portal = await self.db.portal.find_unique(where={"id": new_log.portalId}) if new_log.portalId else None
            
            return {
                "id": new_log.id,
                "userId": new_log.userId,
                "userName": user.name if user else "Desconhecido",
                "portalId": new_log.portalId,
                "portalName": portal.name if portal else "N/A",
                "event": new_log.event,
                "reason": new_log.reason,
                "cardValue": new_log.cardValue,
                "timestamp": new_log.timestamp.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erro ao processar log: {e}")
            return None
    
    def _map_event_type(self, log_data: Dict) -> str:
        """
        Mapeia tipo de evento do iDFace para nosso sistema
        """
        # Mapear códigos do iDFace para eventos legíveis
        event_code = log_data.get("event", 0)
        
        event_map = {
            0: "access_granted",
            1: "access_denied",
            2: "unknown_user",
            3: "invalid_credential",
            4: "expired_access",
            5: "time_restriction",
            6: "door_forced",
            7: "door_left_open"
        }
        
        return event_map.get(event_code, "unknown")
    
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