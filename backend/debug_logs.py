"""
Script de debug para verificar por que logs não estão sendo capturados
Execute: python debug_logs.py
"""
import asyncio
import sys
import os
import httpx

sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.utils.idface_client import IDFaceClient


async def main():
    """Debug dos logs"""
    print("\n" + "="*70)
    print("🔍 DEBUG - Verificando logs do dispositivo")
    print("="*70)
    
    try:
        # Criar cliente iDFace
        client = IDFaceClient()
        
        # 1. Verificar último log NO DEVICE
        print("\n1️⃣  Buscando TODOS os logs do device (sem filtro)...")
        async with client:
            all_logs = await client.load_access_logs()
        
        device_logs = all_logs.get("access_logs", [])
        print(f"   ✅ Total no device: {len(device_logs)} logs")
        
        if device_logs:
            # Mostrar os últimos 3
            recent = device_logs[-3:] if len(device_logs) >= 3 else device_logs
            print(f"\n   Últimos {len(recent)} logs no device:")
            for log in recent:
                log_id = log.get("id")
                user_id = log.get("user_id")
                portal_id = log.get("portal_id")
                event = log.get("event")
                timestamp = log.get("time")
                print(f"      • Log #{log_id}: user_id={user_id}, portal_id={portal_id}, event={event}, time={timestamp}")
        
        # 2. Contar logs no device de novo com since_timestamp
        print("\n2️⃣  Verificando logs com filtro de timestamp...")
        # Se houver logs, pegar o timestamp do último
        if device_logs:
            last_log = device_logs[-1]
            last_time = last_log.get("time", 0)
            print(f"   Último timestamp no device: {last_time}")
            
            # Tentar buscar logs com since_timestamp = last_time
            filtered = await client.load_access_logs_filtered(since_timestamp=last_time)
            filtered_logs = filtered.get("access_logs", [])
            print(f"   Logs com since_timestamp={last_time}: {len(filtered_logs)} logs")
            
            # Tentar com since_timestamp = last_time - 1
            filtered_minus_1 = await client.load_access_logs_filtered(since_timestamp=last_time - 1)
            filtered_logs_minus_1 = filtered_minus_1.get("access_logs", [])
            print(f"   Logs com since_timestamp={last_time - 1}: {len(filtered_logs_minus_1)} logs")
        
        print("\n✅ Verificação concluída!")
    
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
