
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal


class ProductCreate(BaseModel):
    vendor_id: int = Field(..., gt=0)
    product_name: str = Field(
        ..., min_length=2, max_length=150
    )
    category: Optional[str] = Field(
        default=None, max_length=100
    )
    price: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)


class ProductResponse(BaseModel):
    product_id: int
    vendor_id: int
    product_name: str
    category: Optional[str] = None
    price: Decimal

    class Config:
        from_attributes = True
