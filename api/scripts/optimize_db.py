import os
import sys
from sqlalchemy import text

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db

def optimize():
    app = create_app()
    with app.app_context():
        print("🚀 Starting Database Optimization...")
        
        try:
            # Add index to orders.customer_phone
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_orders_customer_phone ON orders (customer_phone);
            """))
            print("✅ Index created: idx_orders_customer_phone")
            
            # Add index to demands.customer_phone
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_demands_customer_phone ON demands (customer_phone);
            """))
            print("✅ Index created: idx_demands_customer_phone")
            
            db.session.commit()
            print("🎉 Database optimization complete!")
        except Exception as e:
            print(f"❌ Error during optimization: {e}")
            db.session.rollback()

if __name__ == "__main__":
    optimize()
