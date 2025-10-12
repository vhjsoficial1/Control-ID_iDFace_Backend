"""
HTTP Client for iDFace API communication
Handles session management and requests to the Control ID device
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
        await self.client.aclose()
    
    async def login(self) -> str:
        """Create session with iDFace device"""
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
        """End current session"""
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
        """Ensure we have a valid session"""
        if not self.session or (self.session_expires and datetime.now() >= self.session_expires):
            await self.login()
    
    async def request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """Make authenticated request to iDFace"""
        await self.ensure_session()
        
        url = f"{self.base_url}/{endpoint}"
        params = kwargs.get("params", {})
        params["session"] = self.session
        kwargs["params"] = params
        
        response = await self.client.request(method, url, **kwargs)
        response.raise_for_status()
        
        # Some endpoints don't return JSON
        try:
            return response.json()
        except:
            return {"status": "success"}
    
    # ==================== User Operations ====================
    
    async def create_user(self, user_data: Dict) -> Dict:
        """Create user in iDFace"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "users",
                "values": [user_data]
            }
        )
    
    async def update_user(self, user_id: int, user_data: Dict) -> Dict:
        """Update user in iDFace"""
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
        """Delete user from iDFace"""
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
        """Load users from iDFace"""
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
        """Upload facial image for user"""
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
        """Upload multiple user images"""
        return await self.request(
            "POST",
            "user_set_image_list.fcgi",
            json={
                "match": True,
                "user_images": user_images
            }
        )
    
    async def get_user_image(self, user_id: int) -> bytes:
        """Download user image"""
        await self.ensure_session()
        url = f"{self.base_url}/user_get_image.fcgi"
        params = {"session": self.session, "user_id": user_id}
        
        response = await self.client.post(url, params=params)
        response.raise_for_status()
        return response.content
    
    async def delete_user_images(self, user_ids: list[int]) -> Dict:
        """Delete user images"""
        return await self.request(
            "POST",
            "user_destroy_image.fcgi",
            json={"user_ids": user_ids}
        )
    
    # ==================== Access Rules ====================
    
    async def create_access_rule(self, rule_data: Dict) -> Dict:
        """Create access rule"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "access_rules",
                "values": [rule_data]
            }
        )
    
    async def load_access_rules(self) -> Dict:
        """Load all access rules"""
        return await self.request(
            "POST",
            "load_objects.fcgi",
            json={"object": "access_rules"}
        )
    
    # ==================== Time Zones ====================
    
    async def create_time_zone(self, tz_data: Dict) -> Dict:
        """Create time zone"""
        return await self.request(
            "POST",
            "create_objects.fcgi",
            json={
                "object": "time_zones",
                "values": [tz_data]
            }
        )
    
    async def create_time_span(self, span_data: Dict) -> Dict:
        """Create time span"""
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
        """Load access logs from device"""
        return await self.request(
            "POST",
            "load_objects.fcgi",
            json={"object": "access_logs"}
        )
    
    # ==================== User Access Rules ====================
    
    async def create_user_access_rule(self, user_id: int, access_rule_id: int) -> Dict:
        """Link user to access rule"""
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
        """Register card for user"""
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
    
    # ==================== System ====================
    
    async def get_system_info(self) -> Dict:
        """Get device system information"""
        return await self.request(
            "POST",
            "system_information.fcgi"
        )
    
    async def reboot(self) -> Dict:
        """Reboot device"""
        return await self.request(
            "POST",
            "reboot.fcgi"
        )
    
    async def execute_actions(self, actions: list) -> Dict:
        """Execute actions (open door, etc)"""
        return await self.request(
            "POST",
            "execute_actions.fcgi",
            json={"actions": actions}
        )


# Singleton instance
idface_client = IDFaceClient()