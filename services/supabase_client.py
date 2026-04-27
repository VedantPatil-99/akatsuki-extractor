from supabase import create_client, Client
from core.config import settings

supabase: Client = create_client(
    settings.SUPABASE_URL, 
    settings.SUPABASE_SECRET_KEY
)