"""
Migration script to add company_phone column to orders table.
Run this after updating models.py.
"""
from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Add company_phone column if it doesn't exist
    try:
        db.session.execute(text("""
            ALTER TABLE orders ADD COLUMN IF NOT EXISTS company_phone VARCHAR(20);
        """))
        db.session.commit()
        print("✅ Added company_phone column to orders table")
    except Exception as e:
        print(f"Column may already exist or error: {e}")
        db.session.rollback()
    
    # Update address default for existing rows
    try:
        db.session.execute(text("""
            UPDATE orders SET address = 'Non defini' WHERE address IS NULL OR address = '' OR address = 'Pickup';
        """))
        db.session.commit()
        print("✅ Updated existing orders with default address")
    except Exception as e:
        print(f"Error updating addresses: {e}")
        db.session.rollback()

    print("Migration complete!")
