from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

class CompanyOut(BaseModel):
    id: int
    name: str
    phone_number: Optional[str] = None
    voice: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserOut(BaseModel):
    id: int
    username: str
    company_id: Optional[int]
    is_admin: bool
    is_superadmin: bool
    company_data: Optional[CompanyOut] = None
    
    class Config:
        from_attributes = True

class OrderBase(BaseModel):
    order_detail: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None
    company_phone: Optional[str] = None

class OrderOut(OrderBase):
    id: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DemandOut(BaseModel):
    id: int
    content: str
    status: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
