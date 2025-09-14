from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = 'pending'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'

class OrderBase(BaseModel):
    customer_name: str
    product_name: str
    status: OrderStatus = OrderStatus.PENDING

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    status: Optional[OrderStatus] = None

class Order(OrderBase):
    id: int
    updated_at: datetime

    class config:
        from_attributes = True

class DatabaseChangE(BaseModel):
    operation: str
    data: Optional[dict] = None
    old_data: Optional[dict] = None
    new_data: Optional[dict] = None
