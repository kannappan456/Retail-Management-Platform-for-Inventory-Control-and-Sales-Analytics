
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class VendorCreate(BaseModel):
    business_name: str = Field(
        ..., min_length=2, max_length=100
    )
    owner_name: str = Field(
        ..., min_length=2, max_length=100
    )
    email: EmailStr
    phone: Optional[str] = Field(
        default=None, max_length=20
    )
    category: Optional[str] = Field(
        default=None, max_length=100
    )


class VendorResponse(BaseModel):
    vendor_id: int
    business_name: str
    owner_name: str
    email: EmailStr
    phone: Optional[str] = None
    category: Optional[str] = None
    status: str

    class Config:
        from_attributes = True
