"""Append-only audit event logger.

Audit rows are written through this class and *only* through this class.
The logger enforces two invariants:

1. ``occurred_at`` is always stamped by the logger, never by callers.
2. The ``payload_json`` column is valid JSON.

The underlying table has no UPDATE / DELETE surface in any repository in
this project. Schema-level revocation of update rights on the table is a
deployment concern handled separately.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from lpbf_serializer.db.schema import AuditEventRow
from lpbf_serializer.domain.ids import BuildCode


class AuditEventType(str, Enum):
    BUILD_OPENED = "build.opened"
    BUILD_CODE_ALLOCATED = "build.code_allocated"
    PART_PLACED = "build.part_placed"
    SERIALS_ASSIGNED = "build.serials_assigned"
    ENGRAVING_APPLIED = "build.engraving_applied"
    EXPORT_REQUESTED = "quantam.export_requested"
    EXPORT_SUCCEEDED = "quantam.export_succeeded"
    EXPORT_FAILED = "quantam.export_failed"
    BUILD_PERSISTED = "build.persisted"


class AuditLogger:
    def __init__(self, session: Session, *, actor: str) -> None:
        if len(actor.strip()) == 0:
            raise ValueError("AuditLogger requires a non-empty actor")
        self._session = session
        self._actor = actor

    def log(
        self,
        event_type: AuditEventType,
        *,
        build_code: BuildCode | None,
        payload: dict[str, Any],
    ) -> None:
        row = AuditEventRow(
            occurred_at=datetime.now(UTC),
            actor=self._actor,
            event_type=event_type.value,
            build_code=str(build_code) if build_code is not None else None,
            payload_json=json.dumps(payload, default=str, sort_keys=True),
        )
        self._session.add(row)
