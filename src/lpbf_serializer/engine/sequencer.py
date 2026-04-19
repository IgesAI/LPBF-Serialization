"""Transactional build-code sequencer.

Usage::

    with Session(engine) as s, s.begin():
        seq = BuildSequencer(s, prefix="B#", digits=4)
        code = seq.allocate_next()
        # ... insert build row that references ``code`` ...

The sequencer mutates the single ``build_counter`` row inside the caller's
transaction. If the caller rolls back, the counter rolls back with it; if
the caller commits, the counter advances atomically with the build
insertion. There is no retry loop: a concurrent writer that collides will
raise ``DuplicateBuildCodeError`` downstream, which is surfaced to the user.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from lpbf_serializer.db.schema import BuildCounterRow
from lpbf_serializer.domain.ids import BuildCode


class BuildSequencerNotInitialized(RuntimeError):
    """Raised when the ``build_counter`` row is missing."""


class BuildSequencer:
    def __init__(self, session: Session, *, prefix: str, digits: int) -> None:
        self._session = session
        self._prefix = prefix
        self._digits = digits

    def peek(self) -> BuildCode:
        row = self._row()
        return BuildCode(prefix=self._prefix, number=row.next_value, digits=self._digits)

    def allocate_next(self) -> BuildCode:
        row = self._row()
        code = BuildCode(
            prefix=self._prefix, number=row.next_value, digits=self._digits
        )
        row.next_value = row.next_value + 1
        self._session.flush()
        return code

    def _row(self) -> BuildCounterRow:
        row = self._session.execute(
            select(BuildCounterRow).where(BuildCounterRow.id == 1).with_for_update()
            if self._session.bind is not None
            and self._session.bind.dialect.name != "sqlite"
            else select(BuildCounterRow).where(BuildCounterRow.id == 1)
        ).scalar_one_or_none()
        if row is None:
            raise BuildSequencerNotInitialized(
                "build_counter row (id=1) is missing; migrations did not run"
            )
        return row
