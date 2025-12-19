"""
Serviço de lógica de negócio para gerenciamento de visitantes
Contém operações complexas e validações de visitantes
"""
from typing import Optional, Dict, Any
from datetime import datetime
from app.utils.idface_client import idface_client, idface_client_2
import logging
import asyncio

logger = logging.getLogger(__name__)


class VisitorService:
    """Serviço para gerenciar visitantes e suas operações"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== Visitor CRUD Operations ====================
    
    async def create_visitor(
        self,
        name: str,
        registration: str,
        begin_time: datetime,
        end_time: datetime,
        image: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria um novo visitante com validações
        """
        # Validações
        validation_errors = []
        
        if not name or len(name.strip()) == 0:
            validation_errors.append("Nome é obrigatório")
        
        if len(name) > 255:
            validation_errors.append("Nome não pode ter mais de 255 caracteres")
        
        if not registration or len(registration.strip()) == 0:
            validation_errors.append("Empresa é obrigatória")
        
        if len(registration) > 255:
            validation_errors.append("Empresa não pode ter mais de 255 caracteres")
        
        # Validar datas
        if not begin_time:
            validation_errors.append("Data de início é obrigatória")
        
        if not end_time:
            validation_errors.append("Data de fim é obrigatória")
        
        if begin_time and end_time:
            if end_time <= begin_time:
                validation_errors.append("Data de fim deve ser posterior à data de início")
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        try:
            # Criar visitante
            visitor = await self.db.visitor.create(
                data={
                    "name": name.strip(),
                    "registration": registration.strip(),
                    "beginTime": begin_time,
                    "endTime": end_time,
                    "image": image
                }
            )
            
            logger.info(f"Visitante criado: ID {visitor.id}, Nome: {visitor.name}")
            
            return {
                "success": True,
                "visitor": visitor,
                "message": "Visitante criado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao criar visitante: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def update_visitor(
        self,
        visitor_id: int,
        name: Optional[str] = None,
        registration: Optional[str] = None,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Atualiza um visitante existente
        """
        # Verificar se visitante existe
        visitor = await self.db.visitor.find_unique(where={"id": visitor_id})
        if not visitor:
            return {
                "success": False,
                "errors": [f"Visitante {visitor_id} não encontrado"]
            }
        
        # Validações
        validation_errors = []
        update_data = {}
        
        if name is not None:
            if len(name.strip()) == 0:
                validation_errors.append("Nome não pode ser vazio")
            elif len(name) > 255:
                validation_errors.append("Nome não pode ter mais de 255 caracteres")
            else:
                update_data["name"] = name.strip()
        
        if registration is not None:
            if len(registration.strip()) == 0:
                validation_errors.append("Empresa não pode ser vazia")
            elif len(registration) > 255:
                validation_errors.append("Empresa não pode ter mais de 255 caracteres")
            else:
                update_data["registration"] = registration.strip()
        
        if begin_time is not None:
            update_data["beginTime"] = begin_time
        
        if end_time is not None:
            update_data["endTime"] = end_time
        
        # Validar datas
        final_begin = update_data.get("beginTime", visitor.beginTime)
        final_end = update_data.get("endTime", visitor.endTime)
        
        if final_begin and final_end and final_end <= final_begin:
            validation_errors.append("Data de fim deve ser posterior à data de início")
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        if not update_data:
            return {
                "success": True,
                "visitor": visitor,
                "message": "Nenhuma alteração necessária"
            }
        
        try:
            updated_visitor = await self.db.visitor.update(
                where={"id": visitor_id},
                data=update_data
            )
            
            logger.info(f"Visitante atualizado: ID {visitor_id}")
            
            return {
                "success": True,
                "visitor": updated_visitor,
                "message": "Visitante atualizado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao atualizar visitante {visitor_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def delete_visitor(self, visitor_id: int) -> Dict[str, Any]:
        """
        Deleta um visitante
        """
        visitor = await self.db.visitor.find_unique(
            where={"id": visitor_id},
            include={"accessLogs": True}
        )
        
        if not visitor:
            return {
                "success": False,
                "errors": [f"Visitante {visitor_id} não encontrado"]
            }
        
        try:
            # Deletar do LEITOR 1
            if visitor.idFaceId:
                try:
                    async with idface_client:
                        await idface_client.delete_user(user_id=visitor.idFaceId)
                except Exception as e:
                    logger.warning(f"Erro ao deletar visitante {visitor_id} do LEITOR 1: {e}")
                
                # Deletar do LEITOR 2
                try:
                    async with idface_client_2:
                        await idface_client_2.delete_user(user_id=visitor.idFaceId)
                except Exception as e:
                    logger.warning(f"Erro ao deletar visitante {visitor_id} do LEITOR 2: {e}")
            
            # Deletar do banco local
            await self.db.visitor.delete(where={"id": visitor_id})
            
            logger.info(f"Visitante deletado: ID {visitor_id}, Nome: {visitor.name}")
            
            return {
                "success": True,
                "message": f"Visitante '{visitor.name}' deletado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao deletar visitante {visitor_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Visitor Search & Filtering ====================
    
    async def search_visitors(
        self,
        query: Optional[str] = None,
        company: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 2000
    ) -> Dict[str, Any]:
        """
        Busca visitantes com filtros avançados
        """
        where = {}
        
        # Filtro por texto (nome ou empresa)
        if query:
            where["OR"] = [
                {"name": {"contains": query, "mode": "insensitive"}},
                {"registration": {"contains": query, "mode": "insensitive"}}
            ]
        
        # Filtro específico por empresa
        if company:
            where["registration"] = {"contains": company, "mode": "insensitive"}
        
        # Filtro por visitantes ativos (dentro do período de validade)
        if active_only:
            now = datetime.now()
            where["AND"] = [
                {"beginTime": {"lte": now}},
                {"endTime": {"gte": now}}
            ]
        
        try:
            visitors = await self.db.visitor.find_many(
                where=where,
                skip=skip,
                take=limit,
                order={"name": "asc"}
            )
            
            total = await self.db.visitor.count(where=where)
            
            return {
                "success": True,
                "visitors": visitors,
                "total": total,
                "skip": skip,
                "limit": limit
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar visitantes: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def get_visitor_full_details(self, visitor_id: int) -> Dict[str, Any]:
        """
        Retorna detalhes completos de um visitante
        """
        try:
            visitor = await self.db.visitor.find_unique(
                where={"id": visitor_id},
                include={"accessLogs": True}
            )
            
            if not visitor:
                return {
                    "success": False,
                    "errors": [f"Visitante {visitor_id} não encontrado"]
                }
            
            return {
                "success": True,
                "visitor": visitor
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar detalhes do visitante {visitor_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Image Management ====================
    
    async def set_visitor_image(
        self,
        visitor_id: int,
        image_base64: str
    ) -> Dict[str, Any]:
        """
        Define imagem facial do visitante
        """
        visitor = await self.db.visitor.find_unique(where={"id": visitor_id})
        if not visitor:
            return {
                "success": False,
                "errors": [f"Visitante {visitor_id} não encontrado"]
            }
        
        try:
            updated_visitor = await self.db.visitor.update(
                where={"id": visitor_id},
                data={
                    "image": image_base64,
                    "imageTimestamp": datetime.now()
                }
            )
            
            logger.info(f"Imagem do visitante {visitor_id} atualizada")
            
            return {
                "success": True,
                "visitor": updated_visitor,
                "message": "Imagem salva com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao salvar imagem do visitante {visitor_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def delete_visitor_image(self, visitor_id: int) -> Dict[str, Any]:
        """
        Remove imagem facial do visitante
        """
        try:
            visitor = await self.db.visitor.find_unique(where={"id": visitor_id})
            if not visitor:
                return {
                    "success": False,
                    "errors": [f"Visitante {visitor_id} não encontrado"]
                }
            
            # Deletar do LEITOR 1
            if visitor.idFaceId:
                try:
                    async with idface_client:
                        await idface_client.delete_user_image(user_id=visitor.idFaceId)
                except Exception as e:
                    logger.warning(f"Erro ao deletar imagem do LEITOR 1: {e}")
                
                # Deletar do LEITOR 2
                try:
                    async with idface_client_2:
                        await idface_client_2.delete_user_image(user_id=visitor.idFaceId)
                except Exception as e:
                    logger.warning(f"Erro ao deletar imagem do LEITOR 2: {e}")
            
            # Deletar do banco local
            updated_visitor = await self.db.visitor.update(
                where={"id": visitor_id},
                data={
                    "image": None,
                    "imageTimestamp": None
                }
            )
            
            logger.info(f"Imagem do visitante {visitor_id} removida")
            
            return {
                "success": True,
                "visitor": updated_visitor,
                "message": "Imagem removida com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover imagem do visitante {visitor_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
