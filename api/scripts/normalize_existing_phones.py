import sys
import os

# Add the parent directory to sys.path to import modules correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from extensions import db
from models.models import User, Order, Demand
from utils.phone import normalize_phone

def normalize_all():
    with app.app_context():
        print("Starting normalization of existing phone numbers...")
        
        # Normalize Users
        users = User.query.all()
        for user in users:
            if user.phone_number:
                normalized = normalize_phone(user.phone_number)
                if normalized != user.phone_number:
                    print(f"Normalizing User {user.username}: {user.phone_number} -> {normalized}")
                    user.phone_number = normalized
        
        # Normalize Orders
        orders = Order.query.all()
        for order in orders:
            if order.customer_phone:
                normalized_cust = normalize_phone(order.customer_phone)
                if normalized_cust != order.customer_phone:
                    print(f"Normalizing Order {order.id} (customer): {order.customer_phone} -> {normalized_cust}")
                    order.customer_phone = normalized_cust
            
            if order.company_phone:
                normalized_comp = normalize_phone(order.company_phone)
                if normalized_comp != order.company_phone:
                    print(f"Normalizing Order {order.id} (company): {order.company_phone} -> {normalized_comp}")
                    order.company_phone = normalized_comp
        
        # Normalize Demands
        demands = Demand.query.all()
        for demand in demands:
            if demand.customer_phone:
                normalized = normalize_phone(demand.customer_phone)
                if normalized != demand.customer_phone:
                    print(f"Normalizing Demand {demand.id}: {demand.customer_phone} -> {normalized}")
                    demand.customer_phone = normalized
        
        db.session.commit()
        print("Normalization completed successfully.")

if __name__ == "__main__":
    normalize_all()
