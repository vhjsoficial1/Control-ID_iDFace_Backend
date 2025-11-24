"""
Teste de Monitoramento em Tempo Real - Backend iDFace
Monitora passagens no leitor a cada 2 segundos
Execução: python realtime_monitor_test.py
"""

import asyncio
import httpx
import json
from datetime import datetime
from typing import Optional, Dict, Any
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
POLLING_INTERVAL = 2  # segundos


class RealtimeMonitorTest:
    """Teste de monitoramento em tempo real"""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=10.0)
        self.last_log_id: Optional[int] = None
        self.running = False
        self.iteration = 0
        
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    # ==================== Testes Individuais ====================
    
    async def test_alarm_status(self) -> Dict[str, Any]:
        """
        Testa: GET /api/v1/realtime/alarm-status
        Verifica status de alarme do dispositivo
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/realtime/alarm-status"
            )
            response.raise_for_status()
            
            data = response.json()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def test_new_logs(self, since_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Testa: GET /api/v1/realtime/new-logs
        Busca novos logs desde o último ID
        """
        try:
            params = {}
            if since_id is not None:
                params["since_id"] = since_id
            
            response = await self.client.get(
                f"{self.base_url}/api/v1/realtime/new-logs",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Atualizar last_log_id se houver
            if isinstance(data, dict) and "lastId" in data:
                self.last_log_id = data["lastId"]
            
            return {
                "success": True,
                "status_code": response.status_code,
                "data": data,
                "new_logs_count": len(data.get("logs", [])) if isinstance(data, dict) else len(data) if isinstance(data, list) else 0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def test_log_count(self) -> Dict[str, Any]:
        """
        Testa: GET /api/v1/realtime/log-count
        Retorna contagem total de logs
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/realtime/log-count"
            )
            response.raise_for_status()
            
            data = response.json()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def test_recent_activity(self, minutes: int = 5) -> Dict[str, Any]:
        """
        Testa: GET /api/v1/realtime/recent-activity
        Retorna atividade recente (últimos X minutos)
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/realtime/recent-activity",
                params={"minutes": minutes}
            )
            response.raise_for_status()
            
            data = response.json()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def test_monitor_full(self) -> Dict[str, Any]:
        """
        Testa: GET /api/v1/realtime/monitor
        Retorna status completo do sistema (endpoint otimizado)
        """
        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/realtime/monitor"
            )
            response.raise_for_status()
            
            data = response.json()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": data
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    # ==================== Processamento de Logs ====================
    
    def process_log(self, log: Dict) -> None:
        """Processa e exibe um log de passagem"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Extrair informações
        user_name = log.get("userName", log.get("name", "Desconhecido"))
        user_id = log.get("userId", log.get("id", "N/A"))
        event = log.get("event", "unknown")
        log_time = log.get("timestamp", timestamp)
        
        # Determinar status
        if event in ["access_granted", "authorized"]:
            status_icon = "✅"
            status_text = "ACESSO AUTORIZADO"
        elif event in ["access_denied", "denied", "unauthorized"]:
            status_icon = "❌"
            status_text = "ACESSO NEGADO"
        else:
            status_icon = "⚠️"
            status_text = "STATUS DESCONHECIDO"
        
        print(f"\n{status_icon} [{log_time}] {status_text}")
        print(f"   👤 Usuário: {user_name} (ID: {user_id})")
        print(f"   📊 Evento: {event}")
        
        # Informações adicionais
        if "reason" in log and log["reason"]:
            print(f"   📝 Motivo: {log['reason']}")
        if "portalName" in log:
            print(f"   🚪 Portal: {log['portalName']}")
        if "cardValue" in log and log["cardValue"]:
            print(f"   💳 Cartão: {log['cardValue']}")
    
    # ==================== Modo de Monitoramento Otimizado ====================
    
    async def run_optimized_monitoring(self, interval: int = POLLING_INTERVAL):
        """
        Modo otimizado: usa endpoint /monitor (recomendado)
        Faz polling a cada X segundos
        """
        print("=" * 70)
        print("🚀 MONITORAMENTO EM TEMPO REAL - MODO OTIMIZADO")
        print("=" * 70)
        print(f"⏱️  Polling a cada {interval} segundos")
        print(f"🔗 Endpoint: {self.base_url}/api/v1/realtime/monitor")
        print(f"💡 Pressione Ctrl+C para parar")
        print("=" * 70)
        
        self.running = True
        
        try:
            while self.running:
                self.iteration += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                print(f"\n🔄 Iteração #{self.iteration} - {timestamp}")
                
                # Chamar endpoint de monitoramento completo
                result = await self.test_monitor_full()
                
                if result["success"]:
                    data = result["data"]
                    
                    # Processar novos logs
                    if "logs" in data and "newCount" in data["logs"]:
                        new_count = data["logs"]["newCount"]
                        
                        if new_count > 0:
                            print(f"\n🔔 {new_count} nova(s) passagem(ns) detectada(s)!")
                            
                            # Exibir logs recentes
                            recent_logs = data["logs"].get("recent", [])
                            for log in recent_logs:
                                self.process_log(log)
                        else:
                            print("   ⏳ Sem novas passagens")
                    
                    # Exibir status do dispositivo
                    device_status = data.get("deviceStatus", "unknown")
                    status_icon = "🟢" if device_status == "online" else "🔴"
                    print(f"   {status_icon} Dispositivo: {device_status}")
                    
                    # Exibir alarme se ativo
                    if "alarm" in data and data["alarm"].get("active"):
                        print(f"   🚨 ALARME ATIVO! Causa: {data['alarm'].get('cause')}")
                else:
                    print(f"   ❌ Erro: {result.get('error')}")
                
                # Aguardar próxima iteração
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n\n⛔ Monitoramento interrompido pelo usuário")
            self.running = False
    
    # ==================== Modo de Monitoramento Individual ====================
    
    async def run_individual_monitoring(self, interval: int = POLLING_INTERVAL):
        """
        Modo individual: usa endpoints separados
        Útil para debug e testes
        """
        print("=" * 70)
        print("🚀 MONITORAMENTO EM TEMPO REAL - MODO INDIVIDUAL")
        print("=" * 70)
        print(f"⏱️  Polling a cada {interval} segundos")
        print(f"💡 Pressione Ctrl+C para parar")
        print("=" * 70)
        
        self.running = True
        
        try:
            while self.running:
                self.iteration += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                print(f"\n{'='*70}")
                print(f"🔄 Iteração #{self.iteration} - {timestamp}")
                print("="*70)
                
                # 1. Verificar novos logs
                print("\n📋 Verificando novos logs...")
                logs_result = await self.test_new_logs(self.last_log_id)
                
                if logs_result["success"]:
                    new_count = logs_result.get("new_logs_count", 0)
                    
                    if new_count > 0:
                        print(f"🔔 {new_count} nova(s) passagem(ns)!")
                        
                        data = logs_result["data"]
                        logs = data.get("logs", []) if isinstance(data, dict) else data if isinstance(data, list) else []
                        
                        for log in logs:
                            self.process_log(log)
                    else:
                        print("⏳ Sem novas passagens")
                else:
                    print(f"❌ Erro ao buscar logs: {logs_result.get('error')}")
                
                # 2. Status de alarme (a cada 5 iterações)
                if self.iteration % 5 == 0:
                    print("\n🚨 Verificando alarme...")
                    alarm_result = await self.test_alarm_status()
                    
                    if alarm_result["success"]:
                        alarm_data = alarm_result["data"]
                        is_active = alarm_data.get("active", False)
                        
                        if is_active:
                            print(f"⚠️  ALARME ATIVO! Causa: {alarm_data.get('cause')}")
                        else:
                            print("✅ Alarme inativo")
                    else:
                        print(f"❌ Erro ao verificar alarme: {alarm_result.get('error')}")
                
                # 3. Contagem total (a cada 10 iterações)
                if self.iteration % 10 == 0:
                    print("\n📊 Verificando contagem total...")
                    count_result = await self.test_log_count()
                    
                    if count_result["success"]:
                        count_data = count_result["data"]
                        total = count_data.get("count", 0)
                        print(f"📈 Total de logs no dispositivo: {total}")
                    else:
                        print(f"❌ Erro ao contar logs: {count_result.get('error')}")
                
                # 4. Atividade recente (a cada 15 iterações)
                if self.iteration % 15 == 0:
                    print("\n🕐 Verificando atividade recente...")
                    activity_result = await self.test_recent_activity(minutes=5)
                    
                    if activity_result["success"]:
                        activity_data = activity_result["data"]
                        recent_logs = activity_data.get("logs", [])
                        print(f"📜 Atividade dos últimos 5 minutos: {len(recent_logs)} log(s)")
                    else:
                        print(f"❌ Erro ao buscar atividade: {activity_result.get('error')}")
                
                # Aguardar próxima iteração
                await asyncio.sleep(interval)
        
        except KeyboardInterrupt:
            print("\n\n⛔ Monitoramento interrompido pelo usuário")
            self.running = False
    
    # ==================== Teste de Conectividade ====================
    
    async def test_connectivity(self) -> bool:
        """Testa conectividade básica com todas as rotas"""
        print("\n🧪 Testando conectividade com as rotas de realtime...")
        print("=" * 70)
        
        routes = [
            ("Alarm Status", "/api/v1/realtime/alarm-status"),
            ("New Logs", "/api/v1/realtime/new-logs"),
            ("Log Count", "/api/v1/realtime/log-count"),
            ("Recent Activity", "/api/v1/realtime/recent-activity"),
            ("Monitor Full", "/api/v1/realtime/monitor")
        ]
        
        all_ok = True
        
        for name, route in routes:
            try:
                response = await self.client.get(f"{self.base_url}{route}", timeout=5.0)
                status = "✅" if response.status_code == 200 else "⚠️"
                print(f"{status} {name:20s} → {response.status_code}")
                
                if response.status_code != 200:
                    all_ok = False
            except Exception as e:
                print(f"❌ {name:20s} → Erro: {str(e)[:50]}")
                all_ok = False
        
        print("=" * 70)
        
        if all_ok:
            print("✅ Todas as rotas estão acessíveis!")
        else:
            print("⚠️  Algumas rotas apresentaram problemas")
        
        return all_ok


# ==================== Menu Principal ====================

async def main():
    """Menu principal para escolher modo de monitoramento"""
    print("=" * 70)
    print("  🎯 TESTE DE MONITORAMENTO EM TEMPO REAL - iDFace Backend")
    print("=" * 70)
    print(f"\n📡 Backend URL: {BASE_URL}")
    print(f"⏱️  Intervalo de polling: {POLLING_INTERVAL} segundos")
    
    async with RealtimeMonitorTest() as monitor:
        # Teste de conectividade
        print("\n" + "=" * 70)
        connectivity_ok = await monitor.test_connectivity()
        
        if not connectivity_ok:
            print("\n⚠️  Há problemas de conectividade. Deseja continuar? (s/n): ", end="")
            choice = input().strip().lower()
            if choice != "s":
                print("❌ Teste cancelado")
                return
        
        # Menu de escolha
        print("\n" + "=" * 70)
        print("Escolha o modo de monitoramento:")
        print("=" * 70)
        print("1. Modo OTIMIZADO (recomendado)")
        print("   → Usa endpoint /monitor (mais eficiente)")
        print("   → Melhor para produção")
        print("\n2. Modo INDIVIDUAL")
        print("   → Usa endpoints separados")
        print("   → Melhor para debug e testes")
        print("\n0. Sair")
        print("=" * 70)
        
        choice = input("\nDigite sua escolha (1, 2 ou 0) [1]: ").strip() or "1"
        
        if choice == "0":
            print("\n👋 Até logo!")
            return
        
        print("\n💡 Aguarde... iniciando monitoramento em 2 segundos")
        await asyncio.sleep(2)
        
        try:
            if choice == "2":
                await monitor.run_individual_monitoring(interval=POLLING_INTERVAL)
            else:
                await monitor.run_optimized_monitoring(interval=POLLING_INTERVAL)
        except Exception as e:
            print(f"\n❌ Erro inesperado: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⛔ Programa interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()