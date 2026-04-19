"""Per-build PDF report.

The report is generated from committed DB rows only - never from
in-memory state - so that it always reflects what was actually persisted.
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from lpbf_serializer.db.schema import AuditEventRow, BuildRow, PartRow
from lpbf_serializer.domain.ids import BuildCode


class ReportError(Exception):
    pass


def generate_build_report(
    session: Session,
    build_code: BuildCode,
    *,
    output_path: Path,
    plate_width_mm: float,
    plate_depth_mm: float,
) -> Path:
    row = session.execute(
        select(BuildRow).where(BuildRow.build_code == str(build_code))
    ).scalar_one_or_none()
    if row is None:
        raise ReportError(f"No build row for {build_code}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        title=f"LPBF Build Report {build_code}",
        author="LPBF Serializer",
    )

    styles = getSampleStyleSheet()
    elements: list[Flowable] = []

    is_sidecar = row.source_build_file_path is not None

    elements.append(Paragraph(f"Build {row.build_code}", styles["Title"]))
    mode_line = "Mode: sidecar (external build file)" if is_sidecar else "Mode: drag-place"
    src_line = ""
    if is_sidecar:
        src_line = (
            f"Source: {row.source_build_file_format} "
            f"<font size='8'>{row.source_build_file_path}</font><br/>"
            f"Source SHA-256: <font size='8'>{row.source_build_file_sha256}</font><br/>"
        )
    elements.append(
        Paragraph(
            f"{mode_line}<br/>"
            f"Created: {row.created_at.isoformat(timespec='seconds')}<br/>"
            f"{src_line}"
            f"MTT: {row.mtt_path or '(not exported)'}<br/>"
            f"MTT SHA-256: {row.mtt_sha256 or '(n/a)'}<br/>"
            f"Parts: {len(row.parts)}",
            styles["Normal"],
        )
    )
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("Parts", styles["Heading2"]))
    if is_sidecar:
        table_data: list[list[str]] = [["#", "Serial", "Part name", "QA"]]
        for p in sorted(row.parts, key=lambda r: r.part_number):
            table_data.append(
                [
                    str(p.part_number),
                    p.serial_id,
                    p.part_name or "(unnamed)",
                    p.qa_status,
                ]
            )
    else:
        table_data = [
            ["#", "Serial", "X (mm)", "Y (mm)", "STL", "Mesh SHA-256 (prefix)", "QA"]
        ]
        for p in sorted(row.parts, key=lambda r: r.part_number):
            if (
                p.pos_x is None
                or p.pos_y is None
                or p.stl_path is None
                or p.mesh_sha256 is None
            ):
                raise ReportError(
                    f"Part {p.serial_id} is missing drag-place fields; "
                    "refusing to render drag-place row."
                )
            table_data.append(
                [
                    str(p.part_number),
                    p.serial_id,
                    f"{p.pos_x:.2f}",
                    f"{p.pos_y:.2f}",
                    Path(p.stl_path).name,
                    p.mesh_sha256[:12] + "...",
                    p.qa_status,
                ]
            )
    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1E24")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ]
        )
    )
    elements.append(table)
    elements.append(Spacer(1, 8 * mm))

    elements.append(Paragraph("Plate Layout", styles["Heading2"]))
    if is_sidecar:
        elements.append(
            Paragraph(
                "This is a sidecar-registered build. Part XY positions "
                "live inside the external build file and were not "
                "interpreted by this app, so no plate figure is rendered.",
                styles["Normal"],
            )
        )
    else:
        elements.append(
            Paragraph(
                f"Plate: {plate_width_mm:.0f} x {plate_depth_mm:.0f} mm. "
                f"Each marker is drawn at its recorded XY position.",
                styles["Normal"],
            )
        )
        elements.append(_PlateFigure(row.parts, plate_width_mm, plate_depth_mm))
    elements.append(Spacer(1, 8 * mm))

    events = session.execute(
        select(AuditEventRow)
        .where(AuditEventRow.build_code == str(build_code))
        .order_by(AuditEventRow.id)
    ).scalars().all()
    elements.append(Paragraph("Audit Trail", styles["Heading2"]))
    if not events:
        elements.append(Paragraph("(no audit events)", styles["Normal"]))
    else:
        audit_rows: list[list[str]] = [["When", "Actor", "Event", "Payload"]]
        for e in events:
            audit_rows.append(
                [
                    e.occurred_at.isoformat(timespec="seconds"),
                    e.actor,
                    e.event_type,
                    _trim(json.dumps(json.loads(e.payload_json), sort_keys=True), 80),
                ]
            )
        atable = Table(audit_rows, repeatRows=1, colWidths=[35 * mm, 20 * mm, 40 * mm, 80 * mm])
        atable.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1E24")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ]
            )
        )
        elements.append(atable)

    doc.build(elements)
    return output_path


def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "\u2026"


class _PlateFigure(Flowable):
    """Reportlab Flowable that draws the plate with part rectangles."""

    def __init__(
        self,
        parts: list[PartRow],
        plate_width_mm: float,
        plate_depth_mm: float,
    ) -> None:
        super().__init__()
        self._parts = parts
        self._w = plate_width_mm
        self._d = plate_depth_mm
        self._draw_w = 150 * mm
        self._draw_h = self._draw_w * (plate_depth_mm / plate_width_mm)

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:  # noqa: N803
        del availWidth, availHeight
        return self._draw_w, self._draw_h

    def draw(self) -> None:
        canvas: Canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#1E1E24"))
        canvas.rect(0, 0, self._draw_w, self._draw_h, fill=1, stroke=0)

        canvas.setFillColor(colors.HexColor("#3AA3FF"))
        canvas.setStrokeColor(colors.white)
        canvas.setFont("Helvetica", 6)

        sx = self._draw_w / self._w
        sy = self._draw_h / self._d
        marker_mm = 8.0
        marker_w = marker_mm * sx
        marker_h = marker_mm * sy

        for p in self._parts:
            if p.pos_x is None or p.pos_y is None:
                continue
            px = p.pos_x * sx
            py = p.pos_y * sy
            canvas.rect(px, py, marker_w, marker_h, fill=1, stroke=1)
            canvas.setFillColor(colors.white)
            canvas.drawString(px + 2, py + 2, str(p.part_number))
            canvas.setFillColor(colors.HexColor("#3AA3FF"))

        canvas.restoreState()
