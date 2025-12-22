from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
from config.config import Config

import urllib.parse

# Ensure we use the async driver
DATABASE_URL = Config.SQLALCHEMY_DATABASE_URI
connect_args = {}

if DATABASE_URL:
    if DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    # Fix for asyncpg not supporting sslmode query param
    if "sslmode" in DATABASE_URL:
        parsed = urllib.parse.urlparse(DATABASE_URL)
        qs = urllib.parse.parse_qs(parsed.query)
        
        # If sslmode provided, strip it and use connect_args
        if "sslmode" in qs:
            sslmode = qs["sslmode"][0]
            del qs["sslmode"]
            
            # Rebuild URL without sslmode
            new_query = urllib.parse.urlencode(qs, doseq=True)
            DATABASE_URL = urllib.parse.urlunparse(parsed._replace(query=new_query))
            
            if sslmode == 'require':
                # Create a custom SSL context that doesn't verify
                # This mimics libpq's sslmode=require behavior (encryption, no verification)
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connect_args["ssl"] = ssl_context
            elif sslmode == 'disable':
                connect_args["ssl"] = False

engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    future=True, 
    pool_pre_ping=True, 
    connect_args=connect_args,
    pool_size=20,
    max_overflow=40
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session

from sqlalchemy.orm import declarative_base
Base = declarative_base()
