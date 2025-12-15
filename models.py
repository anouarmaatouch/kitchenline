from datetime import datetime
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    company = db.Column(db.String(120))
    password_hash = db.Column(db.String(256))
    system_prompt = db.Column(db.Text)
    phone_number = db.Column(db.String(20)) # The phone number associated with this account (business phone)
    menu = db.Column(db.Text) # JSON or text representation of the menu
    agent_on = db.Column(db.Boolean, default=True)
    voice = db.Column(db.String(20), default='sage')
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'company': self.company,
            'phone_number': self.phone_number,
            'voice': self.voice,
            'agent_on': self.agent_on,
            'system_prompt': self.system_prompt,
            'menu': self.menu,
            'is_admin': self.is_admin
        }

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='recu') # recu, en_cours, termine
    order_detail = db.Column(db.Text, nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    company_phone = db.Column(db.String(20))  # The restaurant phone number this order belongs to
    address = db.Column(db.String(255), default='Non defini')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Optional: Link order to a specific user (restaurant) if needed in future
    # user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'status': self.status,
            'order_detail': self.order_detail,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'company_phone': self.company_phone,
            'address': self.address,
            'created_at': self.created_at.isoformat()
        }

class PushSubscription(db.Model):
    __tablename__ = 'push_subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh,
                'auth': self.auth
            }
        }
