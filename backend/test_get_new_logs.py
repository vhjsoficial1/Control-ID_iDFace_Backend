"""
Script de teste para verificar a função get_new_access_logs
"""
import asyncio
import httpx
from datetime import datetime

BASE_URL = "http://localhost:8000"


async def test_get_new_logs():
    """Testa o endpoint de novos logs"""
    async with httpx.AsyncClient() as client:
        print("=" * 70)
        print("🧪 TESTANDO GET_NEW_ACCESS_LOGS")
        print("=" * 70)
        
        # Teste 1: Primeira chamada (sem since_id)
        print("\n1️⃣  Primeira chamada (sem since_id):")
        print(f"   GET {BASE_URL}/api/v1/realtime/new-logs")
        
        response = await client.get(f"{BASE_URL}/api/v1/realtime/new-logs")
        print(f"   Status: {response.status_code}")
        data = response.json()
        
        print(f"   Resposta:")
        print(f"      - success: {data.get('success')}")
        print(f"      - count: {data.get('count')}")
        print(f"      - totalCount: {data.get('totalCount')}")
        print(f"      - lastId: {data.get('lastId')}")
        print(f"      - timestamp: {data.get('timestamp')}")
        
        # Teste 2: Segunda chamada (com since_id)
        if data.get('lastId'):
            since_id = data.get('lastId')
            print(f"\n2️⃣  Segunda chamada (com since_id={since_id}):")
            print(f"   GET {BASE_URL}/api/v1/realtime/new-logs?since_id={since_id}")
            
            response = await client.get(
                f"{BASE_URL}/api/v1/realtime/new-logs",
                params={"since_id": since_id}
            )
            print(f"   Status: {response.status_code}")
            data2 = response.json()
            
            print(f"   Resposta:")
            print(f"      - success: {data2.get('success')}")
            print(f"      - count: {data2.get('count')}")
            print(f"      - newLogs: {len(data2.get('newLogs', []))} logs")
            if data2.get('newLogs'):
                for log in data2.get('newLogs', []):
                    print(f"        • {log.get('userName')} - {log.get('event')} @ {log.get('timestamp')}")
        
        # Teste 3: Monitor endpoint completo
        print(f"\n3️⃣  Endpoint monitor completo:")
        print(f"   GET {BASE_URL}/api/v1/realtime/monitor")
        
        response = await client.get(f"{BASE_URL}/api/v1/realtime/monitor")
        print(f"   Status: {response.status_code}")
        data3 = response.json()
        
        print(f"   Resposta:")
        print(f"      - success: {data3.get('success')}")
        print(f"      - timestamp: {data3.get('timestamp')}")
        print(f"      - deviceStatus: {data3.get('deviceStatus')}")
        print(f"      - alarm.active: {data3.get('alarm', {}).get('active')}")
        print(f"      - logs.newCount: {data3.get('logs', {}).get('newCount')}")
        print(f"      - logs.totalCount: {data3.get('logs', {}).get('totalCount')}")
        print(f"      - logs.lastId: {data3.get('logs', {}).get('lastId')}")
        
        print("\n" + "=" * 70)
        print("✅ TESTE CONCLUÍDO")
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(test_get_new_logs())
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
