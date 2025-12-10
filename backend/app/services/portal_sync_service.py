from app.database import db, connect_db, disconnect_db
# Importando ambos os clientes
from app.utils.idface_client import idface_client, idface_client_2
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
        Busca áreas nos iDFaces (L1 e L2) e atualiza a tabela Portal no banco local.
        Execução em Fila Indiana.
        """
        stats = {"synced": 0, "created": 0, "updated": 0, "portals": [], "errors": []}
        
        try:
            # 1. Garantir conexão com banco
            await self.ensure_connection()

            # Função auxiliar para processar um dispositivo específico
            async def _process_client(client, label):
                print(f"📡 Buscando dados em {label} (load_objects)...")
                try:
                    async with client:
                        response = await client.request("POST", "load_objects.fcgi", json={"object": "areas"})
                        areas = response.get("areas", [])
                        
                        if not areas:
                            print(f"ℹ️ Nenhuma área encontrada em {label}")
                            return

                        print(f"📋 Encontradas {len(areas)} áreas em {label}.")

                        # Sincronizar com o banco local
                        for area in areas:
                            area_id = area.get("id")
                            area_name = area.get("name")
                            
                            if not area_id: continue

                            try:
                                # Tenta achar pelo ID do iDFace
                                existing = await db.portal.find_first(where={"idFaceId": area_id})
                                
                                status_op = "unchanged"
                                
                                if existing:
                                    if existing.name != area_name:
                                        await db.portal.update(
                                            where={"id": existing.id},
                                            data={"name": area_name}
                                        )
                                        status_op = "updated"
                                        stats["updated"] += 1
                                else:
                                    await db.portal.create(
                                        data={
                                            "idFaceId": area_id,
                                            "name": area_name
                                        }
                                    )
                                    status_op = "created"
                                    stats["created"] += 1
                                
                                # Evita duplicar na lista de retorno se já processado pelo L1
                                if not any(p['id'] == area_id for p in stats["portals"]):
                                    stats["synced"] += 1
                                    stats["portals"].append({
                                        "id": area_id, 
                                        "name": area_name, 
                                        "status": status_op,
                                        "source": label
                                    })
                                    
                            except Exception as e_inner:
                                print(f"❌ Erro ao processar portal #{area_id} de {label}: {e_inner}")
                                # Tenta reconectar se o erro for de conexão perdida com o banco
                                if "Client is not connected" in str(e_inner):
                                    await self.ensure_connection()

                except Exception as e_client:
                    error_msg = f"Erro ao conectar com {label}: {e_client}"
                    print(f"❌ {error_msg}")
                    stats["errors"].append(error_msg)

            # --- FILA INDIANA ---
            
            # 1. Processa Leitor 1
            await _process_client(idface_client, "Leitor 1")
            
            # 2. Processa Leitor 2
            await _process_client(idface_client_2, "Leitor 2")

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