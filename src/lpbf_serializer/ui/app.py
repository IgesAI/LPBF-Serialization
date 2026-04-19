"""Qt application bootstrapper."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication, QMessageBox

from lpbf_serializer.config import load_settings
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.quantam.client import QuantAMClient
from lpbf_serializer.quantam.uia_client import UiaQuantAMClient
from lpbf_serializer.ui.main_window import MainWindow


def run(argv: Sequence[str]) -> int:
    settings = load_settings()
    settings.ensure_dirs()

    run_migrations(settings.effective_database_url)
    engine, session_factory = create_engine_and_session(settings.effective_database_url)

    app = QApplication(list(argv))
    app.setApplicationName("LPBF Serializer")
    app.setOrganizationName("LPBFSerializer")

    quantam_client: QuantAMClient = UiaQuantAMClient(
        exe_path=settings.quantam_exe,
        expected_version=settings.quantam_expected_version,
    )

    try:
        window = MainWindow(
            settings=settings,
            session_factory=session_factory,
            quantam_client=quantam_client,
        )
    except Exception as e:
        QMessageBox.critical(None, "Startup failed", f"{type(e).__name__}: {e}")
        engine.dispose()
        return 2

    window.show()
    exit_code = app.exec()
    engine.dispose()
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv))
