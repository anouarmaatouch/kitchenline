from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
# Note: We don't use UserMixin anymore as it's for Flask-Login

class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    phone_number = Column(String(20), unique=True) # Normalized
    system_prompt = Column(Text)
    menu = Column(Text) 
    agent_on = Column(Boolean, default=True)
    voice = Column(String(20), default='Charon')
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    users = relationship('User', back_populates='company_ref', lazy='selectin')
    orders = relationship('Order', backref='company_ref', lazy='selectin')
    demands = relationship('Demand', backref='company_ref', lazy='selectin')
    menu_images = relationship('MenuImage', backref='company_ref', lazy='selectin', cascade="all, delete-orphan")

    def to_dict(self):
        try:
            menu_image_ids = [img.id for img in self.menu_images]
        except Exception:
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

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(256))
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    is_superadmin = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    
    # Explicit relationship for async compatibility
    company_ref = relationship('Company', back_populates='users', lazy='selectin')

    # We will handle password hashing in auth.py service service
    # The set_password/check_password methods are replaced by utility functions

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

class Order(Base):
    __tablename__ = 'orders'
    
    id = Column(Integer, primary_key=True)
    status = Column(String(20), default='recu') # recu, en_cours, termine
    order_detail = Column(Text, nullable=False)
    customer_name = Column(String(100))
    customer_phone = Column(String(20), index=True)
    company_phone = Column(String(20))
    address = Column(String(255), default='Non defini')
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
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

class PushSubscription(Base):
    __tablename__ = 'push_subscriptions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(String(255), nullable=False)
    auth = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh,
                'auth': self.auth
            }
        }

class Demand(Base):
    __tablename__ = 'demands'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    order_id = Column(Integer, ForeignKey('orders.id'), nullable=True)
    customer_name = Column(String(100))
    customer_phone = Column(String(20), index=True)
    content = Column(Text, nullable=False)
    status = Column(String(20), default='new')
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    order = relationship('Order', backref='demands', lazy='selectin')

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

class MenuImage(Base):
    __tablename__ = 'menu_images'
    
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'), nullable=False)
    image_data = Column(LargeBinary, nullable=False)
    filename = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
