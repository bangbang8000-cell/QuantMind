"""Admin audit logging helper.

Thin wrapper over EnhancedAuditService for admin write operations.
Callers provide the user dict from Depends(require_admin) and a db session.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def log_admin_action(
    *,
    current_user: dict[str, Any],
    action: str,
    resource: str,
    resource_id: str | None = None,
    description: str | None = None,
    db_session: Any,
) -> None:
    """Log an admin action to the audit log.

    Uses EnhancedAuditService which writes to user_audit_logs table.
    Silently degrades on error — audit logging must never block the main flow.
    """
    try:
        from backend.services.api.user_app.services.enhanced_audit_service import (
            EnhancedAuditService,
        )

        audit = EnhancedAuditService(db_session)
        await audit.log_operation(
            user_id=current_user.get("user_id", "unknown"),
            tenant_id=current_user.get("tenant_id", "default"),
            action=action,
            resource=resource,
            resource_id=resource_id,
            description=description,
            success=True,
        )
    except Exception:
        logger.exception("Failed to write admin audit log (action=%s resource=%s)", action, resource)
