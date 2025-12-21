import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')
    
    # Fix for SQLAlchemy requiring 'postgresql://' but Fly providing 'postgres://'
    uri = os.environ.get('DATABASE_URL')
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
        
    SQLALCHEMY_DATABASE_URI = uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Handle stale connections (Fly.io/Postgres)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 20,
        "max_overflow": 10,
    }
    
    # Vonage
    VONAGE_API_KEY = os.environ.get('VONAGE_API_KEY')
    VONAGE_API_SECRET = os.environ.get('VONAGE_API_SECRET')
    VONAGE_APPLICATION_ID = os.environ.get('VONAGE_APPLICATION_ID')
    VONAGE_PRIVATE_KEY_PATH = os.environ.get('VONAGE_PRIVATE_KEY_PATH')
    
    # OpenAI (legacy, can be removed)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    
    # Gemini
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # Server
    PUBLIC_URL = os.environ.get('PUBLIC_URL')

    # Defaults
    DEFAULT_SYSTEM_PROMPT = os.environ.get('DEFAULT_SYSTEM_PROMPT', "You are a helpful AI assistant taking food orders.")

    # VAPID / Web Push
    VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY')
    VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY')
    VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@example.com')
