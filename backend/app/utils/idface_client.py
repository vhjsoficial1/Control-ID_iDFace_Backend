"""
Cliente HTTP para comunicação com a API iDFace
Lida com o gerenciamento de sessões e solicitações ao dispositivo de ID de controle facial iDFace
"""
import httpx
from typing import Optional, Dict, Any
from app.config import settings
import asyncio
from datetime import datetime, timedelta


class IDFaceClient:
    def __init__(self):
        self.base_url = f"http://{settings.IDFACE_IP}"
        self.session: Optional[str] = None
        self.session_expires: Optional[datetime] = None
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        await self.login()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.logout()
        # await self.client.aclose()
    
    async def login(self) -> str:
        """Criar sessão com dispositivo iDFace"""
        url = f"{self.base_url}/login.fcgi"
        payload = {
            "login": settings.IDFACE_LOGIN,
            "password": settings.IDFACE_PASSWORD
        }
        
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        
        data = response.json()
        self.session = data.get("session")
        self.session_expires = datetime.now() + timedelta(seconds=settings.SESSION_TIMEOUT)
        
        return self.session
    
    async def logout(self):
        """Encerrar sessão atual"""
        if not self.session:
            return
        
        url = f"{self.base_url}/logout.fcgi"
        params = {"session": self.session}
        
        try:
            await self.client.post(url, params=params)
        except Exception as e:
            print(f"Logout error: {e}")
        finally:
            self.session = None
            self.session_expires = None
    
    async def ensure_session(self):
        """Garantir que temos uma sessão válida"""
        if not self.session or (self.session_expires and datetime.now() >= self.session_expires):
            await self.login()
    
    async def request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Faça uma solicitação autenticada ao iDFace"""
        await self.ensure_session()
        
        url = f"{self.base_url}/{endpoint}"
        params = kwargs.get("params", {})
        params["session"] = self.session
        kwargs["params"] = params
        
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        
        # Alguns endpoints não retornam JSON
        try:
            return response.json()
        except:
            return {"status": "success"}
    
    # ==================== User Operations ====================
    
    async def create_user(self, user_data: Dict) -> Dict:
        """Criar usuário no iDFace"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "users",
                "values": [user_data]
            }
        )
    
    async def update_user(self, user_id: int, user_data: Dict) -> Dict:
        """Atualizar usuário no iDFace"""
        return await self.request(
            "POST",
            "modify_objects.fcgi",
            json={
                "object": "users",
                "values": user_data,
                "where": {
                    "users": {"id": user_id}
                }
            }
        )
    
    async def delete_user(self, user_id: int) -> Dict:
        """Deletar usuário no iDFace"""
        return await self.request(
            "POST",
            "destroy_objects.fcgi",
            json={
                "object": "users",
                "where": {
                    "users": {"id": user_id}
                }
            }
        )
    
    async def load_users(self, where: Optional[Dict] = None) -> Dict:
        """Carregar informações de usuários do iDFace"""
        payload = {"object": "users"}
        if where:
            payload["where"] = where
        
        return await self.request(
            "POST",
            "load_objects.fcgi",
            json=payload
        )
    
    # ==================== Image Operations ====================
    
    async def set_user_image(
        self, 
        user_id: int, 
        image_data: bytes,
        match: bool = True,
        timestamp: Optional[int] = None
    ) -> Dict:
        """Carregar imagem facial para usuário"""
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        params = {
            "user_id": user_id,
            "match": 1 if match else 0,
            "timestamp": timestamp
        }
        
        return await self.request(
            "POST",
            "user_set_image.fcgi",
            params=params,
            content=image_data,
            headers={"Content-Type": "application/octet-stream"}
        )
    
    async def set_user_image_list(self, user_images: list) -> Dict:
        """Carregar várias imagens de usuário"""
        return await self.request(
            "POST",
            "user_set_image_list.fcgi",
            json={
                "match": True,
                "user_images": user_images
            }
        )
    
    async def get_user_image(self, user_id: int) -> bytes:
        """Baixar imagem do usuário"""
        await self.ensure_session()
        url = f"{self.base_url}/user_get_image.fcgi"
        params = {"session": self.session, "user_id": user_id}
        
        response = await self.client.post(url, params=params)
        response.raise_for_status()
        return response.content
    
    async def delete_user_images(self, user_ids: list[int]) -> Dict:
        """Deletar imagem do usuário"""
        return await self.request(
            "POST",
            "user_destroy_image.fcgi",
            json={"user_ids": user_ids}
        )
    
    # ==================== Access Rules ====================
    
    async def create_access_rule(self, rule_data: Dict) -> Dict:
        """Criar regra de acesso"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "access_rules",
                "values": [rule_data]
            }
        )
    
    async def load_access_rules(self) -> Dict:
        """Carregar todas as regras de acesso"""
        return await self.request(
            "POST",
            "load_objects.fcgi",
            json={"object": "access_rules"}
        )
    
    # ==================== Time Zones ====================
    
    async def create_time_zone(self, tz_data: Dict) -> Dict:
        """Criar fuso horário"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "time_zones",
                "values": [tz_data]
            }
        )
    
    async def create_time_span(self, span_data: Dict) -> Dict:
        """Criar intervalo de tempo"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "time_spans",
                "values": [span_data]
            }
        )
    
    # ==================== Access Logs ====================
    
    async def load_access_logs(self) -> Dict:
        """Carregar logs de acesso do dispositivo"""
        return await self.request(
            "POST",
            "load_objects.fcgi",
            json={"object": "access_logs"}
        )
    
    # ==================== User Access Rules ====================
    
    async def create_user_access_rule(self, user_id: int, access_rule_id: int) -> Dict:
        """Vincular usuário à regra de acesso"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "user_access_rules",
                "values": [{
                    "user_id": user_id,
                    "access_rule_id": access_rule_id
                }]
            }
        )
    
    # ==================== Cards ====================
    
    async def create_card(self, card_value: int, user_id: int) -> Dict:
        """Registrar cartão para usuário"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "cards",
                "values": [{
                    "value": card_value,
                    "user_id": user_id
                }]
            }
        )
    
    # ==================== Face Capture ====================
    
    async def start_face_capture(self, quality: int = 70) -> Dict:
        """Inicia a captura de face no dispositivo"""
        return await self.request(
            "POST",
            "face_start_capture.fcgi",
            params={
                "quality": quality
            }
        )
    
    async def get_capture_status(self) -> Dict:
        """Verifica o status da captura de face"""
        return await self.request(
            "POST",
            "face_get_status.fcgi"
        )
    
    async def get_captured_face(self) -> bytes:
        """Obtém a imagem da face capturada"""
        await self.ensure_session()
        url = f"{self.base_url}/face_get_image.fcgi"
        params = {"session": self.session}
        
        response = await self.client.post(url, params=params)
        response.raise_for_status()
        return response.content

    # ==================== System ====================
    
    async def get_system_info(self) -> Dict:
        """Obtenha informações do sistema do dispositivo"""
        return await self.request(
            "POST",
            "system_information.fcgi"
        )
    
    async def reboot(self) -> Dict:
        """Reinicializar dispositivo"""
        return await self.request(
            "POST",
            "reboot.fcgi"
        )
    
    async def execute_actions(self, actions: list) -> Dict:
        """Executar ações (abrir porta, etc.)"""
        return await self.request(
            "POST",
            "execute_actions.fcgi",
            json={"actions": actions}
        )


# Singleton instance
idface_client = IDFaceClient()