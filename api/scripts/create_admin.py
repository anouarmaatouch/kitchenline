import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db
from models.models import User

app = create_app()

def create_admin():
    with app.app_context():
        # Check if any user exists
        user = User.query.first()
        
        target_username = "admin"
        target_password = "password123"
        
        if not user:
            print(f"No users found. Creating default admin user '{target_username}'...")
            admin = User(
                username=target_username,
                company="My Restaurant",
                phone_number="123456789",
                agent_on=True,
                voice='sage',
                is_admin=True,
                system_prompt="You are a helpful assistant.",
                menu="Burger: $10"
            )
            admin.set_password(target_password)
            db.session.add(admin)
            db.session.commit()
            print(f"Admin user '{target_username}' created successfully with password '{target_password}'!")
        else:
            print(f"User(s) exist. Promoting/Fixing '{user.username}'...")
            # Force rename to 'admin' and reset password
            user.username = target_username
            user.is_admin = True
            user.set_password(target_password)
            db.session.commit()
            print(f"User updated to admin/{target_password}. Verify login now.")

if __name__ == "__main__":
    create_admin()
