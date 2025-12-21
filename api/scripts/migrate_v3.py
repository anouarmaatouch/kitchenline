import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def migrate():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found")
        return

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        print("Adding customer_name and customer_phone to demands table...")
        
        # Add customer_name
        try:
            cur.execute("ALTER TABLE demands ADD COLUMN customer_name VARCHAR(100);")
            print("Added customer_name column.")
        except Exception as e:
            conn.rollback()
            print(f"customer_name column might already exist: {e}")

        # Add customer_phone
        try:
            cur.execute("ALTER TABLE demands ADD COLUMN customer_phone VARCHAR(20);")
            print("Added customer_phone column.")
        except Exception as e:
            conn.rollback()
            print(f"customer_phone column might already exist: {e}")

        conn.commit()
        cur.close()
        conn.close()
        print("Migration V3 successful.")

    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
