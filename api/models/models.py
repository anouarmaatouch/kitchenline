from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from extensions import db

class Company(db.Model):
    __tablename__ = 'companies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone_number = db.Column(db.String(20), unique=True) # Normalized
    system_prompt = db.Column(db.Text)
    menu = db.Column(db.Text) 
    agent_on = db.Column(db.Boolean, default=True)
    voice = db.Column(db.String(20), default='Charon')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='company_ref', lazy=True)
    orders = db.relationship('Order', backref='company_ref', lazy=True)
    demands = db.relationship('Demand', backref='company_ref', lazy=True)
    menu_images = db.relationship('MenuImage', backref='company_ref', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        try:
            menu_image_ids = [img.id for img in self.menu_images]
        except Exception:
            # If menu_images relationship fails (e.g., table doesn't exist or column missing)
            menu_image_ids = []
        
        return {
            'id': self.id,
            'name': self.name,
            'phone_number': self.phone_number,
            'voice': self.voice,
            'agent_on': self.agent_on,
            'system_prompt': self.system_prompt,
            'menu': self.menu,
            'created_at': self.created_at.isoformat(),
            'menu_images': menu_image_ids
        }

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    is_superadmin = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'company_id': self.company_id,
            'is_superadmin': self.is_superadmin,
            'is_admin': self.is_admin,
            'company_data': self.company_ref.to_dict() if self.company_ref else None,
            'menu_images': [img.id for img in (self.company_ref.menu_images if self.company_ref else [])]
        }

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='recu') # recu, en_cours, termine
    order_detail = db.Column(db.Text, nullable=False)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20), index=True)
    company_phone = db.Column(db.String(20))  # The restaurant phone number this order belongs to
    address = db.Column(db.String(255), default='Non defini')
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
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
            'company_phone': self.company_ref.phone_number if self.company_ref else self.company_phone,
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

class Demand(db.Model):
    __tablename__ = 'demands'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Optional link to restaurant user
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True) # Optional link to an order
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20), index=True)
    content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='new') # new, processed
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    order = db.relationship('Order', backref=db.backref('demands', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'content': self.content,
            'status': self.status,
            'order_id': self.order_id,
            'customer_name': self.customer_name,
            'customer_phone': self.customer_phone,
            'created_at': self.created_at.isoformat()
        }

class MenuImage(db.Model):
    __tablename__ = 'menu_images'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=False) # Storing image as bytes
    filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

