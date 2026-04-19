"""Physical plate-token artifact generator.

For a registered build (drag-place or sidecar), produces a single-page
PDF intended to be printed and physically attached to the build plate
before the build starts. The operator can scan the QR to look the build
up in the DB and see the authoritative per-part serial table.

QR payload format (URI-style, no fabrication):

    lpbf-serializer://build/<BUILD_CODE>?sha256=<BUILD_FILE_SHA256>

If no source build file exists (drag-place mode), the ``sha256`` query
parameter is omitted. The scanner decides how to resolve the URI.
"""

from __future__ import annotations

import io
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from lpbf_serializer.db.schema import BuildRow
from lpbf_serializer.domain.ids import BuildCode


class PlateTokenError(Exception):
    pass


def _qr_payload(row: BuildRow) -> str:
    base = f"lpbf-serializer://build/{row.build_code}"
    if row.source_build_file_sha256:
        return f"{base}?sha256={row.source_build_file_sha256}"
    if row.mtt_sha256:
        return f"{base}?sha256={row.mtt_sha256}"
    return base


def _qr_image_bytes(payload: str, *, box_size: int = 10) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_plate_token(
    session: Session,
    build_code: BuildCode,
    *,
    output_path: Path,
) -> Path:
    row = session.execute(
        select(BuildRow).where(BuildRow.build_code == str(build_code))
    ).scalar_one_or_none()
    if row is None:
        raise PlateTokenError(f"No build row for {build_code}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        title=f"LPBF Plate Token {build_code}",
        author="LPBF Serializer",
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    story: list[Flowable] = []

    story.append(Paragraph(f"BUILD TOKEN: <b>{row.build_code}</b>", styles["Title"]))
    story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            f"Created: {row.created_at.isoformat(timespec='seconds')}  |  "
            f"Parts: {len(row.parts)}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    qr_png = _qr_image_bytes(_qr_payload(row))
    qr_img = Image(io.BytesIO(qr_png), width=55 * mm, height=55 * mm)

    if row.source_build_file_path:
        prov_text = (
            f"<b>Source build file</b><br/>"
            f"{row.source_build_file_format}: "
            f"<font size='8'>{Path(row.source_build_file_path).name}</font><br/>"
            f"SHA-256: <font size='7'>{row.source_build_file_sha256}</font>"
        )
    elif row.mtt_path:
        prov_text = (
            f"<b>Generated MTT</b><br/>"
            f"<font size='8'>{Path(row.mtt_path).name}</font><br/>"
            f"SHA-256: <font size='7'>{row.mtt_sha256}</font>"
        )
    else:
        prov_text = "<b>No source build file linked.</b>"

    header_table = Table(
        [[qr_img, Paragraph(prov_text, styles["Normal"])]],
        colWidths=[60 * mm, 110 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("<b>Parts on this plate</b>", styles["Heading3"]))
    table_data: list[list[str]] = [["#", "Serial", "Part name (from header)"]]
    for p in sorted(row.parts, key=lambda r: r.part_number):
        table_data.append(
            [
                str(p.part_number),
                p.serial_id,
                p.part_name or "(drag-place)",
            ]
        )
    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[10 * mm, 40 * mm, 120 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E1E24")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    story.append(
        Paragraph(
            "<font size='8'>This token is generated from persisted database "
            "rows. The QR code encodes the build code and the SHA-256 of the "
            "source build file (if registered). Scanning it identifies the "
            "build in the LPBF Serializer database.</font>",
            styles["Normal"],
        )
    )

    doc.build(story)
    return output_path
