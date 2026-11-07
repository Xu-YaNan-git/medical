"""Central env / profile settings for persistence and privacy."""

from __future__ import annotations

import os


def app_env() -> str:
    """Return 'dev' or 'prod'. Reads APP_ENV or PROFILE; default 'dev'."""
    raw = (os.environ.get("APP_ENV") or os.environ.get("PROFILE") or "dev").strip().lower()
    if raw in ("prod", "production"):
        return "prod"
    return "dev"


def is_prod() -> bool:
    return app_env() == "prod"


def store_backend() -> str:
    return (os.environ.get("STORE_BACKEND") or "sqlite").strip().lower()


def sqlite_path(default: str) -> str:
    return (os.environ.get("SQLITE_PATH") or default).strip()


def reset_store_allowed() -> bool:
    """Whether RESET_STORE should wipe the DB on boot.

    In prod, RESET_STORE is ignored unless ALLOW_RESET_IN_PROD=1.
    """
    flag = (os.environ.get("RESET_STORE") or "").strip().lower()
    if flag not in ("1", "true", "yes"):
        return False
    if is_prod():
        allow = (os.environ.get("ALLOW_RESET_IN_PROD") or "").strip().lower()
        return allow in ("1", "true", "yes")
    return True


def allow_demo_reset() -> bool:
    """Runtime POST /api/demo/reset gate.

    Allowed in non-prod. In prod, only when ALLOW_RESET_IN_PROD=1.
    Independent of boot-time RESET_STORE.
    """
    if not is_prod():
        return True
    allow = (os.environ.get("ALLOW_RESET_IN_PROD") or "").strip().lower()
    return allow in ("1", "true", "yes")


def mask_sensitive_default_on() -> bool:
    raw = os.environ.get("MASK_SENSITIVE")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def allow_full_sensitive() -> bool:
    """Dangerous: only honored outside prod."""
    if is_prod():
        return False
    return (os.environ.get("ALLOW_FULL_SENSITIVE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def should_mask_sensitive() -> bool:
    """Force-mask identity phones/ids in API responses unless explicitly disabled (non-prod)."""
    if allow_full_sensitive():
        return False
    return mask_sensitive_default_on()
