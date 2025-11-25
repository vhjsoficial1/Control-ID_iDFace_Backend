from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    
    # iDFace Reader Configuration
    IDFACE_IP: str
    IDFACE_LOGIN: str
    IDFACE_PASSWORD: str
    IDFACE_GATEWAY: str
    IDFACE_NETMASK: str
    
    # API Configuration
    API_TITLE: str = "iDFace Control System"
    API_VERSION: str = "1.0.0"
    API_SECRET_KEY: str
    
    # Session management
    SESSION_TIMEOUT: int = 3600  # 1 hour in seconds
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()