from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path
import importlib.util
import os
import re
from typing import Any
from uuid import uuid4

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PDF_FONT_NAME = "JusticeKPUnicode"
PDF_FONT_BOLD_NAME = "JusticeKPUnicodeBold"
DOCUMENT_SCOPE = "latest_final_reviewer_approved_transcript"
CONFIDENTIALITY_NOTICE = (
    "CONFIDENTIAL — Official barangay case record. Access, use, reproduction, and disclosure "
    "are limited to authorized personnel and lawful purposes."
)
DECISION_SUPPORT_DISCLAIMER = (
    "Decision-support disclaimer: JUSTICE-KP supports documentation and review. It does not "
    "replace the authority, independent judgment, or legal duties of barangay officials, the "
    "Lupon Tagapamayapa, courts, or other competent authorities."
)


@dataclass(frozen=True)
class TranscriptPdfArtifact:
    content: bytes
    sha256: str
    page_count: int
    generated_at: datetime
    document_id: str
    filename: str
    scope: str = DOCUMENT_SCOPE


def _font_candidates() -> list[tuple[Path, Path]]:
    configured = os.getenv("JUSTICE_KP_PDF_FONT", "").strip()
    configured_bold = os.getenv("JUSTICE_KP_PDF_FONT_BOLD", "").strip()
    package_fonts = Path(reportlab.__file__).resolve().parent / "fonts"
    candidates: list[tuple[Path, Path]] = []
    if configured:
        regular = Path(configured).expanduser()
        candidates.append((regular, Path(configured_bold).expanduser() if configured_bold else regular))
    matplotlib_spec = importlib.util.find_spec("matplotlib")
    matplotlib_root = (
        Path(next(iter(matplotlib_spec.submodule_search_locations)))
        if matplotlib_spec and matplotlib_spec.submodule_search_locations
        else None
    )
    candidates.append(
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        )
    )
    if matplotlib_root:
        candidates.append(
            (
                matplotlib_root / "mpl-data/fonts/ttf/DejaVuSans.ttf",
                matplotlib_root / "mpl-data/fonts/ttf/DejaVuSans-Bold.ttf",
            )
        )
    candidates.extend(
        [
            (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
            (package_fonts / "Vera.ttf", package_fonts / "VeraBd.ttf"),
        ]
    )
    return candidates


def ensure_unicode_fonts() -> tuple[str, str]:
    if PDF_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return PDF_FONT_NAME, PDF_FONT_BOLD_NAME
    for regular, bold in _font_candidates():
        if regular.is_file() and bold.is_file():
            pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, str(regular)))
            pdfmetrics.registerFont(TTFont(PDF_FONT_BOLD_NAME, str(bold)))
            return PDF_FONT_NAME, PDF_FONT_BOLD_NAME
    raise RuntimeError(
        "No Unicode TrueType font is available for transcript PDF generation. "
        "Set JUSTICE_KP_PDF_FONT and JUSTICE_KP_PDF_FONT_BOLD."
    )


def _display_datetime(value: Any) -> str:
    if value is None or value == "":
        return "Not recorded"
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _timestamp(value: Any) -> str:
    try:
        seconds = max(0.0, float(value))
    except (TypeError, ValueError):
        return ""
    minutes, second = divmod(int(seconds), 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def _segment_timestamp(segment: dict[str, Any]) -> str:
    start = segment.get("start")
    end = segment.get("end")
    try:
        has_timing = float(start or 0) > 0 or float(end or 0) > 0
    except (TypeError, ValueError):
        has_timing = False
    if not has_timing:
        return ""
    start_text = _timestamp(start)
    end_text = _timestamp(end)
    return f"[{start_text}–{end_text}]" if end_text else f"[{start_text}]"


def _safe_filename(case_id: str) -> str:
    safe_case_id = re.sub(r"[^A-Za-z0-9_-]+", "-", case_id).strip("-") or "case"
    return f"{safe_case_id}-complete-transcript.pdf"


class CompletedTranscriptPdfService:
    def build(
        self,
        summary: dict[str, Any],
        *,
        generated_by: str,
        generated_by_username: str,
        generated_at: datetime | None = None,
        document_id: str | None = None,
    ) -> TranscriptPdfArtifact:
        transcript = summary.get("transcript")
        if not transcript or transcript.get("redacted"):
            raise ValueError("An authorized final transcript is required to generate this PDF.")

        regular_font, bold_font = ensure_unicode_fonts()
        generated = generated_at or datetime.now(timezone.utc)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        generated = generated.astimezone(timezone.utc)
        artifact_id = document_id or uuid4().hex
        workflow = summary["workflow"]
        final_outcome = summary["final_outcome"]
        case_id = str(workflow.get("case_id") or "")

        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=27 * mm,
            bottomMargin=25 * mm,
            title=f"JUSTICE-KP Complete Transcript — {case_id}",
            author=generated_by,
            subject="Latest final reviewer-approved transcript",
            creator="JUSTICE-KP",
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "TranscriptTitle",
            parent=styles["Title"],
            fontName=bold_font,
            fontSize=19,
            leading=23,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=3 * mm,
        )
        subtitle_style = ParagraphStyle(
            "TranscriptSubtitle",
            parent=styles["Normal"],
            fontName=regular_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#475569"),
            spaceAfter=5 * mm,
        )
        section_style = ParagraphStyle(
            "TranscriptSection",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#1d4ed8"),
            spaceBefore=4 * mm,
            spaceAfter=2.5 * mm,
        )
        body_style = ParagraphStyle(
            "TranscriptBody",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=9.5,
            leading=14,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#111827"),
            splitLongWords=True,
            spaceAfter=2.5 * mm,
        )
        segment_style = ParagraphStyle(
            "TranscriptSegment",
            parent=body_style,
            borderColor=colors.HexColor("#cbd5e1"),
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#f8fafc"),
            spaceAfter=3 * mm,
        )
        small_style = ParagraphStyle(
            "TranscriptSmall",
            parent=body_style,
            fontSize=8.3,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )

        story: list[Any] = [
            Paragraph("JUSTICE-KP", title_style),
            Paragraph("Printable Complete Transcript", subtitle_style),
        ]

        metadata_rows = [
            ("Case ID", case_id),
            ("Final outcome", final_outcome.get("outcome") or "Not recorded"),
            ("Finalized date", _display_datetime(final_outcome.get("finalized_at"))),
            ("Transcript ID", str(transcript.get("id") or "Not recorded")),
            ("Transcript type", transcript.get("recording_type_label") or transcript.get("recording_type") or "Not recorded"),
            ("Document scope", "Latest final reviewer-approved transcript"),
            ("Generated", _display_datetime(generated)),
            ("Generated by", f"{generated_by} ({generated_by_username})"),
            ("Document ID", artifact_id),
        ]
        table_data = [
            [
                Paragraph(f"<b>{escape(str(label))}</b>", body_style),
                Paragraph(escape(str(value)), body_style),
            ]
            for label, value in metadata_rows
        ]
        metadata_table = Table(table_data, colWidths=[43 * mm, 122 * mm], repeatRows=0, hAlign="LEFT")
        metadata_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eff6ff")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.extend(
            [
                metadata_table,
                Spacer(1, 3 * mm),
                Paragraph(escape(CONFIDENTIALITY_NOTICE), small_style),
                Paragraph("Complete transcript", section_style),
            ]
        )

        segments = [item for item in (transcript.get("segments") or []) if isinstance(item, dict)]
        if segments:
            for segment in segments:
                speaker = escape(str(segment.get("speaker") or "Speaker"))
                timing = _segment_timestamp(segment)
                text = escape(str(segment.get("text") or "")).replace("\n", "<br/>")
                heading = f"<b>{speaker}</b>"
                if timing:
                    heading += f" <font color='#64748b'>{escape(timing)}</font>"
                story.append(Paragraph(f"{heading}<br/>{text or ' '}", segment_style))
        else:
            content = str(transcript.get("content") or "")
            if not content:
                story.append(Paragraph("No transcript text was saved.", body_style))
            else:
                # Every source line is emitted. Paragraph handles wrapping and splitting
                # across A4 pages without imposing a length or page limit.
                for line in content.splitlines() or [content]:
                    story.append(Paragraph(escape(line) or "&nbsp;", body_style))

        story.extend(
            [
                Spacer(1, 3 * mm),
                Paragraph("Document notice", section_style),
                Paragraph(escape(DECISION_SUPPORT_DISCLAIMER), body_style),
                Paragraph(
                    "Integrity metadata: the SHA-256 hash of the delivered PDF is recorded in the "
                    "server audit event and returned in the X-Document-SHA256 response header.",
                    small_style,
                ),
            ]
        )

        page_count = 0

        def page_decorations(canvas: Any, doc: Any) -> None:
            nonlocal page_count
            page_count = max(page_count, doc.page)
            canvas.saveState()
            canvas.setTitle(f"JUSTICE-KP Complete Transcript — {case_id}")
            canvas.setAuthor(generated_by)
            canvas.setSubject("Latest final reviewer-approved transcript")
            canvas.setCreator("JUSTICE-KP")
            canvas.setFont(regular_font, 7.5)
            canvas.setFillColor(colors.HexColor("#475569"))
            canvas.drawString(20 * mm, A4[1] - 15 * mm, f"JUSTICE-KP • Case {case_id}")
            canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 15 * mm, "CONFIDENTIAL")
            canvas.setStrokeColor(colors.HexColor("#cbd5e1"))
            canvas.setLineWidth(0.4)
            canvas.line(20 * mm, A4[1] - 18 * mm, A4[0] - 20 * mm, A4[1] - 18 * mm)
            canvas.line(20 * mm, 18 * mm, A4[0] - 20 * mm, 18 * mm)
            canvas.setFont(regular_font, 7)
            canvas.drawString(20 * mm, 12 * mm, "Confidential official case record")
            canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {doc.page}")
            canvas.restoreState()

        document.build(story, onFirstPage=page_decorations, onLaterPages=page_decorations)
        content = buffer.getvalue()
        return TranscriptPdfArtifact(
            content=content,
            sha256=sha256(content).hexdigest(),
            page_count=page_count,
            generated_at=generated,
            document_id=artifact_id,
            filename=_safe_filename(case_id),
        )
