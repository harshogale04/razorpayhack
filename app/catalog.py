"""
Agent-readable catalog. Deliberately minimal: structured fields an AI buyer
needs to decide and act, nothing a human-facing storefront would add
(no marketing copy, no images, no upsell text).
"""

# Seed data - swap for a real product DB later. Prices are in paise.
PRODUCTS = [
    {"product_id": "sku-001", "sku": "TSHIRT-BLK-M", "unit_weight_g": 180, "stock": 42, "price_paise": 79900},
    {"product_id": "sku-002", "sku": "MUG-CERAMIC-350ML", "unit_weight_g": 320, "stock": 15, "price_paise": 34900},
    {"product_id": "sku-003", "sku": "NOTEBOOK-A5-DOT", "unit_weight_g": 210, "stock": 60, "price_paise": 24900},
    {"product_id": "sku-004", "sku": "BACKPACK-CANVAS-20L", "unit_weight_g": 650, "stock": 8, "price_paise": 249900},
    {"product_id": "sku-005", "sku": "WATERBOTTLE-STEEL-750ML", "unit_weight_g": 280, "stock": 3, "price_paise": 89900},
]


def get_catalog():
    return PRODUCTS


def get_product(product_id: str):
    for p in PRODUCTS:
        if p["product_id"] == product_id:
            return p
    return None


def decrement_stock(product_id: str, quantity: int) -> bool:
    product = get_product(product_id)
    if product is None or product["stock"] < quantity:
        return False
    product["stock"] -= quantity
    return True
