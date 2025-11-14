"""
Database Schemas for Slug'sEra Ecommerce

Each Pydantic model corresponds to a MongoDB collection (lowercased class name).
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, EmailStr


class Product(BaseModel):
    title: str = Field(..., description="Product title")
    slug: str = Field(..., description="URL-safe identifier")
    description: str = Field(..., description="Long product description")
    price: float = Field(..., ge=0)
    colors: List[Literal["red", "off-white", "black", "coffee-brown"]] = Field(...)
    design_type: Literal["plain", "graphic", "embroidery"] = Field(...)
    images: List[str] = Field(..., description="Image URLs (front/back, close-ups)")
    in_stock: bool = Field(True)
    rating: float = Field(4.8, ge=0, le=5)
    gsm: int = Field(420, description="Fabric weight in GSM")
    fabric: str = Field("Cotton Fleece")
    details: List[str] = Field(default_factory=list, description="Bullet points")
    sizes: List[Literal["S", "M", "L", "XL", "XXL"]] = Field(default_factory=lambda: ["S","M","L","XL","XXL"])


class User(BaseModel):
    name: str
    email: EmailStr
    password_hash: str
    wishlist: List[str] = Field(default_factory=list, description="Product slugs")


class CartItem(BaseModel):
    product_slug: str
    qty: int = Field(1, ge=1)
    size: Literal["S", "M", "L", "XL", "XXL"]
    color: Literal["red", "off-white", "black", "coffee-brown"]


class Address(BaseModel):
    full_name: str
    phone: str
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str


class Order(BaseModel):
    user_email: Optional[EmailStr] = None
    guest: bool = True
    items: List[CartItem]
    address: Address
    payment_method: Literal["COD", "PREPAID"]
    discount_code: Optional[str] = None
    subtotal: float
    discount: float
    shipping: float
    tax: float
    total: float
    status: Literal["pending", "confirmed", "shipped", "delivered", "cancelled"] = "pending"
