from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=72)
    role: Literal["Customer", "Vendor"]

    # Required when registering as a Vendor
    business_name: Optional[str] = Field(
        default=None, min_length=2, max_length=100
    )
    owner_name: Optional[str] = Field(
        default=None, min_length=2, max_length=100
    )
    phone: Optional[str] = Field(
        default=None, max_length=20
    )
    category: Optional[str] = Field(
        default=None, max_length=100
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=72)


class UserResponse(BaseModel):
    user_id: int
    email: EmailStr
    role: str
    vendor_id: Optional[int] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse