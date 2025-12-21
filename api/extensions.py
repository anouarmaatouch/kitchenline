from flask_sqlalchemy import SQLAlchemy
from flask_sock import Sock

# Configure database with connection pooling for high concurrency
db = SQLAlchemy(
    engine_options={
        'pool_size': 50,           # Base connection pool size
        'max_overflow': 100,       # Additional connections when needed
        'pool_pre_ping': True,     # Verify connections before use
        'pool_recycle': 3600,      # Recycle connections every hour
        'echo': False,             # Set to True for SQL debugging
    }
)
sock = Sock()
