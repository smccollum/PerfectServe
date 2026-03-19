import calendar
from pathlib import Path

from PySide6.QtGui import (
    QImage,
    QPainter,
    QFont,
    QPen,
    QPdfWriter,
    QPageLayout,
    QPageSize,
    QTextDocument,
)
from PySide6.QtCore import Qt, QRectF, QMarginsF

PDF_DPI = 200
PAGE_W_IN = 11.0
PAGE_H_IN = 8.5
IMG_W = int(PAGE_W_IN * PDF_DPI)   # 2200
IMG_H = int(PAGE_H_IN * PDF_DPI)   # 1700


def render_calendar_to_image(
    calendar_data: dict,
    logo_path: str | None = None
) -> QImage:
    image = QImage(IMG_W, IMG_H, QImage.Format_RGB32)
    image.fill(Qt.white)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)

    _render_calendar(painter, IMG_W, IMG_H, calendar_data, logo_path)

    painter.end()
    return image


def export_calendar_to_pdf(image: QImage, output_path: Path) -> None:
    writer = QPdfWriter(str(output_path))
    writer.setResolution(PDF_DPI)

    page_layout = QPageLayout(
        QPageSize(QPageSize.Letter),
        QPageLayout.Landscape,
        QMarginsF(0, 0, 0, 0),
    )
    writer.setPageLayout(page_layout)

    painter = QPainter(writer)
    page_rect = writer.pageLayout().paintRectPixels(PDF_DPI)
    painter.drawImage(page_rect, image)
    painter.end()


def _render_calendar(
    p: QPainter,
    w: int,
    h: int,
    calendar_data: dict,
    logo_path: str | None,
) -> None:
    margin = int(h * 0.020)
    usable_w = w - 2 * margin

    days_data = calendar_data.get("days") or []
    rows_to_draw = []
    for row in range(6):
        row_has_days = any(
            (days_data[row * 7 + col] if row * 7 + col < len(days_data) else None)
            for col in range(7)
        )
        if row_has_days:
            rows_to_draw.append(row)

    if not rows_to_draw:
        rows_to_draw = list(range(6))

    title_font = QFont("Helvetica", int(h * 0.028), QFont.Bold)
    header_font = QFont("Helvetica", int(h * 0.016), QFont.Bold)
    day_num_font = QFont("Helvetica", int(h * 0.016), QFont.Bold)
    text_font = QFont("Helvetica", int(h * 0.012))
    notes_font = QFont("Helvetica", int(h * 0.012))

    title_h = int(h * 0.060)
    header_h = int(h * 0.040)
    notes_h = int(h * 0.12)

    grid_top = margin + title_h + header_h
    grid_h = (h - margin) - grid_top - notes_h
    grid_bottom = grid_top + grid_h

    cell_w = usable_w / 7
    cell_h = grid_h / len(rows_to_draw)

    pad = int(h * 0.008)
    line_h = int(h * 0.022)
    day_num_h = int(h * 0.022)

    p.setPen(QPen(Qt.black, 1))

    logo = QImage()
    if logo_path:
        try:
            logo = QImage(str(logo_path))
        except Exception:
            logo = QImage()

    logo_h = int(title_h * 0.85)

    if not logo.isNull():
        scaled = logo.scaledToHeight(logo_h, Qt.SmoothTransformation)
        p.drawImage(
            QRectF(
                margin,
                margin + (title_h - logo_h) / 2,
                scaled.width(),
                logo_h
            ),
            scaled
        )
    else:
        placeholder = "Nephrology Associates"

        placeholder_font = QFont(
            "Helvetica",
            max(8, int(h * 0.028 * 0.75)),
            QFont.Bold
        )
        p.setFont(placeholder_font)

        p.drawText(
            QRectF(
                margin,
                margin,
                usable_w * 0.40,
                title_h
            ),
            Qt.AlignLeft | Qt.AlignVCenter,
            placeholder
        )

    month = int(calendar_data.get("month", 0))
    year = calendar_data.get("year", "")
    team = calendar_data.get("team", "")
    month_name = calendar.month_name[month] if 1 <= month <= 12 else ""
    center_title = f"{month_name} {year} – {team}"

    center_font = QFont("Helvetica", max(8, int(h * 0.028 * 0.85)), QFont.Bold)
    p.setFont(center_font)
    p.drawText(
        QRectF(margin, margin, usable_w, title_h),
        Qt.AlignCenter,
        center_title
    )

    facility = (calendar_data.get("facility") or "").strip()
    if facility:
        facility_font = QFont("Helvetica", int(h * 0.016), QFont.Bold)
        p.setFont(facility_font)
        p.drawText(
            QRectF(margin, margin, usable_w, title_h),
            Qt.AlignRight | Qt.AlignVCenter,
            facility
        )

    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    p.setFont(header_font)
    for i, d in enumerate(days):
        p.drawText(
            QRectF(margin + i * cell_w, margin + title_h, cell_w, header_h),
            Qt.AlignCenter,
            d
        )

    p.setPen(QPen(Qt.black, 1))

    visible_shift_rows = int(calendar_data.get("visible_shift_rows", 0))

    for draw_row_index, actual_row in enumerate(rows_to_draw):
        for col in range(7):
            idx = actual_row * 7 + col
            cell = days_data[idx] if idx < len(days_data) else None

            x = margin + col * cell_w
            y = grid_top + draw_row_index * cell_h

            p.drawRect(QRectF(x, y, cell_w, cell_h))

            if not cell:
                continue

            day_text = str(cell.get("day", "")).strip()
            if not day_text:
                continue

            p.setFont(day_num_font)
            p.drawText(
                QRectF(x + pad, y + pad, cell_w - 2 * pad, day_num_h),
                Qt.AlignLeft | Qt.AlignTop,
                day_text
            )

            p.setFont(text_font)
            text_y = y + pad + day_num_h + int(h * 0.005)

            shown = 0
            for shift in cell.get("shifts", []):
                if shown >= visible_shift_rows:
                    break

                shift_type = shift.get("shift_type", "")
                time_text = (shift.get("time_text") or "")
                doctor = (shift.get("doctor") or "")

                if shift_type == "exception":
                    time_trim = time_text.strip()
                    if not _has_user_content(time_trim, doctor):
                        continue

                    if time_trim.lower() == "(exception)":
                        line = doctor if doctor else ""
                    else:
                        if doctor:
                            line = f"{time_trim} {doctor}".strip()
                        else:
                            line = time_trim

                    if not line:
                        continue
                else:
                    if not doctor:
                        continue
                    line = f"{time_text} {doctor}".strip()

                p.drawText(
                    QRectF(x + pad, text_y, cell_w - 2 * pad, line_h),
                    Qt.AlignLeft | Qt.AlignTop,
                    line
                )
                text_y += line_h
                shown += 1

    notes_y = grid_bottom + int(h * 0.015)

    left_text = _html_to_plain_text(calendar_data.get("notes_left_html")).strip()
    right_text = _html_to_plain_text(calendar_data.get("notes_right_html")).strip()

    if left_text or right_text:
        p.setFont(notes_font)

        divider_w = int(w * 0.002)
        col_gap = int(w * 0.010)

        total_w = usable_w
        col_w = (total_w - divider_w - col_gap * 2) / 2

        left_x = margin
        divider_x = left_x + col_w + col_gap
        right_x = divider_x + divider_w + col_gap

        if left_text:
            p.drawText(
                QRectF(left_x, notes_y, col_w, notes_h),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                left_text
            )

        p.setPen(QPen(Qt.lightGray, divider_w))
        p.drawLine(
            divider_x,
            notes_y,
            divider_x,
            notes_y + notes_h
        )

        p.setPen(QPen(Qt.black, 1))

        if right_text:
            p.drawText(
                QRectF(right_x, notes_y, col_w, notes_h),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                right_text
            )


def _has_user_content(time_text: str, doctor: str) -> bool:
    if doctor:
        return True
    t = (time_text or "").strip()
    if not t:
        return False
    if t.lower() == "(exception)":
        return False
    return True


def _html_to_plain_text(value: str | None) -> str:
    doc = QTextDocument()
    doc.setHtml(value or "")
    return doc.toPlainText()
