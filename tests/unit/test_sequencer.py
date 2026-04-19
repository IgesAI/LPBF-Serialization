"""Tests for the build-code sequencer against a real SQLite DB."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.engine.sequencer import BuildSequencer


@pytest.fixture
def session(tmp_path: Path) -> Session:
    db = tmp_path / "t.sqlite3"
    url = f"sqlite:///{db.as_posix()}"
    run_migrations(url)
    _, factory = create_engine_and_session(url)
    return factory()


def test_peek_does_not_advance(session: Session) -> None:
    with session.begin():
        seq = BuildSequencer(session, prefix="B#", digits=4)
        assert str(seq.peek()) == "B#0001"
        assert str(seq.peek()) == "B#0001"


def test_allocate_advances(session: Session) -> None:
    with session.begin():
        seq = BuildSequencer(session, prefix="B#", digits=4)
        a = seq.allocate_next()
        b = seq.allocate_next()
    assert str(a) == "B#0001"
    assert str(b) == "B#0002"


def test_rollback_restores_counter(session: Session) -> None:
    seq = BuildSequencer(session, prefix="B#", digits=4)
    try:
        with session.begin():
            seq.allocate_next()
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with session.begin():
        assert str(seq.peek()) == "B#0001"
