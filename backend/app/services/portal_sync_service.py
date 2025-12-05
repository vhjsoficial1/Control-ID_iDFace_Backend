from app.database import db, connect_db, disconnect_db
from app.utils.idface_client import idface_client
import logging

logger = logging.getLogger(__name__)

class PortalSyncService:
    async def ensure_connection(self):
        """Garante que a conexão com o banco esteja ativa"""
        try:
            if not db.is_connected():
                print("🔌 Conectando ao banco de dados...")
                await connect_db()
                print("✅ Banco de dados conectado.")
        except Exception as e:
            print(f"❌ Erro ao conectar ao banco: {e}")
            raise e

    async def sync_portals_from_device(self):
        """
        Busca áreas no iDFace e atualiza a tabela Portal no banco local
        """
        stats = {"synced": 0, "created": 0, "updated": 0, "portals": []}
        
        try:
            # 1. Garantir conexão
            await self.ensure_connection()

            # 2. Buscar áreas no dispositivo
            print("📡 Buscando dados no equipamento (load_objects)...")
            response = await idface_client.request("POST", "load_objects.fcgi", json={"object": "areas"})
            areas = response.get("areas", [])
            
            if not areas:
                return {"success": False, "error": "Nenhuma área encontrada no dispositivo"}

            print(f"📋 Encontradas {len(areas)} áreas no equipamento.")

            # 3. Sincronizar com o banco local
            for area in areas:
                area_id = area.get("id")
                area_name = area.get("name")
                
                if not area_id: continue

                try:
                    # Tenta achar pelo ID do iDFace
                    # Nota: O campo no banco é idFaceId para mapear com o ID externo
                    existing = await db.portal.find_first(where={"idFaceId": area_id})
                    
                    status = "unchanged"
                    
                    if existing:
                        if existing.name != area_name:
                            await db.portal.update(
                                where={"id": existing.id},
                                data={"name": area_name}
                            )
                            status = "updated"
                            stats["updated"] += 1
                    else:
                        await db.portal.create(
                            data={
                                "idFaceId": area_id,
                                "name": area_name
                            }
                        )
                        status = "created"
                        stats["created"] += 1
                    
                    stats["synced"] += 1
                    stats["portals"].append({
                        "id": area_id, 
                        "name": area_name, 
                        "status": status
                    })
                except Exception as e_inner:
                    print(f"❌ Erro ao processar portal #{area_id}: {e_inner}")
                    # Tenta reconectar se o erro for de conexão perdida
                    if "Client is not connected" in str(e_inner):
                        await self.ensure_connection()

            return {"success": True, **stats}

        except Exception as e:
            logger.error(f"Erro geral na sincronização de portais: {e}")
            return {"success": False, "error": str(e)}

    async def get_synced_portals(self):
        """Lista os portais que estão no banco local"""
        try:
            await self.ensure_connection()
                
            portals = await db.portal.find_many(order={"idFaceId": "asc"})
            return {
                "success": True,
                "count": len(portals),
                "portals": [
                    {"id": p.id, "idFaceId": p.idFaceId, "name": p.name} 
                    for p in portals
                ]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

portal_sync_service = PortalSyncService()