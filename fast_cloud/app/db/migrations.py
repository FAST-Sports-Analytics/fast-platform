from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def migrate_schema(engine: Engine) -> None:
    """Small idempotent SQLite-safe migration for v0.3.0c.

    Existing installations keep their users, clubs, licences and activations.
    New tables are created by metadata.create_all before this function runs.
    """
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "last_login_at" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
        with engine.begin() as connection:
            if "organisation_id" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN organisation_id INTEGER REFERENCES organisations(id)"))
            if "role" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(40) NOT NULL DEFAULT 'analyst'"))
            if "products_json" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN products_json TEXT NOT NULL DEFAULT '[]'"))
            if "sports_json" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN sports_json TEXT NOT NULL DEFAULT '[]'"))
            if "must_change_password" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0"))
            if "invited_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN invited_at DATETIME"))
            if "invitation_token_hash" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN invitation_token_hash VARCHAR(64)"))
            if "invitation_expires_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN invitation_expires_at DATETIME"))
            if "password_reset_token_hash" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_reset_token_hash VARCHAR(64)"))
            if "password_reset_expires_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_reset_expires_at DATETIME"))
            # ``is_admin`` is reserved for platform-wide FAST administrators.
            # Older builds also set it for organisation administrators; retain
            # their role while removing unintended global Cloud Admin access.
            connection.execute(text("UPDATE users SET role='administrator' WHERE is_admin IS TRUE AND organisation_id IS NOT NULL"))
            connection.execute(text("UPDATE users SET is_admin=FALSE WHERE organisation_id IS NOT NULL"))
            connection.execute(text("UPDATE users SET role='administrator' WHERE is_admin IS TRUE AND organisation_id IS NULL"))
            connection.execute(text("UPDATE users SET role='analyst' WHERE role IS NULL OR role=''"))


    if "organisations" in table_names:
        organisation_columns = {column["name"] for column in inspector.get_columns("organisations")}
        organisation_additions = {
            "subscription_tier": "VARCHAR(80) NOT NULL DEFAULT 'FAST Professional'",
            "sports_json": "TEXT NOT NULL DEFAULT '[]'",
            "max_seats": "INTEGER NOT NULL DEFAULT 1",
            "expires_at": "DATETIME",
            "logo_url": "VARCHAR(500)",
            "short_name": "VARCHAR(40)",
            "primary_colour": "VARCHAR(16) NOT NULL DEFAULT '#19D978'",
            "secondary_colour": "VARCHAR(16) NOT NULL DEFAULT '#151A1D'",
            "accent_colour": "VARCHAR(16) NOT NULL DEFAULT '#19D978'",
            "deployment_ring": "VARCHAR(30) NOT NULL DEFAULT 'production'",
        }
        with engine.begin() as connection:
            for name, definition in organisation_additions.items():
                if name not in organisation_columns:
                    connection.execute(text(f"ALTER TABLE organisations ADD COLUMN {name} {definition}"))
            connection.execute(text("UPDATE organisations SET subscription_tier='FAST Professional' WHERE subscription_tier IS NULL OR subscription_tier=''"))
            connection.execute(text("UPDATE organisations SET sports_json='[]' WHERE sports_json IS NULL OR sports_json=''"))
            connection.execute(text("UPDATE organisations SET max_seats=1 WHERE max_seats IS NULL OR max_seats < 1"))
            connection.execute(text("UPDATE organisations SET primary_colour='#19D978' WHERE primary_colour IS NULL OR primary_colour=''"))
            connection.execute(text("UPDATE organisations SET secondary_colour='#151A1D' WHERE secondary_colour IS NULL OR secondary_colour=''"))
            connection.execute(text("UPDATE organisations SET accent_colour='#19D978' WHERE accent_colour IS NULL OR accent_colour=''"))


    if "organisation_subscriptions" in table_names:
        subscription_columns = {column["name"] for column in inspector.get_columns("organisation_subscriptions")}
        subscription_additions = {
            "pending_downgrade_plan_id": "INTEGER",
            "pending_downgrade_user_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "pending_downgrade_device_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "pending_downgrade_effective_at": "DATETIME",
        }
        with engine.begin() as connection:
            for name, definition in subscription_additions.items():
                if name not in subscription_columns:
                    connection.execute(text(f"ALTER TABLE organisation_subscriptions ADD COLUMN {name} {definition}"))


    if "organisation_subscriptions" in table_names:
        subscription_columns = {column["name"] for column in inspector.get_columns("organisation_subscriptions")}
        subscription_additions = {
            "pending_downgrade_plan_id": "INTEGER",
            "pending_downgrade_user_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "pending_downgrade_device_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "pending_downgrade_effective_at": "DATETIME",
        }
        with engine.begin() as connection:
            for name, definition in subscription_additions.items():
                if name not in subscription_columns:
                    connection.execute(text(f"ALTER TABLE organisation_subscriptions ADD COLUMN {name} {definition}"))

    if "clubs" in table_names:
        club_columns = {column["name"] for column in inspector.get_columns("clubs")}
        if "organisation_id" not in club_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE clubs ADD COLUMN organisation_id INTEGER REFERENCES organisations(id)"))

    if "club_members" in table_names:
        # Club access roles are intentionally limited to Analyst and Coach.
        # Owner remains system-managed. Legacy Viewer/Member rows are mapped
        # to Coach, the least-privileged product-bearing club role.
        with engine.begin() as connection:
            connection.execute(text("UPDATE club_members SET role='coach' WHERE role IN ('viewer', 'member') OR role IS NULL OR role=''"))


    if "releases" in table_names:
        release_columns = {column["name"] for column in inspector.get_columns("releases")}
        release_additions = {
            "package_filename": "VARCHAR(255)",
            "package_sha256": "VARCHAR(64)",
            "package_size": "INTEGER",
            "updated_at": "DATETIME",
            "published_at": "DATETIME",
            "product_target": "VARCHAR(40) NOT NULL DEFAULT 'all'",
            "minimum_launcher_version": "VARCHAR(40)",
            "mandatory": "BOOLEAN NOT NULL DEFAULT 0",
            "mandatory_deadline": "DATETIME",
            "deployment_ring": "VARCHAR(30) NOT NULL DEFAULT 'development'",
            "rollout_percentage": "INTEGER NOT NULL DEFAULT 100",
            "rollout_status": "VARCHAR(20) NOT NULL DEFAULT 'active'",
            "rollout_notes": "TEXT",
        }
        with engine.begin() as connection:
            for name, definition in release_additions.items():
                if name not in release_columns:
                    connection.execute(text(f"ALTER TABLE releases ADD COLUMN {name} {definition}"))


    if "device_activations" in table_names:
        device_columns = {column["name"] for column in inspector.get_columns("device_activations")}
        device_additions = {
            "installed_version": "VARCHAR(40)",
            "update_channel": "VARCHAR(20)",
            "last_update_at": "DATETIME",
            "update_health": "VARCHAR(40)",
            "pending_update_version": "VARCHAR(40)",
            "last_telemetry_event": "VARCHAR(80)",
            "deployment_ring": "VARCHAR(30)",
            "installed_products_json": "TEXT NOT NULL DEFAULT '{}'",
            "product_health_json": "TEXT NOT NULL DEFAULT '{}'",
            "live_status_json": "TEXT NOT NULL DEFAULT '{}'",
        }
        with engine.begin() as connection:
            for name, definition in device_additions.items():
                if name not in device_columns:
                    connection.execute(text(f"ALTER TABLE device_activations ADD COLUMN {name} {definition}"))

    if "licences" not in table_names:
        return
    existing = {column["name"] for column in inspector.get_columns("licences")}
    additions = {
        "owner_type": "VARCHAR(20) NOT NULL DEFAULT 'individual'",
        "club_id": "INTEGER REFERENCES clubs(id)",
        "template_id": "INTEGER REFERENCES licence_templates(id)",
        "max_users": "INTEGER NOT NULL DEFAULT 1",
        "renewable": "BOOLEAN NOT NULL DEFAULT 1",
        "features_json": "TEXT NOT NULL DEFAULT '[]'",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE licences ADD COLUMN {name} {definition}"))
        connection.execute(text("UPDATE licences SET owner_type='individual' WHERE owner_type IS NULL OR owner_type=''"))
        connection.execute(text("UPDATE licences SET max_users=1 WHERE max_users IS NULL"))
        connection.execute(text("UPDATE licences SET renewable=TRUE WHERE renewable IS NULL"))
