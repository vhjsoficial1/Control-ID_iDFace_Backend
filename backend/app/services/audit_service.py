"""
Serviço de lógica de negócio para auditoria e logs de acesso
Contém operações complexas de análise e relatórios de auditoria
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import logging
import csv
import json
from io import StringIO

logger = logging.getLogger(__name__)


class AuditService:
    """Serviço para gerenciar logs de auditoria e análises"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== Log Management ====================
    
    async def create_access_log(
        self,
        user_id: Optional[int] = None,
        portal_id: Optional[int] = None,
        event: str = "unknown",
        reason: Optional[str] = None,
        card_value: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Cria um registro de log de acesso
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Validações básicas
        valid_events = [
            "access_granted",
            "access_denied",
            "unknown_user",
            "invalid_credential",
            "expired_access",
            "time_restriction",
            "door_forced",
            "door_left_open"
        ]
        
        if event not in valid_events:
            logger.warning(f"Evento desconhecido: {event}")
        
        try:
            log = await self.db.accesslog.create(
                data={
                    "userId": user_id,
                    "portalId": portal_id,
                    "event": event,
                    "reason": reason,
                    "cardValue": card_value,
                    "timestamp": timestamp
                }
            )
            
            logger.info(f"Log de acesso criado: ID {log.id}, Evento: {event}")
            
            return {
                "success": True,
                "log": log,
                "message": "Log criado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao criar log de acesso: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def bulk_create_logs(
        self,
        logs_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cria múltiplos logs em batch
        """
        success_count = 0
        failed_count = 0
        errors = []
        
        for log_data in logs_data:
            try:
                await self.db.accesslog.create(data=log_data)
                success_count += 1
            except Exception as e:
                failed_count += 1
                errors.append(str(e))
        
        return {
            "success": failed_count == 0,
            "message": f"{success_count} log(s) criado(s)",
            "successCount": success_count,
            "failedCount": failed_count,
            "errors": errors[:10]
        }
    
    async def delete_old_logs(
        self,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Remove logs mais antigos que X dias
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        try:
            # Contar antes de deletar
            count = await self.db.accesslog.count(
                where={"timestamp": {"lt": cutoff_date}}
            )
            
            # Deletar
            await self.db.accesslog.delete_many(
                where={"timestamp": {"lt": cutoff_date}}
            )
            
            logger.info(f"{count} logs antigos removidos (>{days} dias)")
            
            return {
                "success": True,
                "message": f"{count} logs removidos com sucesso",
                "deletedCount": count,
                "cutoffDate": cutoff_date
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover logs antigos: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Analytics & Statistics ====================
    
    async def get_access_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_id: Optional[int] = None,
        portal_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calcula estatísticas detalhadas de acesso
        """
        where = {}
        
        # Filtros de data
        if start_date or end_date:
            where["timestamp"] = {}
            if start_date:
                where["timestamp"]["gte"] = start_date
            if end_date:
                where["timestamp"]["lte"] = end_date
        
        if user_id:
            where["userId"] = user_id
        
        if portal_id:
            where["portalId"] = portal_id
        
        try:
            logs = await self.db.accesslog.find_many(
                where=where,
                include={"user": True, "portal": True}
            )
            
            total = len(logs)
            
            if total == 0:
                return {
                    "success": True,
                    "statistics": {
                        "total": 0,
                        "byEvent": {},
                        "byHour": {},
                        "byDayOfWeek": {}
                    }
                }
            
            # Estatísticas por evento
            events = Counter(log.event for log in logs)
            by_event = {
                event: {
                    "count": count,
                    "percentage": round((count / total) * 100, 2)
                }
                for event, count in events.items()
            }
            
            # Estatísticas por hora do dia
            hours = Counter(log.timestamp.hour for log in logs)
            by_hour = dict(sorted(hours.items()))
            
            # Estatísticas por dia da semana
            days = Counter(log.timestamp.strftime("%A") for log in logs)
            by_day_of_week = dict(days)
            
            # Períodos de maior movimento
            peak_hour = max(hours.items(), key=lambda x: x[1])
            peak_day = max(days.items(), key=lambda x: x[1])
            
            # Taxa de sucesso
            granted = events.get("access_granted", 0)
            denied = events.get("access_denied", 0)
            success_rate = round((granted / (granted + denied) * 100), 2) if (granted + denied) > 0 else 0
            
            return {
                "success": True,
                "statistics": {
                    "total": total,
                    "dateRange": {
                        "start": min(log.timestamp for log in logs).isoformat(),
                        "end": max(log.timestamp for log in logs).isoformat()
                    },
                    "byEvent": by_event,
                    "byHour": by_hour,
                    "byDayOfWeek": by_day_of_week,
                    "successRate": success_rate,
                    "peakHour": {"hour": peak_hour[0], "count": peak_hour[1]},
                    "peakDay": {"day": peak_day[0], "count": peak_day[1]},
                    "granted": granted,
                    "denied": denied
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def get_user_access_pattern(
        self,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analisa padrão de acesso de um usuário
        """
        start_date = datetime.now() - timedelta(days=days)
        
        try:
            logs = await self.db.accesslog.find_many(
                where={
                    "userId": user_id,
                    "timestamp": {"gte": start_date}
                },
                order_by={"timestamp": "asc"}
            )
            
            if not logs:
                return {
                    "success": True,
                    "pattern": {
                        "totalAccess": 0,
                        "message": "Sem dados no período"
                    }
                }
            
            # Padrão de horários
            hours = [log.timestamp.hour for log in logs]
            avg_hour = sum(hours) / len(hours)
            
            # Dias mais frequentes
            days_of_week = Counter(log.timestamp.strftime("%A") for log in logs)
            most_common_day = days_of_week.most_common(1)[0]
            
            # Frequência de acesso
            total_days = (datetime.now() - start_date).days
            access_frequency = len(logs) / total_days if total_days > 0 else 0
            
            # Horário típico de entrada/saída
            morning_access = [log for log in logs if 6 <= log.timestamp.hour <= 12]
            evening_access = [log for log in logs if 17 <= log.timestamp.hour <= 23]
            
            return {
                "success": True,
                "userId": user_id,
                "pattern": {
                    "totalAccess": len(logs),
                    "periodDays": days,
                    "averageHour": round(avg_hour, 1),
                    "mostCommonDay": most_common_day[0],
                    "accessFrequency": round(access_frequency, 2),
                    "morningAccess": len(morning_access),
                    "eveningAccess": len(evening_access),
                    "typicalSchedule": {
                        "morning": len(morning_access) > 0,
                        "evening": len(evening_access) > 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao analisar padrão de acesso: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def detect_anomalies(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Detecta anomalias nos logs de acesso
        """
        since = datetime.now() - timedelta(hours=hours)
        
        try:
            logs = await self.db.accesslog.find_many(
                where={"timestamp": {"gte": since}},
                include={"user": True, "portal": True}
            )
            
            anomalies = []
            
            # Detectar acessos múltiplos em curto período
            user_access_times = defaultdict(list)
            for log in logs:
                if log.userId:
                    user_access_times[log.userId].append(log.timestamp)
            
            for user_id, times in user_access_times.items():
                times_sorted = sorted(times)
                for i in range(len(times_sorted) - 1):
                    diff = (times_sorted[i + 1] - times_sorted[i]).total_seconds()
                    if diff < 60:  # Menos de 1 minuto entre acessos
                        anomalies.append({
                            "type": "rapid_successive_access",
                            "userId": user_id,
                            "timeDiff": diff,
                            "severity": "medium"
                        })
            
            # Detectar acessos fora do horário normal
            for log in logs:
                hour = log.timestamp.hour
                if hour < 6 or hour > 22:  # Fora do horário 06:00-22:00
                    anomalies.append({
                        "type": "unusual_hour_access",
                        "userId": log.userId,
                        "hour": hour,
                        "timestamp": log.timestamp.isoformat(),
                        "severity": "low"
                    })
            
            # Detectar tentativas múltiplas de acesso negado
            denied_attempts = defaultdict(int)
            for log in logs:
                if log.event == "access_denied" and log.userId:
                    denied_attempts[log.userId] += 1
            
            for user_id, count in denied_attempts.items():
                if count >= 3:
                    anomalies.append({
                        "type": "multiple_denied_attempts",
                        "userId": user_id,
                        "count": count,
                        "severity": "high"
                    })
            
            # Agrupar por severidade
            by_severity = {
                "high": [a for a in anomalies if a["severity"] == "high"],
                "medium": [a for a in anomalies if a["severity"] == "medium"],
                "low": [a for a in anomalies if a["severity"] == "low"]
            }
            
            return {
                "success": True,
                "period": f"Últimas {hours} horas",
                "totalAnomalies": len(anomalies),
                "anomalies": anomalies[:50],  # Limitar retorno
                "bySeverity": {
                    "high": len(by_severity["high"]),
                    "medium": len(by_severity["medium"]),
                    "low": len(by_severity["low"])
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao detectar anomalias: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Reports ====================
    
    async def generate_access_report(
        self,
        start_date: datetime,
        end_date: datetime,
        user_ids: Optional[List[int]] = None,
        portal_ids: Optional[List[int]] = None,
        events: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Gera relatório detalhado de acessos
        """
        where = {
            "timestamp": {
                "gte": start_date,
                "lte": end_date
            }
        }
        
        if user_ids:
            where["userId"] = {"in": user_ids}
        
        if portal_ids:
            where["portalId"] = {"in": portal_ids}
        
        if events:
            where["event"] = {"in": events}
        
        try:
            logs = await self.db.accesslog.find_many(
                where=where,
                include={
                    "user": True,
                    "portal": True
                },
                order_by={"timestamp": "desc"}
            )
            
            # Estatísticas gerais
            total = len(logs)
            events_count = Counter(log.event for log in logs)
            users_count = len(set(log.userId for log in logs if log.userId))
            portals_count = len(set(log.portalId for log in logs if log.portalId))
            
            # Top usuários
            user_access = Counter(log.userId for log in logs if log.userId)
            top_users = []
            for user_id, count in user_access.most_common(10):
                user_log = next((log for log in logs if log.userId == user_id), None)
                if user_log and user_log.user:
                    top_users.append({
                        "userId": user_id,
                        "userName": user_log.user.name,
                        "accessCount": count
                    })
            
            # Top portais
            portal_access = Counter(log.portalId for log in logs if log.portalId)
            top_portals = []
            for portal_id, count in portal_access.most_common(10):
                portal_log = next((log for log in logs if log.portalId == portal_id), None)
                if portal_log and portal_log.portal:
                    top_portals.append({
                        "portalId": portal_id,
                        "portalName": portal_log.portal.name,
                        "accessCount": count
                    })
            
            return {
                "success": True,
                "report": {
                    "period": {
                        "start": start_date.isoformat(),
                        "end": end_date.isoformat()
                    },
                    "summary": {
                        "totalLogs": total,
                        "uniqueUsers": users_count,
                        "uniquePortals": portals_count,
                        "eventTypes": dict(events_count)
                    },
                    "topUsers": top_users,
                    "topPortals": top_portals,
                    "logs": [
                        {
                            "id": log.id,
                            "timestamp": log.timestamp.isoformat(),
                            "event": log.event,
                            "userName": log.user.name if log.user else None,
                            "portalName": log.portal.name if log.portal else None,
                            "reason": log.reason
                        }
                        for log in logs[:1000]  # Limitar a 1000 registros
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Export ====================
    
    async def export_to_csv(
        self,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Exporta logs para formato CSV
        """
        where = {
            "timestamp": {
                "gte": start_date,
                "lte": end_date
            }
        }
        
        if filters:
            where.update(filters)
        
        try:
            logs = await self.db.accesslog.find_many(
                where=where,
                include={
                    "user": True,
                    "portal": True
                },
                order_by={"timestamp": "desc"}
            )
            
            # Criar CSV em memória
            output = StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                "ID",
                "Timestamp",
                "Event",
                "User ID",
                "User Name",
                "Portal ID",
                "Portal Name",
                "Card Value",
                "Reason"
            ])
            
            # Dados
            for log in logs:
                writer.writerow([
                    log.id,
                    log.timestamp.isoformat(),
                    log.event,
                    log.userId or "",
                    log.user.name if log.user else "",
                    log.portalId or "",
                    log.portal.name if log.portal else "",
                    log.cardValue or "",
                    log.reason or ""
                ])
            
            csv_content = output.getvalue()
            output.close()
            
            return {
                "success": True,
                "format": "csv",
                "recordCount": len(logs),
                "content": csv_content,
                "filename": f"access_logs_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
            }
            
        except Exception as e:
            logger.error(f"Erro ao exportar CSV: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def export_to_json(
        self,
        start_date: datetime,
        end_date: datetime,
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Exporta logs para formato JSON
        """
        where = {
            "timestamp": {
                "gte": start_date,
                "lte": end_date
            }
        }
        
        if filters:
            where.update(filters)
        
        try:
            logs = await self.db.accesslog.find_many(
                where=where,
                include={
                    "user": True,
                    "portal": True
                },
                order_by={"timestamp": "desc"}
            )
            
            # Formatar para JSON
            logs_data = [
                {
                    "id": log.id,
                    "timestamp": log.timestamp.isoformat(),
                    "event": log.event,
                    "user": {
                        "id": log.userId,
                        "name": log.user.name if log.user else None
                    } if log.userId else None,
                    "portal": {
                        "id": log.portalId,
                        "name": log.portal.name if log.portal else None
                    } if log.portalId else None,
                    "cardValue": log.cardValue,
                    "reason": log.reason
                }
                for log in logs
            ]
            
            json_content = json.dumps(logs_data, indent=2, ensure_ascii=False)
            
            return {
                "success": True,
                "format": "json",
                "recordCount": len(logs),
                "content": json_content,
                "filename": f"access_logs_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
            }
            
        except Exception as e:
            logger.error(f"Erro ao exportar JSON: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Compliance & Audit ====================
    
    async def get_compliance_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Gera relatório de conformidade de auditoria
        """
        start_date = datetime.now() - timedelta(days=days)
        
        try:
            total_logs = await self.db.accesslog.count(
                where={"timestamp": {"gte": start_date}}
            )
            
            # Logs sem usuário identificado
            unknown_logs = await self.db.accesslog.count(
                where={
                    "timestamp": {"gte": start_date},
                    "userId": None
                }
            )
            
            # Acessos negados
            denied_logs = await self.db.accesslog.count(
                where={
                    "timestamp": {"gte": start_date},
                    "event": "access_denied"
                }
            )
            
            # Calcularcompliance score
            compliance_score = 100
            
            if total_logs > 0:
                unknown_rate = (unknown_logs / total_logs) * 100
                denied_rate = (denied_logs / total_logs) * 100
                
                # Penalidades
                if unknown_rate > 10:
                    compliance_score -= min(20, unknown_rate)
                
                if denied_rate > 5:
                    compliance_score -= min(10, denied_rate)
            
            compliance_score = max(0, compliance_score)
            
            # Status de conformidade
            if compliance_score >= 90:
                status = "excellent"
            elif compliance_score >= 75:
                status = "good"
            elif compliance_score >= 60:
                status = "acceptable"
            else:
                status = "needs_improvement"
            
            return {
                "success": True,
                "compliance": {
                    "score": round(compliance_score, 2),
                    "status": status,
                    "period": f"Últimos {days} dias",
                    "metrics": {
                        "totalLogs": total_logs,
                        "unknownAccess": unknown_logs,
                        "deniedAccess": denied_logs,
                        "unknownRate": round((unknown_logs / total_logs * 100), 2) if total_logs > 0 else 0,
                        "deniedRate": round((denied_logs / total_logs * 100), 2) if total_logs > 0 else 0
                    },
                    "recommendations": self._generate_compliance_recommendations(
                        compliance_score,
                        unknown_logs,
                        denied_logs
                    )
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao gerar relatório de conformidade: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    def _generate_compliance_recommendations(
        self,
        score: float,
        unknown_count: int,
        denied_count: int
    ) -> List[str]:
        """Gera recomendações baseadas no compliance score"""
        recommendations = []
        
        if score < 90:
            recommendations.append("Revisar políticas de acesso e auditoria")
        
        if unknown_count > 0:
            recommendations.append(
                f"Investigar {unknown_count} acesso(s) sem identificação de usuário"
            )
        
        if denied_count > 10:
            recommendations.append(
                f"Analisar {denied_count} tentativa(s) de acesso negado"
            )
        
        if not recommendations:
            recommendations.append("Sistema em conformidade total")
        
        return recommendations