"""
Script para associar TODOS os 2 portais a TODOS os departamentos e horários existentes
Execute: python backend/fix_all_portals.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import db
from app.utils.idface_client import idface_client


async def fix_all_portal_associations():
    """
    Associa TODOS os portais a TODAS as access rules (departamentos e horários)
    """
    await db.connect()
    
    print("\n" + "="*80)
    print("🔧 CORREÇÃO: ASSOCIAR TODOS OS PORTAIS A TODOS OS DEPARTAMENTOS/HORÁRIOS")
    print("="*80 + "\n")
    
    # 1. Buscar todos os portais
    all_portals = await db.portal.find_many()
    print(f"📍 Portais encontrados: {len(all_portals)}")
    for portal in all_portals:
        print(f"   • Portal {portal.id}: {portal.name} (iDFace #{portal.idFaceId})")
    
    # 2. Buscar todas as AccessRules
    all_access_rules = await db.accessrule.find_many()
    print(f"\n📋 Access Rules encontradas: {len(all_access_rules)}")
    
    total_associations = 0
    total_synced = 0
    total_errors = 0
    
    # 3. Para cada AccessRule, garantir que TODOS os portais estejam associados
    for access_rule in all_access_rules:
        print(f"\n🔄 Processando: {access_rule.name} (ID: {access_rule.id})")
        
        # Buscar portais já associados
        existing_portals = await db.portalaccessrule.find_many(
            where={"accessRuleId": access_rule.id}
        )
        existing_portal_ids = {p.portalId for p in existing_portals}
        
        # Associar portais faltantes
        for portal in all_portals:
            if portal.id not in existing_portal_ids:
                try:
                    # Criar vínculo local Portal-AccessRule
                    await db.portalaccessrule.create(
                        data={
                            "portalId": portal.id,
                            "accessRuleId": access_rule.id
                        }
                    )
                    total_associations += 1
                    print(f"   ✅ Associado ao portal: {portal.name}")
                    
                    # Sincronizar Portal-AccessRule com iDFace
                    if portal.idFaceId and access_rule.idFaceId:
                        try:
                            async with idface_client:
                                await idface_client.request(
                                    "POST",
                                    "create_objects.fcgi",
                                    json={
                                        "object": "portal_access_rules",
                                        "values": [{
                                            "portal_id": portal.idFaceId,
                                            "access_rule_id": access_rule.idFaceId
                                        }]
                                    }
                                )
                            total_synced += 1
                            print(f"   🔄 Sincronizado Portal-AccessRule com iDFace")
                        except Exception as e:
                            print(f"   ⚠️  Erro ao sincronizar Portal-AccessRule: {e}")
                            total_errors += 1
                    
                    # ✅ ADICIONAL: Tentar vincular Portal aos Groups relacionados
                    # Buscar grupos vinculados a esta AccessRule
                    group_rules = await db.groupaccessrule.find_many(
                        where={"accessRuleId": access_rule.id},
                        include={"group": True}
                    )
                    
                    for gar in group_rules:
                        if gar.group and gar.group.idFaceId and portal.idFaceId:
                            try:
                                async with idface_client:
                                    await idface_client.request(
                                        "POST",
                                        "create_objects.fcgi",
                                        json={
                                            "object": "portal_groups",
                                            "values": [{
                                                "portal_id": portal.idFaceId,
                                                "group_id": gar.group.idFaceId
                                            }]
                                        }
                                    )
                                print(f"   🔗 Vinculado Portal ao Group '{gar.group.name}'")
                            except Exception as e:
                                # Vínculo direto pode não existir no iDFace
                                print(f"   ℹ️  Vínculo Portal-Group: {e}")
                    
                    # ✅ ADICIONAL: Tentar vincular Portal aos TimeZones relacionados
                    # Buscar time zones vinculados a esta AccessRule
                    tz_rules = await db.accessruletimezone.find_many(
                        where={"accessRuleId": access_rule.id},
                        include={"timeZone": True}
                    )
                    
                    for artz in tz_rules:
                        if artz.timeZone and artz.timeZone.idFaceId and portal.idFaceId:
                            try:
                                async with idface_client:
                                    await idface_client.request(
                                        "POST",
                                        "create_objects.fcgi",
                                        json={
                                            "object": "portal_time_zones",
                                            "values": [{
                                                "portal_id": portal.idFaceId,
                                                "time_zone_id": artz.timeZone.idFaceId
                                            }]
                                        }
                                    )
                                print(f"   🕐 Vinculado Portal ao TimeZone '{artz.timeZone.name}'")
                            except Exception as e:
                                # Vínculo direto pode não existir no iDFace
                                print(f"   ℹ️  Vínculo Portal-TimeZone: {e}")
                
                except Exception as e:
                    print(f"   ❌ Erro ao associar portal {portal.name}: {e}")
                    total_errors += 1
            else:
                print(f"   ℹ️  Portal {portal.name} já estava associado")
    
    # 4. Relatório final
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL")
    print("="*80)
    print(f"✅ Total de novas associações criadas: {total_associations}")
    print(f"🔄 Total sincronizadas com iDFace: {total_synced}")
    print(f"❌ Total de erros: {total_errors}")
    
    # 5. Verificação final
    print("\n" + "="*80)
    print("🔍 VERIFICAÇÃO FINAL - ESTADO ATUAL DO BANCO")
    print("="*80 + "\n")
    
    for access_rule in all_access_rules:
        linked_portals = await db.portalaccessrule.find_many(
            where={"accessRuleId": access_rule.id},
            include={"portal": True}
        )
        
        portal_names = [p.portal.name for p in linked_portals]
        status = "✅" if len(portal_names) == len(all_portals) else "⚠️"
        
        print(f"{status} {access_rule.name}")
        print(f"   Portais: {', '.join(portal_names) if portal_names else 'NENHUM'}")
        print(f"   Total: {len(portal_names)}/{len(all_portals)}\n")
    
    await db.disconnect()
    print("\n✅ Correção concluída!\n")


if __name__ == "__main__":
    asyncio.run(fix_all_portal_associations())