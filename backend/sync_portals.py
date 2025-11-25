"""
Script para sincronizar portais do dispositivo iDFace com o banco de dados
Execute: python sync_portals.py
"""
import asyncio
import sys
import os

# Adicionar o caminho para importar app
sys.path.insert(0, os.path.dirname(__file__))

from app.services.portal_sync_service import portal_sync_service


async def main():
    """Sincroniza portais do dispositivo"""
    print("\n" + "="*70)
    print("🔄 SINCRONIZAÇÃO DE PORTAIS - iDFace")
    print("="*70)
    
    print("\n📡 Conectando ao dispositivo e sincronizando portais...")
    result = await portal_sync_service.sync_portals_from_device()
    
    print("\n" + "="*70)
    print("✅ RESULTADO DA SINCRONIZAÇÃO")
    print("="*70)
    
    if result["success"]:
        print(f"✅ Status: SUCESSO")
        print(f"📊 Total sincronizado: {result['synced']} portais")
        print(f"   ✨ Criados: {result['created']}")
        print(f"   ✏️  Atualizados: {result['updated']}")
        
        if result['portals']:
            print(f"\n📋 Portais sincronizados:")
            for portal in result['portals']:
                status_icon = "✨" if portal['status'] == "created" else "✏️" if portal['status'] == "updated" else "✓"
                print(f"   {status_icon} ID {portal['id']}: {portal['name']} ({portal['status']})")
    else:
        print(f"❌ Status: ERRO")
        print(f"   Erro: {result.get('error')}")
    
    print("\n" + "="*70)
    print("📋 PORTAIS CADASTRADOS NO BANCO")
    print("="*70)
    
    portals = await portal_sync_service.get_synced_portals()
    
    if portals["success"]:
        print(f"\n✅ Total de portais no banco: {portals['count']}")
        
        if portals['portals']:
            for portal in portals['portals']:
                print(f"   • Portal {portal['id']} (iDFace #{portal['idFaceId']}): {portal['name']}")
        else:
            print("   ⚠️  Nenhum portal cadastrado")
    else:
        print(f"❌ Erro ao buscar portais: {portals.get('error')}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
