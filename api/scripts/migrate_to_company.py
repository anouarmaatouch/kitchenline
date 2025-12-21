import os
import sys
from sqlalchemy import text, create_engine

# Try to import psycopg2 to ensure it's available
try:
    import psycopg2
except ImportError:
    try:
        import psycopg2_binary as psycopg2
    except ImportError:
        print("WARNING: psycopg2 not found. PostgreSQL driver may not work.")

# Add the project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
api_dir = os.path.dirname(script_dir)  # /app/api
app_root = os.path.dirname(api_dir)    # /app
sys.path.insert(0, app_root)

# Get database URL directly from environment or config, without importing app
def get_database_url():
    # Try environment variable first
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return database_url
    
    # Try SQLALCHEMY_DATABASE_URI
    database_url = os.environ.get('SQLALCHEMY_DATABASE_URI')
    if database_url:
        return database_url
    
    # Try loading from config file
    try:
        from api.config.config import Config
        return Config.SQLALCHEMY_DATABASE_URI
    except:
        pass
    
    return None

def migrate():
    print("Starting migration to Company-based architecture...")
    
    # Get database URL without initializing the full app
    database_url = get_database_url()
    if not database_url:
        print("ERROR: No database URL found. Set DATABASE_URL environment variable.")
        return
    
    # Fix postgres:// to postgresql:// (SQLAlchemy requires postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+psycopg2://', 1)
    elif database_url.startswith('postgresql://'):
        # Ensure we use psycopg2 driver
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    
    print(f"Connecting to database...")
    print(f"Database URL: {database_url[:50]}...")  # Print first 50 chars for debugging
    
    try:
        # Create a direct engine connection (bypassing Flask-SQLAlchemy entirely)
        # Use psycopg2 driver explicitly
        engine = create_engine(database_url, pool_pre_ping=True)
    except Exception as e:
        print(f"ERROR creating database engine: {e}")
        print("Make sure psycopg2 or psycopg2-binary is installed:")
        print("  pip install psycopg2-binary")
        raise
    
    with engine.begin() as conn:
        # 1. Migrate Users to Companies using raw SQL
        print("Migrating users to companies...")
        
        # Get all users
        users_result = conn.execute(text("SELECT id, username, company, phone_number, system_prompt, menu, agent_on, voice, is_admin FROM users"))
        users = users_result.fetchall()
        
        for user_row in users:
            user_id, username, old_company_name, old_phone, old_prompt, old_menu, old_agent_on, old_voice, old_is_admin = user_row
            
            # Check if company already exists for this phone
            if old_phone:
                company_result = conn.execute(
                    text("SELECT id FROM companies WHERE phone_number = :phone"),
                    {"phone": old_phone}
                )
                company_row = company_result.fetchone()
                
                if company_row:
                    company_id = company_row[0]
                else:
                    # Create new company
                    conn.execute(
                        text("""
                            INSERT INTO companies (name, phone_number, system_prompt, menu, agent_on, voice, created_at)
                            VALUES (:name, :phone, :prompt, :menu, :agent_on, :voice, CURRENT_TIMESTAMP)
                        """),
                        {
                            "name": old_company_name or f"{username}'s Restaurant",
                            "phone": old_phone,
                            "prompt": old_prompt,
                            "menu": old_menu,
                            "agent_on": old_agent_on if old_agent_on is not None else True,
                            "voice": old_voice or 'sage'
                        }
                    )
                    company_result = conn.execute(
                        text("SELECT id FROM companies WHERE phone_number = :phone"),
                        {"phone": old_phone}
                    )
                    company_id = company_result.fetchone()[0]
            else:
                # No phone number, create company with username-based name
                conn.execute(
                    text("""
                        INSERT INTO companies (name, phone_number, system_prompt, menu, agent_on, voice, created_at)
                        VALUES (:name, NULL, :prompt, :menu, :agent_on, :voice, CURRENT_TIMESTAMP)
                    """),
                    {
                        "name": old_company_name or f"{username}'s Restaurant",
                        "prompt": old_prompt,
                        "menu": old_menu,
                        "agent_on": old_agent_on if old_agent_on is not None else True,
                        "voice": old_voice or 'sage'
                    }
                )
                # Get the last inserted company (for this user)
                company_result = conn.execute(
                    text("SELECT id FROM companies WHERE name = :name ORDER BY id DESC LIMIT 1"),
                    {"name": old_company_name or f"{username}'s Restaurant"}
                )
                company_id = company_result.fetchone()[0]
            
            # Update user with company_id
            is_superadmin = (username == 'admin')
            conn.execute(
                text("""
                    UPDATE users 
                    SET company_id = :company_id, 
                        is_superadmin = :is_superadmin,
                        is_admin = :is_admin
                    WHERE id = :user_id
                """),
                {
                    "company_id": company_id,
                    "is_superadmin": is_superadmin,
                    "is_admin": old_is_admin if old_is_admin is not None else is_superadmin,
                    "user_id": user_id
                }
            )
            print(f"  Migrated user: {username} -> Company ID: {company_id}")
        
        print("✓ Users migrated to Companies.")
        
        # 2. Link Orders to Companies
        print("Linking orders to companies...")
        orders_result = conn.execute(
            text("SELECT id, company_phone FROM orders WHERE company_id IS NULL")
        )
        orders = orders_result.fetchall()
        
        for order_row in orders:
            order_id, company_phone = order_row
            if company_phone:
                company_result = conn.execute(
                    text("SELECT id FROM companies WHERE phone_number = :phone"),
                    {"phone": company_phone}
                )
                company_row = company_result.fetchone()
                if company_row:
                    conn.execute(
                        text("UPDATE orders SET company_id = :company_id WHERE id = :order_id"),
                        {"company_id": company_row[0], "order_id": order_id}
                    )
        
        print("✓ Orders linked to Companies.")
        
        # 3. Link Demands to Companies
        print("Linking demands to companies...")
        # First via orders
        conn.execute(text("""
            UPDATE demands d
            SET company_id = o.company_id
            FROM orders o
            WHERE d.order_id = o.id 
              AND d.company_id IS NULL 
              AND o.company_id IS NOT NULL
        """))
        
        # Then via users
        conn.execute(text("""
            UPDATE demands d
            SET company_id = u.company_id
            FROM users u
            WHERE d.user_id = u.id 
              AND d.company_id IS NULL 
              AND u.company_id IS NOT NULL
        """))
        
        print("✓ Demands linked to Companies.")
    
    engine.dispose()
    print("\nMigration completed successfully!")

if __name__ == "__main__":
    migrate()
