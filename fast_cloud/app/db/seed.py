from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LicenceTemplate, Product, Sport, SubscriptionPlan

PRODUCTS = [
    ("analysis", "FAST Analysis", "Multi-sport coding and analysis application."),
    ("viewer", "FAST Viewer", "Review, annotate and comment on delivered clips."),
]
SPORTS = [
    ("football", "Football"), ("rugby", "Rugby"), ("cricket", "Cricket"),
    ("basketball", "Basketball"), ("baseball", "Baseball"),
    ("volleyball", "Volleyball"), ("tennis", "Tennis"),
    ("field_hockey", "Field Hockey"), ("ice_hockey", "Ice Hockey"),
    ("netball", "Netball"),
]


def seed_catalogue(db: Session) -> None:
    for key, name, description in PRODUCTS:
        if not db.scalar(select(Product).where(Product.key == key)):
            db.add(Product(key=key, name=name, description=description))
    for key, name in SPORTS:
        if not db.scalar(select(Sport).where(Sport.key == key)):
            db.add(Sport(key=key, name=name))
    db.flush()

    plan_defaults = [
        {"name": "Starter", "description": "Entry plan for small teams.", "seats": 2, "devices": 2, "products": ["analysis"], "sports": ["football"]},
        {"name": "Professional", "description": "Configurable multi-product plan.", "seats": 5, "devices": 5, "products": ["analysis", "viewer"], "sports": []},
        {"name": "Enterprise", "description": "Large organisation plan with advanced platform features.", "seats": 25, "devices": 25, "products": ["analysis", "viewer"], "sports": []},
        {"name": "Custom", "description": "Individually configured commercial agreement.", "seats": 1, "devices": 1, "products": [], "sports": []},
    ]
    for item in plan_defaults:
        if not db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == item["name"])):
            db.add(SubscriptionPlan(
                name=item["name"], description=item["description"], included_seats=item["seats"],
                max_devices=item["devices"], products_json=json.dumps(item["products"]),
                sports_json=json.dumps(item["sports"]), monthly_price_pence=0, annual_price_pence=0,
                features_json=json.dumps({"remote_management": item["name"] in {"Professional", "Enterprise", "Custom"}}),
            ))
    db.flush()

    defaults = [
        {
            "name": "FAST Starter Individual", "owner_type": "individual", "tier": "FAST Starter",
            "products": ["analysis"], "sports": ["football"], "devices": 1, "users": 1, "days": 365,
        },
        {
            "name": "FAST Professional Individual", "owner_type": "individual", "tier": "FAST Professional",
            "products": ["analysis", "viewer"], "sports": [], "devices": 2, "users": 1, "days": 365,
        },
        {
            "name": "FAST Professional Club", "owner_type": "club", "tier": "FAST Professional Club",
            "products": ["analysis", "viewer"], "sports": [], "devices": 5, "users": 10, "days": 365,
        },
        {
            "name": "FAST Enterprise Club", "owner_type": "club", "tier": "FAST Enterprise",
            "products": ["analysis", "viewer"], "sports": [], "devices": 25, "users": 100, "days": None,
        },
    ]
    for item in defaults:
        if not db.scalar(select(LicenceTemplate).where(LicenceTemplate.name == item["name"])):
            db.add(LicenceTemplate(
                name=item["name"], owner_type=item["owner_type"], tier=item["tier"],
                products_json=json.dumps(item["products"]), sports_json=json.dumps(item["sports"]),
                default_max_devices=item["devices"], default_max_users=item["users"],
                default_duration_days=item["days"], renewable=True,
            ))
    db.commit()
