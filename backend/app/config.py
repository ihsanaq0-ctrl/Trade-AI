from pydantic_settings import BaseSettings

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
        env_file = ".env"

settings = Settings()
