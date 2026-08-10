from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Iterable


ROLE_PRODUCTS: dict[str, set[str] | None] = {
    "administrator": None,
    "analyst": {"analysis", "viewer", "hub"},
    "coach": {"viewer", "hub"},
    "scout": {"scout"},
}


def normalise_product(value: object) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    if text.startswith("fast_"):
        text = text[5:]
    aliases = {"bench_viewer": "viewer"}
    return aliases.get(text, text)


def effective_role(*, role: str | None, is_platform_admin: bool) -> str:
    return "administrator" if is_platform_admin else str(role or "analyst").strip().lower()


def _json_list(raw: object) -> list[str]:
    if isinstance(raw, str):
        try:
            value = json.loads(raw or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    else:
        value = raw
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if str(item).strip()]


def filter_products(
    licence_products: object,
    *,
    role: str | None,
    is_platform_admin: bool = False,
    assigned_products: object = None,
) -> list[str]:
    original = _json_list(licence_products)
    role_key = effective_role(role=role, is_platform_admin=is_platform_admin)
    allowed = ROLE_PRODUCTS.get(role_key, set())

    result: list[str] = []
    for item in original:
        key = normalise_product(item)
        if allowed is None or key in allowed:
            result.append(item)

    # Empty assignment means "use the role defaults". This preserves the
    # existing organisation workflow where role selection alone grants its
    # standard products; a non-empty assignment narrows those defaults.
    assigned = {normalise_product(item) for item in _json_list(assigned_products)}
    if assigned:
        result = [item for item in result if normalise_product(item) in assigned]
    return result


def filter_sports(licence_sports: object, *, assigned_sports: object = None) -> list[str]:
    original = _json_list(licence_sports)
    assigned = {str(item).strip().lower() for item in _json_list(assigned_sports)}
    if not assigned:
        return original
    return [item for item in original if str(item).strip().lower() in assigned]


def licence_is_current(status: object, expires_at: datetime | None) -> bool:
    if str(status or "").strip().lower() != "active":
        return False
    if expires_at is None:
        return True
    expiry = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=timezone.utc)
    return expiry > datetime.now(timezone.utc)
