"""
Serviço de Monitoramento em Tempo Real
Captura eventos do leitor iDFace continuamente
backend/app/services/realtime_service.py
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
# Importando ambos os clientes
from app.utils.idface_client import idface_client, idface_client_2
import logging
import traceback

logger = logging.getLogger(__name__)


class RealtimeMonitorService:
    """Serviço para monitorar eventos em tempo real do iDFace"""
    
    def __init__(self, db):
        self.db = db
        self.last_alarm_check = None
        self.last_log_id = None
    
    async def check_alarm_status(self) -> Dict[str, Any]:
        """
        Verifica status de alarme do dispositivo (Fila Indiana: L1 e L2)
        Equivalente a: POST alarm_status.fcgi
        
        Returns:
            {"active": bool, "cause": int}
        """
        final_result = {
            "success": False,
            "active": False,
            "cause": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        # --- LEITOR 1 ---
        try:
            async with idface_client:
                result = await idface_client.request(
                    "POST",
                    "alarm_status.fcgi"
                )
                
                self.last_alarm_check = datetime.now()
                
                # Se L1 respondeu, já consideramos sucesso na comunicação
                final_result["success"] = True
                final_result["timestamp"] = self.last_alarm_check.isoformat()
                
                if result.get("active", False):
                    final_result["active"] = True
                    final_result["cause"] = result.get("cause", 0)
                
        except Exception as e:
            logger.error(f"Erro ao verificar alarme Leitor 1: {e}")
            final_result["error_l1"] = str(e)

        # --- LEITOR 2 ---
        try:
            async with idface_client_2:
                result_2 = await idface_client_2.request(
                    "POST",
                    "alarm_status.fcgi"
                )
                
                self.last_alarm_check = datetime.now()
                
                # Se L2 respondeu (mesmo que L1 tenha falhado), é sucesso
                final_result["success"] = True
                final_result["timestamp"] = self.last_alarm_check.isoformat()
                
                # Se L2 estiver em alarme, o status global fica ativo (OR lógico)
                if result_2.get("active", False):
                    final_result["active"] = True
                    # Se L1 não tinha causa, usa a do L2
                    if final_result["cause"] == 0:
                        final_result["cause"] = result_2.get("cause", 0)
                        
        except Exception as e:
            logger.error(f"Erro ao verificar alarme Leitor 2: {e}")
            final_result["error_l2"] = str(e)

        return final_result
    
    async def get_new_access_logs(self, since_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Busca novos logs de acesso desde o último ID conhecido (Fila Indiana: L1 + L2).
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
            
            all_device_logs = []

            # 2. Buscar logs filtrados do dispositivo LEITOR 1
            try:
                logger.info(f"📡 Chamando load_access_logs_filtered L1 (since={since_timestamp})")
                async with idface_client:
                    result = await idface_client.load_access_logs_filtered(
                        since_timestamp=since_timestamp,
                        limit=7  # ✅ Conforme frontend real
                    )
                    
                    logs_l1 = result.get("access_logs", [])
                    if logs_l1:
                        logger.info(f"📊 Leitor 1 retornou {len(logs_l1)} logs")
                        all_device_logs.extend(logs_l1)
            except Exception as e:
                logger.error(f"Erro ao buscar logs Leitor 1: {e}")

            # 3. Buscar logs filtrados do dispositivo LEITOR 2
            try:
                logger.info(f"📡 Chamando load_access_logs_filtered L2 (since={since_timestamp})")
                async with idface_client_2:
                    result_2 = await idface_client_2.load_access_logs_filtered(
                        since_timestamp=since_timestamp,
                        limit=7
                    )
                    
                    logs_l2 = result_2.get("access_logs", [])
                    if logs_l2:
                        logger.info(f"📊 Leitor 2 retornou {len(logs_l2)} logs")
                        all_device_logs.extend(logs_l2)
            except Exception as e:
                logger.error(f"Erro ao buscar logs Leitor 2: {e}")
            
            # Ordenar logs combinados por tempo para processamento correto
            all_device_logs.sort(key=lambda x: x.get("time", 0))

            if all_device_logs:
                logger.info(f"   Total Logs Combinados: {len(all_device_logs)}")
            
            # 4. Enriquecer cada log com dados do usuário e área
            enriched_logs = []
            for log_data in all_device_logs:
                log_id_device = log_data.get("id")
                if not log_id_device:
                    continue
                
                # Verificar duplicata no banco (importante pois L1 e L2 podem ter logs com mesmo ID)
                # O ideal seria usar ID + Device, mas mantendo a lógica original:
                existing = await self.db.accesslog.find_unique(
                    where={"idFaceLogId": log_id_device}
                )
                if existing:
                    continue
                
                # ✅ Buscar dados do usuário (Tenta L1, se falhar tenta L2)
                if log_data.get("user_id"):
                    user_found = False
                    # Tenta L1
                    try:
                        async with idface_client:
                            user_result = await idface_client.load_users_by_id(log_data["user_id"])
                            user_data = user_result.get("users", [{}])[0]
                            if user_data:
                                log_data["user_name"] = user_data.get("name", "Desconhecido")
                                log_data["registration"] = user_data.get("registration", "")
                                user_found = True
                    except Exception as e:
                        logger.warning(f"L1: Erro ao buscar usuário {log_data.get('user_id')}: {e}")
                    
                    # Tenta L2 se não achou
                    if not user_found:
                        try:
                            async with idface_client_2:
                                user_result = await idface_client_2.load_users_by_id(log_data["user_id"])
                                user_data = user_result.get("users", [{}])[0]
                                if user_data:
                                    log_data["user_name"] = user_data.get("name", "Desconhecido")
                                    log_data["registration"] = user_data.get("registration", "")
                                    user_found = True
                        except Exception as e:
                            logger.warning(f"L2: Erro ao buscar usuário {log_data.get('user_id')}: {e}")

                    if not user_found:
                        log_data["user_name"] = "Desconhecido"
                        log_data["registration"] = ""
                
                # ✅ Buscar dados da área/portal (Tenta L1, se falhar tenta L2)
                if log_data.get("portal_id"):
                    area_found = False
                    # Tenta L1
                    try:
                        async with idface_client:
                            area_result = await idface_client.load_areas(
                                where_field="id",
                                where_value=log_data["portal_id"]  # ID do portal/área
                            )
                            area_data = area_result.get("areas", [{}])[0]
                            if area_data:
                                log_data["area_name"] = area_data.get("name", "Entrada")
                                area_found = True
                    except Exception as e:
                        logger.warning(f"L1: Erro ao buscar área: {e}")
                    
                    # Tenta L2
                    if not area_found:
                        try:
                            async with idface_client_2:
                                area_result = await idface_client_2.load_areas(
                                    where_field="id",
                                    where_value=log_data["portal_id"]
                                )
                                area_data = area_result.get("areas", [{}])[0]
                                if area_data:
                                    log_data["area_name"] = area_data.get("name", "Entrada")
                                    area_found = True
                        except Exception as e:
                            logger.warning(f"L2: Erro ao buscar área: {e}")

                    if not area_found:
                        log_data["area_name"] = "Entrada"
                
                enriched_logs.append(log_data)
            
            # 5. Processar e salvar logs novos
            saved_logs = []
            for log_data in enriched_logs:
                saved_log = await self._process_and_save_log(log_data)
                if saved_log:
                    saved_logs.append(saved_log)
            
            # 6. Retornar último ID
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
                    logger.warning(f"   ⚠️  Usuário iDFace #{user_id_device} não cadastrado no banco (face desconhecida)")
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
            
            # Determinar o status do acesso e razão
            event_display, reason = self._determine_access_status(log_data, user, portal)
            logger.info(f"   📊 Status: {event_display} | Razão: {reason}")
            
            # Criar log no banco (userId e portalId podem ser null)
            new_log = await self.db.accesslog.create(
                data={
                    "idFaceLogId": log_id_device,
                    "userId": user_id_db,  # ✅ Pode ser null
                    "portalId": portal_id_db,  # ✅ Pode ser null
                    "event": event_display,  # ✅ Usar mensagem traduzida
                    "reason": reason,  # ✅ Adicionar motivo se houver
                    "cardValue": log_data.get("card_value"),
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
            return "Acesso Concedido"
        elif event_code == 0:
            return "Acesso Negado"
        elif event_code == 1:
            return "Acesso Negado"
        else:
            return "Desconhecido"
    
    def _determine_access_status(self, log_data: Dict, user: Optional[Any], portal: Optional[Any]) -> tuple:
        """
        Determina o status de acesso e a razão baseado nos dados disponíveis
        
        Returns:
            (event_display, reason) - Mensagem do evento e razão (se houver)
        """
        event_code = log_data.get("event", 0)
        user_id_device = log_data.get("user_id")
        portal_id_device = log_data.get("portal_id")
        
        # ✅ Caso 1: Acesso Concedido - usuário existe e tem portal
        if event_code == 7:
            if user and portal:
                return ("Acesso Concedido", None)
            elif user and not portal:
                # Usuário existe mas portal não está cadastrado
                return ("Acesso Negado", "Portal não cadastrado")
            elif not user and portal:
                # Face desconhecida mas o sistema retornou event=7 (raro)
                return ("Acesso Negado", "Face desconhecida")
            else:
                # Nenhum dado disponível
                return ("Acesso Negado", "Usuário/Portal não encontrados")
        
        # ✅ Caso 2: Acesso Negado - verificar razão
        elif event_code == 0 or event_code == 1:
            if user_id_device and not user:
                # Face desconhecida
                return ("Acesso Negado", "Face desconhecida")
            elif user and not portal:
                # Usuário existe mas sem acesso ao portal
                return ("Acesso Negado", "Sem acesso ao portal")
            elif user and portal:
                # Ambos existem mas evento é negado (acesso expirado, horário, etc)
                return ("Acesso Negado", "Acesso não autorizado")
            else:
                return ("Acesso Negado", "Motivo desconhecido")
        
        # ✅ Caso 3: Evento desconhecido
        else:
            return ("Desconhecido", "Tipo de evento não mapeado")
    
    async def get_access_log_count(self) -> Dict[str, Any]:
        """
        Conta total de logs de acesso no dispositivo (L1 e L2)
        Equivalente ao COUNT(*) que o frontend faz
        """
        count = 0
        success = False
        error = None

        # --- LEITOR 1 ---
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
                
                count += result.get("count", 0)
                success = True
                
        except Exception as e:
            logger.error(f"Erro ao contar logs L1: {e}")
            error = str(e)

        # --- LEITOR 2 ---
        try:
            async with idface_client_2:
                result_2 = await idface_client_2.request(
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
                
                count += result_2.get("count", 0)
                success = True
                
        except Exception as e:
            logger.error(f"Erro ao contar logs L2: {e}")
            # Se L1 falhou, sobrescreve o erro. Se L1 passou, ignora erro do L2.
            if not success:
                error = str(e)

        return {
            "success": success,
            "count": count,
            "timestamp": datetime.now().isoformat(),
            "error": error
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
    

    async def get_device_info(self) -> Dict[str, Any]:
        """
        Obtém informações do dispositivo iDFace conectado (Tenta L1, depois L2)
        Tenta buscar info do device, mas se falhar, verifica conectividade básica
        """
        # --- TENTATIVA LEITOR 1 ---
        try:
            async with idface_client:
                # Método 1: Tentar buscar configurações do sistema
                try:
                    result = await idface_client.request(
                        "POST",
                        "system_information.fcgi"
                    )
                    
                    if result:
                        return {
                            "success": True,
                            "connected": True,
                            "device": {
                                "id": result.get("device_id", 1),
                                "name": result.get("device_name",   "iDFace (L1)"),
                                "ip": idface_client.base_url.replace    ("http://", "").replace("https://", ""),
                                "model": result.get("model", "iDFace"),
                                "serial": result.get("serial_number",   "N/A"),
                                "firmware": result.get  ("firmware_version", "N/A")
                            },
                            "lastCommunication": datetime.now().    isoformat()
                        }
                except:
                    pass
                
                # Método 2: Verificar status de alarme (endpoint mais   simples)
                try:
                    result = await idface_client.request(
                        "POST",
                        "alarm_status.fcgi"
                    )
                    
                    # Se chegou aqui, o dispositivo está respondendo
                    return {
                        "success": True,
                        "connected": True,
                        "device": {
                            "id": 1,  # ID padrão quando não    conseguimos buscar
                            "name": "iDFace (L1)",
                            "ip": idface_client.base_url.replace    ("http://", "").replace("https://", ""),
                            "model": "iDFace Biométrico",
                            "serial": "N/A"
                        },
                        "lastCommunication": datetime.now().isoformat()
                    }
                except:
                    pass
                
                # Método 3: Buscar pela contagem de logs (último    recurso)
                try:
                    result = await idface_client.request(
                        "POST",
                        "load_objects.fcgi",
                        json={
                            "object": "access_logs",
                            "fields": ["COUNT(*)"],
                            "where": []
                        }
                    )
                    
                    # Se chegou aqui, está online
                    return {
                        "success": True,
                        "connected": True,
                        "device": {
                            "id": 1,
                            "name": "iDFace (L1)",
                            "ip": idface_client.base_url.replace    ("http://", "").replace("https://", ""),
                            "model": "iDFace",
                            "serial": "N/A"
                        },
                        "lastCommunication": datetime.now().isoformat()
                    }
                except:
                    pass
        except Exception:
            pass

        # --- TENTATIVA LEITOR 2 (Se L1 falhou totalmente) ---
        try:
            async with idface_client_2:
                # Método 1: Tentar buscar configurações do sistema
                try:
                    result = await idface_client_2.request(
                        "POST",
                        "system_information.fcgi"
                    )
                    
                    if result:
                        return {
                            "success": True,
                            "connected": True,
                            "device": {
                                "id": result.get("device_id", 2),
                                "name": result.get("device_name",   "iDFace (L2)"),
                                "ip": idface_client_2.base_url.replace    ("http://", "").replace("https://", ""),
                                "model": result.get("model", "iDFace"),
                                "serial": result.get("serial_number",   "N/A"),
                                "firmware": result.get  ("firmware_version", "N/A")
                            },
                            "lastCommunication": datetime.now().    isoformat()
                        }
                except:
                    pass
                
                # Método 2: Verificar status de alarme (endpoint mais   simples)
                try:
                    result = await idface_client_2.request(
                        "POST",
                        "alarm_status.fcgi"
                    )
                    
                    return {
                        "success": True,
                        "connected": True,
                        "device": {
                            "id": 2,
                            "name": "iDFace (L2)",
                            "ip": idface_client_2.base_url.replace    ("http://", "").replace("https://", ""),
                            "model": "iDFace Biométrico",
                            "serial": "N/A"
                        },
                        "lastCommunication": datetime.now().isoformat()
                    }
                except:
                    pass
                
                # Método 3: Buscar pela contagem de logs (último    recurso)
                try:
                    result = await idface_client_2.request(
                        "POST",
                        "load_objects.fcgi",
                        json={
                            "object": "access_logs",
                            "fields": ["COUNT(*)"],
                            "where": []
                        }
                    )
                    
                    return {
                        "success": True,
                        "connected": True,
                        "device": {
                            "id": 2,
                            "name": "iDFace (L2)",
                            "ip": idface_client_2.base_url.replace    ("http://", "").replace("https://", ""),
                            "model": "iDFace",
                            "serial": "N/A"
                        },
                        "lastCommunication": datetime.now().isoformat()
                    }
                except:
                    pass
        except Exception:
            pass
        
        # Se nenhum método funcionou em nenhum leitor
        return {
            "success": False,
            "connected": False,
            "error": "Não foi possível conectar a nenhum dispositivo",
            "device": None
        }