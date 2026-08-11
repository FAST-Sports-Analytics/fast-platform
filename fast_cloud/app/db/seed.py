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

    # Commercial launch defaults. Existing standard plans are kept in sync so
    # Railway deployments pick up approved FAST pricing without manual DB edits.
    plan_defaults = [
        {"name": "Starter", "description": "For individual analysts and developing teams.", "monthly": 3900, "annual": 39000, "seats": 2, "devices": 2, "storage": 25, "products": ["analysis"], "sports": ["football"], "remote": False, "priority": False, "self_service": True},
        {"name": "Professional", "description": "For clubs and performance departments using connected analysis and review.", "monthly": 8900, "annual": 89000, "seats": 5, "devices": 5, "storage": 100, "products": ["analysis", "viewer"], "sports": [], "remote": True, "priority": True, "self_service": True},
        # Enterprise is intentionally quote-only: a zero amount must never become a free Stripe checkout.
        {"name": "Enterprise", "description": "For larger organisations requiring advanced platform features and tailored capacity.", "monthly": 0, "annual": 0, "seats": 25, "devices": 25, "storage": 500, "products": ["analysis", "viewer"], "sports": [], "remote": True, "priority": True, "self_service": False},
        {"name": "Custom", "description": "Individually configured commercial agreement.", "monthly": 0, "annual": 0, "seats": 1, "devices": 1, "storage": 0, "products": [], "sports": [], "remote": True, "priority": True, "self_service": False},
    ]
    for item in plan_defaults:
        plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.name == item["name"]))
        if not plan:
            plan = SubscriptionPlan(name=item["name"])
            db.add(plan)
        plan.description = item["description"]
        plan.monthly_price_pence = item["monthly"]
        plan.annual_price_pence = item["annual"]
        plan.included_seats = item["seats"]
        plan.max_devices = item["devices"]
        plan.cloud_storage_gb = item["storage"]
        plan.products_json = json.dumps(item["products"])
        plan.sports_json = json.dumps(item["sports"])
        plan.features_json = json.dumps({"remote_management": item["remote"], "priority_support": item["priority"]})
        plan.self_service_upgrades = item["self_service"]
        plan.active = True
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
