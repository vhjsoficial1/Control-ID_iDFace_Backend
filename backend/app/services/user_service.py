"""
Serviço de lógica de negócio para gerenciamento de usuários
Contém operações complexas e validações de usuários
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from app.utils.idface_client import idface_client, idface_client_2
import base64
import hashlib
import secrets
import logging
import re

logger = logging.getLogger(__name__)


class UserService:
    """Serviço para gerenciar usuários e suas operações"""
    
    def __init__(self, db):
        self.db = db
    
    # ==================== User CRUD Operations ====================
    
    async def create_user(
        self,
        name: str,
        registration: Optional[str] = None,
        password: Optional[str] = None,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        image: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cria um novo usuário com validações
        """
        # Validações
        validation_errors = []
        
        if not name or len(name.strip()) == 0:
            validation_errors.append("Nome é obrigatório")
        
        if len(name) > 255:
            validation_errors.append("Nome não pode ter mais de 255 caracteres")
        
        
        if registration is not None and registration.strip() == "":
            registration = None
        if password is not None and password.strip() == "":
            password = None

        # Validar datas
        if begin_time and end_time:
            if end_time <= begin_time:
                validation_errors.append("Data de fim deve ser posterior à data de início")
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        # Hash da senha se fornecida
        hashed_password = None
        salt = None
        if password:
            salt = secrets.token_hex(16)
            hashed_password = self._hash_password(password, salt)
        
        try:
            # Criar usuário
            user = await self.db.user.create(
                data={
                    "name": name.strip(),
                    "registration": registration,
                    "password": hashed_password,
                    "salt": salt,
                    "beginTime": begin_time,
                    "endTime": end_time,
                    "image": image
                }
            )
            
            logger.info(f"Usuário criado: ID {user.id}, Nome: {user.name}")
            
            return {
                "success": True,
                "user": user,
                "message": "Usuário criado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao criar usuário: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def update_user(
        self,
        user_id: int,
        name: Optional[str] = None,
        registration: Optional[str] = None,
        password: Optional[str] = None,
        begin_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Atualiza um usuário existente
        """
        # Verificar se usuário existe
        user = await self.db.user.find_unique(where={"id": user_id})
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
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
            if registration.strip() == "":
                registration = None
            else:
                update_data["registration"] = registration

        
        if begin_time is not None:
            update_data["beginTime"] = begin_time
        
        if end_time is not None:
            update_data["endTime"] = end_time
        
        # Validar datas
        final_begin = update_data.get("beginTime", user.beginTime)
        final_end = update_data.get("endTime", user.endTime)
        
        if final_begin and final_end and final_end <= final_begin:
            validation_errors.append("Data de fim deve ser posterior à data de início")
        
        # Atualizar senha se fornecida
        if password:
            salt = secrets.token_hex(16)
            hashed_password = self._hash_password(password, salt)
            update_data["password"] = hashed_password
            update_data["salt"] = salt
        
        if validation_errors:
            return {
                "success": False,
                "errors": validation_errors
            }
        
        if not update_data:
            return {
                "success": True,
                "user": user,
                "message": "Nenhuma alteração necessária"
            }
        
        try:
            updated_user = await self.db.user.update(
                where={"id": user_id},
                data=update_data
            )
            
            logger.info(f"Usuário atualizado: ID {user_id}")
            
            return {
                "success": True,
                "user": updated_user,
                "message": "Usuário atualizado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao atualizar usuário {user_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def delete_user(self, user_id: int, cascade: bool = True) -> Dict[str, Any]:
        """
        Deleta um usuário (e opcionalmente seus dados relacionados)
        """
        user = await self.db.user.find_unique(
            where={"id": user_id},
            include={
                "cards": True,
                "qrcodes": True,
                "templates": True,
                "accessLogs": True
            }
        )
        
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
            }
        
        try:
            # Verificar dados relacionados
            related_data = {
                "cards": len(user.cards) if user.cards else 0,
                "qrcodes": len(user.qrcodes) if user.qrcodes else 0,
                "templates": len(user.templates) if user.templates else 0,
                "accessLogs": len(user.accessLogs) if user.accessLogs else 0
            }
            
            # Se não for cascade e tiver dados relacionados, avisar
            if not cascade and sum(related_data.values()) > 0:
                return {
                    "success": False,
                    "errors": ["Usuário possui dados relacionados. Use cascade=true para forçar deleção."],
                    "relatedData": related_data
                }
            
            # Deletar usuário (cascade é automático no Prisma)
            await self.db.user.delete(where={"id": user_id})
            
            logger.info(f"Usuário deletado: ID {user_id}, Nome: {user.name}")
            
            return {
                "success": True,
                "message": f"Usuário '{user.name}' deletado com sucesso",
                "deletedRelatedData": related_data
            }
            
        except Exception as e:
            logger.error(f"Erro ao deletar usuário {user_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== User Search & Filtering ====================
    
    async def search_users(
        self,
        query: Optional[str] = None,
        registration: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 2000
    ) -> Dict[str, Any]:
        """
        Busca usuários com filtros avançados
        """
        where = {}
        
        # Filtro por texto (nome ou matrícula)
        if query:
            where["OR"] = [
                {"name": {"contains": query, "mode": "insensitive"}},
                {"registration": {"contains": query, "mode": "insensitive"}}
            ]
        
        # Filtro específico por matrícula
        if registration:
            where["registration"] = registration
        
        # Filtro por usuários ativos (dentro do período de validade)
        if active_only:
            now = datetime.now()
            where["AND"] = [
                {"OR": [
                    {"beginTime": None},
                    {"beginTime": {"lte": now}}
                ]},
                {"OR": [
                    {"endTime": None},
                    {"endTime": {"gte": now}}
                ]}
            ]
        
        try:
            users = await self.db.user.find_many(
                where=where,
                skip=skip,
                take=limit,
                include={
                    "cards": True,
                    "qrcodes": True,
                    "userGroups": {
                        "include": {
                            "group": True
                        }
                    },
                    "userAccessRules": {
                        "include": {
                            "accessRule": True
                        }
                    }
                },
                order={"name": "asc"}
            )
            
            total = await self.db.user.count(where=where)
            
            return {
                "success": True,
                "users": users,
                "total": total,
                "skip": skip,
                "limit": limit
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar usuários: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def get_user_full_details(self, user_id: int) -> Dict[str, Any]:
        """
        Retorna detalhes completos de um usuário
        """
        try:
            user = await self.db.user.find_unique(
                where={"id": user_id},
                include={
                    "cards": True,
                    "qrcodes": True,
                    "templates": True,
                    "userGroups": {
                        "include": {
                            "group": True
                        }
                    },
                    "userAccessRules": {
                        "include": {
                            "accessRule": {
                                "include": {
                                    "timeZones": {
                                        "include": {
                                            "timeZone": True
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "accessLogs": {
                        "take": 10,
                        "order": {"timestamp": "desc"}
                    }
                }
            )
            
            if not user:
                return {
                    "success": False,
                    "errors": [f"Usuário {user_id} não encontrado"]
                }
            
            # Calcular status
            status = self._get_user_status(user)
            
            return {
                "success": True,
                "user": user,
                "status": status,
                "statistics": {
                    "totalCards": len(user.cards) if user.cards else 0,
                    "totalQRCodes": len(user.qrcodes) if user.qrcodes else 0,
                    "totalAccessRules": len(user.userAccessRules) if user.userAccessRules else 0,
                    "recentAccessLogs": len(user.accessLogs) if user.accessLogs else 0,
                    "hasFacialImage": bool(user.image),
                    "syncedWithDevice": bool(user.idFaceId)
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao buscar detalhes do usuário {user_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Image Management ====================
    
    async def set_user_image(
        self,
        user_id: int,
        image_base64: str,
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Define imagem facial do usuário
        """
        user = await self.db.user.find_unique(where={"id": user_id})
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
            }
        
        # Validar imagem
        if validate:
            validation = self._validate_image_base64(image_base64)
            if not validation["valid"]:
                return {
                    "success": False,
                    "errors": validation["errors"]
                }
        
        try:
            updated_user = await self.db.user.update(
                where={"id": user_id},
                data={
                    "image": image_base64,
                    "imageTimestamp": datetime.now()
                }
            )
            
            logger.info(f"Imagem facial definida para usuário {user_id}")
            
            return {
                "success": True,
                "user": updated_user,
                "message": "Imagem facial salva com sucesso",
                "imageSize": len(image_base64)
            }
            
        except Exception as e:
            logger.error(f"Erro ao salvar imagem do usuário {user_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def delete_user_image(self, user_id: int) -> Dict[str, Any]:
        """
        Remove imagem facial do usuário
        """
        try:
            await self.db.user.update(
                where={"id": user_id},
                data={
                    "image": None,
                    "imageTimestamp": None
                }
            )
            
            logger.info(f"Imagem facial removida do usuário {user_id}")
            
            return {
                "success": True,
                "message": "Imagem facial removida com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover imagem do usuário {user_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Card Management ====================
    
    async def add_card_to_user(
        self,
        user_id: int,
        card_value: int
    ) -> Dict[str, Any]:
        """
        Adiciona cartão a um usuário
        """
        # Verificar usuário
        user = await self.db.user.find_unique(where={"id": user_id})
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
            }
        
        # Verificar se cartão já existe
        existing_card = await self.db.card.find_first(
            where={"value": card_value}
        )
        
        if existing_card:
            if existing_card.userId == user_id:
                return {
                    "success": False,
                    "errors": ["Cartão já pertence a este usuário"]
                }
            else:
                return {
                    "success": False,
                    "errors": [f"Cartão já está registrado para outro usuário (ID: {existing_card.userId})"]
                }
        
        try:
            card = await self.db.card.create(
                data={
                    "value": card_value,
                    "userId": user_id
                }
            )
            
            logger.info(f"Cartão {card_value} adicionado ao usuário {user_id}")
            
            return {
                "success": True,
                "card": card,
                "message": "Cartão adicionado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao adicionar cartão: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    async def remove_card_from_user(
        self,
        card_id: int
    ) -> Dict[str, Any]:
        """
        Remove cartão de um usuário
        """
        card = await self.db.card.find_unique(where={"id": card_id})
        if not card:
            return {
                "success": False,
                "errors": [f"Cartão {card_id} não encontrado"]
            }
        
        try:
            await self.db.card.delete(where={"id": card_id})
            
            logger.info(f"Cartão {card_id} removido do usuário {card.userId}")
            
            return {
                "success": True,
                "message": "Cartão removido com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Erro ao remover cartão {card_id}: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Access Rules ====================
    
    async def link_user_to_access_rule(
        self,
        user_id: int,
        access_rule_id: int
    ) -> Dict[str, Any]:
        """
        Vincula usuário a uma regra de acesso
        """
        # Verificar usuário
        user = await self.db.user.find_unique(where={"id": user_id})
        if not user:
            return {
                "success": False,
                "errors": [f"Usuário {user_id} não encontrado"]
            }
        
        # Verificar regra
        rule = await self.db.accessrule.find_unique(where={"id": access_rule_id})
        if not rule:
            return {
                "success": False,
                "errors": [f"Regra de acesso {access_rule_id} não encontrada"]
            }
        
        # Verificar se já existe vínculo
        existing = await self.db.useraccessrule.find_first(
            where={
                "userId": user_id,
                "accessRuleId": access_rule_id
            }
        )
        
        if existing:
            return {
                "success": False,
                "errors": ["Usuário já está vinculado a esta regra"]
            }
        
        try:
            link = await self.db.useraccessrule.create(
                data={
                    "userId": user_id,
                    "accessRuleId": access_rule_id
                }
            )
            
            logger.info(f"Usuário {user_id} vinculado à regra {access_rule_id}")
            
            return {
                "success": True,
                "link": link,
                "message": f"Usuário vinculado à regra '{rule.name}'"
            }
            
        except Exception as e:
            logger.error(f"Erro ao vincular usuário à regra: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }
    
    # ==================== Validation & Helper Methods ====================
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Hash de senha com salt"""
        return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    
    def _validate_image_base64(self, image_base64: str) -> Dict[str, Any]:
        """Valida string base64 de imagem"""
        errors = []
        
        # Verificar se é base64 válido
        try:
            image_data = base64.b64decode(image_base64)
        except Exception:
            errors.append("Imagem inválida: não é base64 válido")
            return {"valid": False, "errors": errors}
        
        # Verificar tamanho (limite de 5MB)
        max_size = 5 * 1024 * 1024  # 5MB
        if len(image_data) > max_size:
            errors.append(f"Imagem muito grande: máximo {max_size / 1024 / 1024}MB")
        
        # Verificar formato (header de imagem)
        valid_headers = [
            b'\xff\xd8\xff',  # JPEG
            b'\x89PNG',       # PNG
            b'GIF89a',        # GIF
            b'GIF87a'         # GIF
        ]
        
        is_valid_format = any(image_data.startswith(header) for header in valid_headers)
        if not is_valid_format:
            errors.append("Formato de imagem não suportado (use JPEG, PNG ou GIF)")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    def _get_user_status(self, user) -> str:
        """Determina status do usuário baseado nas datas"""
        now = datetime.now()
        
        # Verificar se está dentro do período de validade
        if user.beginTime and user.beginTime > now:
            return "pending"  # Ainda não iniciou
        
        if user.endTime and user.endTime < now:
            return "expired"  # Expirado
        
        if user.beginTime and user.endTime:
            return "active"  # Ativo com período definido
        
        return "active"  # Ativo sem restrições
    
    # ==================== Statistics ====================
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """
        Retorna estatísticas gerais de usuários
        """
        try:
            total_users = await self.db.user.count()
            
            # Usuários com imagem
            users_with_image = await self.db.user.count(
                where={"image": {"not": None}}
            )
            
            # Usuários sincronizados
            synced_users = await self.db.user.count(
                where={"idFaceId": {"not": None}}
            )
            
            # Usuários ativos
            now = datetime.now()
            active_users = await self.db.user.count(
                where={
                    "AND": [
                        {"OR": [
                            {"beginTime": None},
                            {"beginTime": {"lte": now}}
                        ]},
                        {"OR": [
                            {"endTime": None},
                            {"endTime": {"gte": now}}
                        ]}
                    ]
                }
            )
            
            # Total de cartões
            total_cards = await self.db.card.count()
            
            # Total de QR codes
            total_qrcodes = await self.db.qrcode.count()
            
            return {
                "success": True,
                "statistics": {
                    "totalUsers": total_users,
                    "activeUsers": active_users,
                    "usersWithImage": users_with_image,
                    "syncedUsers": synced_users,
                    "totalCards": total_cards,
                    "totalQRCodes": total_qrcodes,
                    "percentages": {
                        "withImage": round((users_with_image / total_users * 100), 2) if total_users > 0 else 0,
                        "synced": round((synced_users / total_users * 100), 2) if total_users > 0 else 0,
                        "active": round((active_users / total_users * 100), 2) if total_users > 0 else 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Erro ao calcular estatísticas: {e}")
            return {
                "success": False,
                "errors": [str(e)]
            }