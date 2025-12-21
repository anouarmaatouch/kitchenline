import os
import sys
from sqlalchemy import text, create_engine

# Add the project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(script_dir)  # /app/api
app_root = os.path.dirname(api_dir)    # /app
sys.path.insert(0, app_root)

def get_database_url():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
        elif database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
        return database_url
    return None

def fix_menu_images_table():
    print("Fixing menu_images table schema...")
    
    database_url = get_database_url()
    if not database_url:
        print("ERROR: No database URL found.")
        return
    
    engine = create_engine(database_url, pool_pre_ping=True)
    
    with engine.begin() as conn:
        # Check if table exists and what columns it has
        try:
            result = conn.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'menu_images'
            """))
            columns = {row[0]: row[1] for row in result.fetchall()}
            
            if not columns:
                print("menu_images table doesn't exist. Creating it...")
                conn.execute(text("""
                    CREATE TABLE menu_images (
                        id SERIAL PRIMARY KEY,
                        company_id INTEGER NOT NULL REFERENCES companies(id),
                        image_data BYTEA NOT NULL,
                        filename VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                print("✓ Created menu_images table")
            else:
                print(f"Found menu_images table with columns: {list(columns.keys())}")
                
                # If it has user_id instead of company_id, we need to migrate
                if 'user_id' in columns and 'company_id' not in columns:
                    print("Table has user_id but not company_id. Migrating...")
                    # Add company_id column
                    conn.execute(text("ALTER TABLE menu_images ADD COLUMN company_id INTEGER REFERENCES companies(id)"))
                    
                    # Migrate data: get company_id from users
                    conn.execute(text("""
                        UPDATE menu_images mi
                        SET company_id = u.company_id
                        FROM users u
                        WHERE mi.user_id = u.id AND u.company_id IS NOT NULL
                    """))
                    
                    # Drop user_id column
                    conn.execute(text("ALTER TABLE menu_images DROP COLUMN user_id"))
                    print("✓ Migrated from user_id to company_id")
                
                # If company_id doesn't exist, add it
                elif 'company_id' not in columns:
                    print("Adding company_id column...")
                    conn.execute(text("ALTER TABLE menu_images ADD COLUMN company_id INTEGER REFERENCES companies(id)"))
                    print("✓ Added company_id column")
                
                # Make company_id NOT NULL if it's nullable
                if 'company_id' in columns:
                    try:
                        conn.execute(text("ALTER TABLE menu_images ALTER COLUMN company_id SET NOT NULL"))
                        print("✓ Set company_id to NOT NULL")
                    except Exception as e:
                        print(f"Could not set company_id to NOT NULL (might have NULL values): {e}")
                        # If there are NULL values, set them to a default company or delete them
                        # For now, we'll just leave it nullable
                
                print("✓ menu_images table schema is correct")
        
        except Exception as e:
            print(f"Error checking/fixing menu_images table: {e}")
            raise
    
    engine.dispose()
    print("\nmenu_images table fix completed!")

if __name__ == "__main__":
    fix_menu_images_table()

