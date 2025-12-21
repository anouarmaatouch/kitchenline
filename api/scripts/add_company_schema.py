import os
import sys
from sqlalchemy import text, create_engine

# Add the project root to sys.path
# When running from /app, we need /app in the path
script_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(script_dir)  # /app/api
app_root = os.path.dirname(api_dir)    # /app
sys.path.insert(0, app_root)

# Now we can import from api.*
from api.app import create_app
from api.extensions import db

def add_schema():
    app = create_app()
    with app.app_context():
        print("Adding Company schema to database...")
        
        # Get database URL from app config
        database_url = app.config.get('SQLALCHEMY_DATABASE_URI') or app.config.get('DATABASE_URL')
        if not database_url:
            print("ERROR: No database URL found in app config")
            return
        
        # Create a direct engine connection (bypassing Flask-SQLAlchemy context issues)
        engine = create_engine(database_url)
        
        with engine.begin() as conn:
            # Create companies table if it doesn't exist
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(120) NOT NULL,
                        phone_number VARCHAR(20) UNIQUE,
                        system_prompt TEXT,
                        menu TEXT,
                        agent_on BOOLEAN DEFAULT TRUE,
                        voice VARCHAR(20) DEFAULT 'sage',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("✓ Companies table created/verified")
            except Exception as e:
                print(f"Companies table error (might already exist): {str(e)}")
            
            # Add company_id to users table
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN company_id INTEGER REFERENCES companies(id)"))
                print("✓ Added company_id to users table")
            except Exception as e:
                print(f"company_id column might already exist: {str(e)}")
            
            # Add company_id to orders table
            try:
                conn.execute(text("ALTER TABLE orders ADD COLUMN company_id INTEGER REFERENCES companies(id)"))
                print("✓ Added company_id to orders table")
            except Exception as e:
                print(f"company_id column might already exist in orders: {str(e)}")
            
            # Add company_id to demands table
            try:
                conn.execute(text("ALTER TABLE demands ADD COLUMN company_id INTEGER REFERENCES companies(id)"))
                print("✓ Added company_id to demands table")
            except Exception as e:
                print(f"company_id column might already exist in demands: {str(e)}")
            
            # Create menu_images table if it doesn't exist
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS menu_images (
                        id SERIAL PRIMARY KEY,
                        company_id INTEGER NOT NULL REFERENCES companies(id),
                        image_data BYTEA NOT NULL,
                        filename VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("✓ Menu images table created/verified")
            except Exception as e:
                print(f"Menu images table error (might already exist): {str(e)}")
            
            # Add is_superadmin to users if it doesn't exist
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE"))
                print("✓ Added is_superadmin to users table")
            except Exception as e:
                print(f"is_superadmin column might already exist: {str(e)}")
        
        engine.dispose()
        print("\nSchema update completed!")

if __name__ == "__main__":
    add_schema()
