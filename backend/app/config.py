import os
from pydantic_settings import BaseSettings

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)

class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""  # service_role key for server-side (bypasses RLS)
    supabase_jwt_secret: str = ""
    metaapi_token: str = ""
    metaapi_account_id: str = ""
    gumroad_secret: str = ""
    admin_emails: str = ""
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    class Config:
        env_file = [
            os.path.join(_BACKEND_DIR, ".env"),
            os.path.join(_ROOT_DIR, ".env"),
            ".env",
        ]
        extra = "ignore"

settings = Settings()

if not settings.supabase_url:
    settings.supabase_url = os.getenv("VITE_SUPABASE_URL", "")
if not settings.supabase_key:
    settings.supabase_key = os.getenv("VITE_SUPABASE_ANON_KEY", "")
