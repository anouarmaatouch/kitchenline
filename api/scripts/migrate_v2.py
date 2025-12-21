import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Create Demands table
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS demands (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    order_id INTEGER REFERENCES orders(id),
                    content TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'new',
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
                );
            """))
            print("Created demands table.")
            
            # Create MenuImages table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS menu_images (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    image_data BYTEA NOT NULL,
                    filename VARCHAR(255),
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() AT TIME ZONE 'utc')
                );
            """))
            print("Created menu_images table.")
            
            conn.commit()
    except Exception as e:
        print(f"Error creating tables: {e}")
