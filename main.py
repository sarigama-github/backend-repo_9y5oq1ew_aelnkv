import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import db, create_document, get_documents
from schemas import Product, Order, User

app = FastAPI(title="Slug'sEra API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"brand": "Slug'sEra", "status": "running"}


# ------------------------- Products -------------------------
@app.get("/api/products")
def list_products(color: Optional[str] = None, design_type: Optional[str] = None) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if color:
        query["colors"] = {"$in": [color]}
    if design_type:
        query["design_type"] = design_type
    products = get_documents("product", query)
    for p in products:
        p["_id"] = str(p["_id"])  # stringify id
    return products


@app.get("/api/products/{slug}")
def get_product(slug: str) -> Dict[str, Any]:
    items = get_documents("product", {"slug": slug}, limit=1)
    if not items:
        raise HTTPException(status_code=404, detail="Product not found")
    item = items[0]
    item["_id"] = str(item["_id"])
    return item


class SeedRequest(BaseModel):
    force: bool = False


@app.post("/api/seed")
def seed_products(payload: SeedRequest):
    # If products already exist and not force, skip
    existing = get_documents("product", {}, limit=1)
    if existing and not payload.force:
        return {"seeded": False, "message": "Products already exist"}

    # Optionally clear existing
    if payload.force:
        db["product"].delete_many({})

    base_details = [
        "420 GSM heavy-weight",
        "Premium cotton fleece",
        "Embroidered + patchwork details",
        "Pre-shrunk, soft-brushed interior",
    ]

    demo_images = lambda color: [
        f"https://images.placeholder.slugsera.com/{color}-front.jpg",
        f"https://images.placeholder.slugsera.com/{color}-back.jpg",
        f"https://images.placeholder.slugsera.com/{color}-embroidery.jpg",
        f"https://images.placeholder.slugsera.com/{color}-patchwork.jpg",
    ]

    data: List[Product] = [
        Product(
            title="Slug'sEra Companion Hoodie – Red",
            slug="companion-hoodie-red",
            description="Signature 420 GSM heavy-weight hoodie with raised embroidery and patchwork.",
            price=109.0,
            colors=["red"],
            design_type="embroidery",
            images=demo_images("red"),
            details=base_details,
        ),
        Product(
            title="Slug'sEra Companion Hoodie – Off-White",
            slug="companion-hoodie-off-white",
            description="Premium off-white with tonal embroidery and textured patchwork.",
            price=109.0,
            colors=["off-white"],
            design_type="embroidery",
            images=demo_images("off-white"),
            details=base_details,
        ),
        Product(
            title="Slug'sEra Companion Hoodie – Black",
            slug="companion-hoodie-black",
            description="Matte black, deep-ink graphic and stitched emblem.",
            price=109.0,
            colors=["black"],
            design_type="graphic",
            images=demo_images("black"),
            details=base_details,
        ),
        Product(
            title="Slug'sEra Companion Hoodie – Coffee Brown",
            slug="companion-hoodie-coffee-brown",
            description="Warm coffee brown with chenille patchwork and embroidery mix.",
            price=109.0,
            colors=["coffee-brown"],
            design_type="embroidery",
            images=demo_images("coffee-brown"),
            details=base_details,
        ),
    ]

    inserted = []
    for prod in data:
        inserted_id = create_document("product", prod)
        inserted.append(inserted_id)

    return {"seeded": True, "inserted": inserted}


# ------------------------- Pricing / Cart Calc -------------------------
class CalcItem(BaseModel):
    product_slug: str
    qty: int
    size: str
    color: str


class CalcRequest(BaseModel):
    items: List[CalcItem]
    discount_code: Optional[str] = None
    country: str = "IN"
    state: Optional[str] = None
    postal_code: Optional[str] = None


@app.post("/api/calc")
def calculate_order(payload: CalcRequest):
    # Fetch product prices
    slugs = [i.product_slug for i in payload.items]
    items_map = {i["slug"]: i for i in get_documents("product", {"slug": {"$in": slugs}})}

    if len(items_map) != len(set(slugs)):
        raise HTTPException(status_code=400, detail="Invalid product in cart")

    breakdown = []
    subtotal = 0.0
    for ci in payload.items:
        prod = items_map[ci.product_slug]
        line = prod["price"] * ci.qty
        subtotal += line
        breakdown.append({
            "slug": ci.product_slug,
            "title": prod["title"],
            "price": prod["price"],
            "qty": ci.qty,
            "line_total": round(line, 2)
        })

    discount = 0.0
    if payload.discount_code:
        code = payload.discount_code.strip().upper()
        if code in ("SLUG10", "WELCOME10"):
            discount = 0.10 * subtotal
        elif code == "VIP20":
            discount = 0.20 * subtotal

    after_discount = max(subtotal - discount, 0.0)

    # Simple shipping logic: free over $150, else $8 domestic / $25 international
    is_domestic = payload.country.upper() in ("IN", "INDIA")
    shipping = 0.0 if after_discount >= 150 else (8.0 if is_domestic else 25.0)

    # Tax: 5% domestic, 0% international (simplified)
    tax = (0.05 * after_discount) if is_domestic else 0.0

    total = after_discount + shipping + tax

    return {
        "items": breakdown,
        "subtotal": round(subtotal, 2),
        "discount": round(discount, 2),
        "shipping": round(shipping, 2),
        "tax": round(tax, 2),
        "total": round(total, 2),
    }


# ------------------------- Orders -------------------------
@app.post("/api/orders")
def create_order(payload: Order):
    # Recalculate totals server-side for integrity
    calc = calculate_order(CalcRequest(
        items=[CalcItem(product_slug=i.product_slug, qty=i.qty, size=i.size, color=i.color) for i in payload.items],
        discount_code=payload.discount_code,
        country=payload.address.country,
        postal_code=payload.address.postal_code,
    ))

    # Persist order
    order_id = create_document("order", {
        **payload.model_dump(),
        **calc,
        "status": "confirmed" if payload.payment_method == "COD" else "pending",
    })

    return {"order_id": order_id, "status": "ok", "summary": calc}


# ------------------------- Auth (Simple) -------------------------
class AuthPayload(BaseModel):
    name: Optional[str] = None
    email: str
    password: str


@app.post("/api/users/register")
def register_user(data: AuthPayload):
    # Ensure unique email
    existing = get_documents("user", {"email": data.email}, limit=1)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    import hashlib
    pwd_hash = hashlib.sha256(data.password.encode()).hexdigest()
    u = User(name=data.name or data.email.split("@")[0], email=data.email, password_hash=pwd_hash)
    uid = create_document("user", u)
    return {"user_id": uid, "email": data.email}


@app.post("/api/users/login")
def login_user(data: AuthPayload):
    import hashlib
    pwd_hash = hashlib.sha256(data.password.encode()).hexdigest()
    user = get_documents("user", {"email": data.email, "password_hash": pwd_hash}, limit=1)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"email": data.email, "ok": True}


# ------------------------- Policies -------------------------
@app.get("/api/policies")
def get_policies():
    return {
        "terms": "Use of this site constitutes acceptance of our Terms & Conditions.",
        "refund": "Refunds/Returns accepted within 7 days in unworn condition.",
        "shipping": "Orders ship within 48 hours. Free shipping on qualifying orders.",
        "privacy": "We respect your privacy. Data is used solely to fulfill orders.",
    }


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
