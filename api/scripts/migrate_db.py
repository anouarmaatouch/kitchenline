import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

def migrate():
    with app.app_context():
        # Check if columns exist, if not add them
        with db.engine.connect() as conn:
            # Check agent_on
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN agent_on BOOLEAN DEFAULT TRUE"))
                print("Added agent_on column")
            except Exception as e:
                print(f"agent_on column might already exist: {e}")
                
            # Check voice
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN voice VARCHAR(20) DEFAULT 'sage'"))
                print("Added voice column")
            except Exception as e:
                print(f"voice column might already exist: {e}")
                
            # Check is_admin
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                print("Added is_admin column")
            except Exception as e:
                print(f"is_admin column might already exist: {e}")
            
            conn.commit()

if __name__ == "__main__":
    migrate()
