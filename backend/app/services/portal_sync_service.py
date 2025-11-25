"""
Serviço de sincronização de portais/áreas do dispositivo iDFace com o banco de dados
Sincroniza os portais configurados no leitor com a tabela de portais do PostgreSQL
"""
from typing import Dict, List, Any
from app.utils.idface_client import idface_client
from app.database import db
import logging

logger = logging.getLogger(__name__)


class PortalSyncService:
    """Sincroniza portais do iDFace com o banco de dados local"""
    
    def __init__(self):
        self.db = db
    
    async def sync_portals_from_device(self) -> Dict[str, Any]:
        """
        Sincroniza portais do dispositivo iDFace com o banco de dados
        Obtém todas as áreas/portais do leitor e salva/atualiza no banco
        
        Returns:
            {
                "success": bool,
                "synced": int,  # quantidade sincronizada
                "created": int,
                "updated": int,
                "portals": [...]
            }
        """
        try:
            logger.info("Iniciando sincronização de portais...")
            
            # 1. Buscar TODAS as áreas do dispositivo
            async with idface_client:
                result = await idface_client.load_areas()
            
            device_areas = result.get("areas", [])
            logger.info(f"Encontrados {len(device_areas)} portais no dispositivo")
            
            if not device_areas:
                return {
                    "success": True,
                    "synced": 0,
                    "created": 0,
                    "updated": 0,
                    "message": "Nenhuma área encontrada no dispositivo",
                    "portals": []
                }
            
            # 2. Processar cada área
            created = 0
            updated = 0
            synced_portals = []
            
            for area in device_areas:
                area_id = area.get("id")
                area_name = area.get("name", f"Portal {area_id}")
                
                if not area_id:
                    logger.warning(f"Área sem ID: {area}")
                    continue
                
                try:
                    # 3. Verificar se portal já existe no banco
                    existing_portal = await self.db.portal.find_unique(
                        where={"idFaceId": area_id}
                    )
                    
                    if existing_portal:
                        # Atualizar nome se mudou
                        if existing_portal.name != area_name:
                            updated_portal = await self.db.portal.update(
                                where={"idFaceId": area_id},
                                data={"name": area_name}
                            )
                            updated += 1
                            logger.info(f"Portal #{area_id} atualizado: {area_name}")
                        else:
                            logger.debug(f"Portal #{area_id} já existe e sem mudanças")
                    else:
                        # Criar novo portal
                        new_portal = await self.db.portal.create(
                            data={
                                "idFaceId": area_id,
                                "name": area_name
                            }
                        )
                        created += 1
                        logger.info(f"Portal #{area_id} criado: {area_name}")
                    
                    synced_portals.append({
                        "id": area_id,
                        "name": area_name,
                        "status": "created" if not existing_portal else "updated" if existing_portal.name != area_name else "unchanged"
                    })
                
                except Exception as e:
                    logger.error(f"Erro ao processar portal #{area_id}: {e}")
                    continue
            
            total_synced = len(synced_portals)
            
            logger.info(f"✅ Sincronização concluída: {total_synced} portais, {created} criados, {updated} atualizados")
            
            return {
                "success": True,
                "synced": total_synced,
                "created": created,
                "updated": updated,
                "portals": synced_portals
            }
        
        except Exception as e:
            logger.error(f"❌ Erro na sincronização de portais: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e),
                "synced": 0,
                "created": 0,
                "updated": 0,
                "portals": []
            }
    
    async def get_synced_portals(self) -> Dict[str, Any]:
        """Retorna lista de portais sincronizados no banco"""
        try:
            portals = await self.db.portal.find_many()
            
            return {
                "success": True,
                "count": len(portals),
                "portals": [
                    {
                        "id": p.id,
                        "idFaceId": p.idFaceId,
                        "name": p.name,
                        "createdAt": p.createdAt.isoformat() if p.createdAt else None
                    }
                    for p in portals
                ]
            }
        except Exception as e:
            logger.error(f"Erro ao buscar portais: {e}")
            return {
                "success": False,
                "error": str(e),
                "count": 0,
                "portals": []
            }


# Singleton instance
portal_sync_service = PortalSyncService()
