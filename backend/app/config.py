from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    
    # iDFace Reader 1
    IDFACE_IP: str
    IDFACE_LOGIN: str
    IDFACE_PASSWORD: str
    IDFACE_GATEWAY: str
    IDFACE_NETMASK: str
    
    # iDFace Reader 2
    IDFACE2_IP: str
    IDFACE2_LOGIN: str
    IDFACE2_PASSWORD: str
    IDFACE2_GATEWAY: str
    IDFACE2_NETMASK: str
    
    API_TITLE: str = "iDFace Control System"
    API_VERSION: str = "1.0.0"
    API_SECRET_KEY: str
    SESSION_TIMEOUT: int = 3600
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()