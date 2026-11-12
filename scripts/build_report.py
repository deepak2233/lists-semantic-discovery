"""Render the repository's reviewed design documents into a standalone PDF report."""

import argparse
import html
import re
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
GREEN = colors.HexColor("#164638")
INK = colors.HexColor("#243f36")
ORANGE = colors.HexColor("#d86b39")
PALE = colors.HexColor("#eff4ed")
GRAY = colors.HexColor("#617367")
WIDTH, HEIGHT = A4
CONTENT_WIDTH = WIDTH - 84


def register_fonts():
    root = Path("/usr/share/fonts/truetype/dejavu")
    if (root / "DejaVuSans.ttf").exists():
        pdfmetrics.registerFont(TTFont("Body", str(root / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("Body-Bold", str(root / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Mono", str(root / "DejaVuSansMono.ttf")))
        pdfmetrics.registerFontFamily(
            "Body", normal="Body", bold="Body-Bold", italic="Body", boldItalic="Body-Bold"
        )
        return "Body", "Body-Bold", "Mono"
    return "Helvetica", "Helvetica-Bold", "Courier"


BODY, BOLD, MONO = register_fonts()
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        "ReportBody",
        fontName=BODY,
        fontSize=9.1,
        leading=13.3,
        textColor=INK,
        spaceAfter=6,
        allowWidows=0,
        allowOrphans=0,
    )
)
styles.add(
    ParagraphStyle(
        "Chapter",
        fontName=BOLD,
        fontSize=23,
        leading=29,
        textColor=GREEN,
        spaceAfter=17,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "Section",
        fontName=BOLD,
        fontSize=13,
        leading=18,
        textColor=GREEN,
        spaceBefore=14,
        spaceAfter=7,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "Subsection",
        fontName=BOLD,
        fontSize=10.5,
        leading=15,
        textColor=GREEN,
        spaceBefore=10,
        spaceAfter=5,
        keepWithNext=True,
    )
)
styles.add(
    ParagraphStyle(
        "TableText",
        fontName=BODY,
        fontSize=7.3,
        leading=10.6,
        textColor=INK,
        spaceAfter=0,
        splitLongWords=True,
    )
)
styles.add(
    ParagraphStyle("TableHead", parent=styles["TableText"], fontName=BOLD, textColor=colors.white)
)
styles.add(
    ParagraphStyle("Small", fontName=BODY, fontSize=8.2, leading=12, textColor=GRAY, spaceAfter=6)
)
styles.add(
    ParagraphStyle(
        "ReportCode",
        fontName=MONO,
        fontSize=7.1,
        leading=10,
        textColor=INK,
        backColor=PALE,
        borderPadding=8,
        spaceBefore=4,
        spaceAfter=10,
    )
)
styles.add(
    ParagraphStyle("Cover", fontName=BOLD, fontSize=50, leading=54, textColor=GREEN, spaceAfter=25)
)
styles.add(
    ParagraphStyle(
        "CoverTitle", fontName=BODY, fontSize=27, leading=34, textColor=GREEN, spaceAfter=18
    )
)
styles.add(
    ParagraphStyle(
        "Eyebrow", fontName=BOLD, fontSize=9, leading=13, textColor=ORANGE, spaceAfter=20
    )
)


def rich(text):
    text = text.replace("\u2014", " - ").replace("\u2013", "-").replace("\u2011", "-")
    text = html.escape(text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<link href="{m[2]}" color="#27654f">{m[1]}</link>',
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", rf'<font name="{MONO}" size="8">\1</font>', text)
    return text


class Architecture(Flowable):
    def __init__(self, production=False):
        super().__init__()
        self.width = CONTENT_WIDTH
        self.height = 352
        self.production = production

    def draw(self):
        c = self.canv
        c.setStrokeColor(colors.HexColor("#c8d8cc"))
        c.setFillColor(PALE)
        c.roundRect(0, 8, 214, 332, 8, stroke=1, fill=1)
        c.setFillColor(colors.HexColor("#f8faf7"))
        c.roundRect(234, 8, 277, 332, 8, stroke=1, fill=1)
        c.setFont(BOLD, 8)
        c.setFillColor(GRAY)
        c.drawString(12, 323, "BROWSER / USER DEVICE")
        c.drawString(246, 323, "BACKEND / TRUSTED SERVICES")

        def box(x, y, w, h, title, detail):
            c.setStrokeColor(colors.HexColor("#bfd0c2"))
            c.setFillColor(colors.white)
            c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
            c.setFillColor(GREEN)
            c.setFont(BOLD, 9)
            c.drawString(x + 10, y + h - 17, title)
            c.setFillColor(GRAY)
            c.setFont(BODY, 7.1)
            c.drawString(x + 10, y + 12, detail)

        def arrow(points):
            c.setStrokeColor(GREEN)
            c.setLineWidth(1.1)
            path = c.beginPath()
            path.moveTo(*points[0])
            for point in points[1:]:
                path.lineTo(*point)
            c.drawPath(path)
            x, y = points[-1]
            px, py = points[-2]
            c.setFillColor(GREEN)
            path = c.beginPath()
            if x > px:
                path.moveTo(x, y)
                path.lineTo(x - 5, y + 3)
                path.lineTo(x - 5, y - 3)
            elif x < px:
                path.moveTo(x, y)
                path.lineTo(x + 5, y + 3)
                path.lineTo(x + 5, y - 3)
            elif y < py:
                path.moveTo(x, y)
                path.lineTo(x - 3, y + 5)
                path.lineTo(x + 3, y + 5)
            else:
                path.moveTo(x, y)
                path.lineTo(x - 3, y - 5)
                path.lineTo(x + 3, y - 5)
            path.close()
            c.drawPath(path, fill=1, stroke=0)

        if not self.production:
            labels = [
                (12, 260, 190, 44, "Public article", "Temporary activeTab access"),
                (12, 196, 190, 44, "Local extraction", "Bounded excerpt and topic words"),
                (12, 126, 190, 50, "User reviews and sends", "No network request before consent"),
                (246, 260, 253, 44, "API boundary", "Identity, validation and admission"),
                (246, 196, 253, 44, "Candidate provider", "Brave Search or labeled demo fixtures"),
                (246, 126, 253, 50, "Rank and fuse", "BM25 + optional local MiniLM + RRF"),
                (
                    246,
                    54,
                    253,
                    50,
                    "Deduplicate and diversify",
                    "Up to ten pages; two per exact host",
                ),
                (12, 54, 190, 50, "Related-page list", "Safe links and plain text explanations"),
            ]
        else:
            labels = [
                (12, 260, 190, 44, "Packaged extension", "Managed public-client sign-in"),
                (12, 196, 190, 44, "Browser sign-in", "PKCE with a trusted identity provider"),
                (12, 126, 190, 50, "User-reviewed request", "Short-lived user access token"),
                (246, 260, 253, 44, "TLS gateway", "Global quotas and request deadlines"),
                (
                    246,
                    196,
                    253,
                    44,
                    "Recommendation replicas",
                    "Stateless service; measured capacity",
                ),
                (
                    246,
                    126,
                    253,
                    50,
                    "Provider and embedding runtime",
                    "Contracted search and versioned model",
                ),
                (
                    246,
                    54,
                    253,
                    50,
                    "Shared operational controls",
                    "Permitted cache, redacted telemetry",
                ),
                (12, 54, 190, 50, "Controlled release", "Cohort rollout and quality review"),
            ]
        for values in labels:
            box(*values)
        arrow([(107, 260), (107, 240)])
        arrow([(107, 196), (107, 176)])
        arrow([(202, 151), (224, 151), (224, 282), (246, 282)])
        arrow([(372, 260), (372, 240)])
        arrow([(372, 196), (372, 176)])
        arrow([(372, 126), (372, 104)])
        arrow([(246, 79), (202, 79)])


def paragraph(text, kind="ReportBody"):
    return Paragraph(rich(text), styles[kind])


def table(rows):
    count = len(rows[0])
    proportions = {
        2: [0.31, 0.69],
        3: [0.22, 0.39, 0.39],
        4: [0.22, 0.25, 0.27, 0.26],
        5: [0.12, 0.11, 0.32, 0.17, 0.28],
    }
    widths = [CONTENT_WIDTH * f for f in proportions.get(count, [1 / count] * count)]
    cells = [
        [paragraph(v.strip(), "TableHead" if r == 0 else "TableText") for v in row]
        for r, row in enumerate(rows)
    ]
    item = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    item.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, GREEN),
            ]
        )
    )
    return [KeepTogether([item]) if len(rows) <= 6 else item, Spacer(1, 12)]


def parse_markdown(text):
    lines, story, buffer = text.splitlines(), [], []

    def flush():
        if buffer:
            story.append(paragraph(" ".join(buffer)))
            buffer.clear()

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("```"):
            flush()
            language = line[3:]
            block = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            if language == "mermaid":
                production = "Packaged extension with managed sign-in" in " ".join(block)
                story += [Architecture(production), Spacer(1, 12)]
            else:
                wrapped = []
                for code_line in block:
                    wrapped.extend(
                        textwrap.wrap(
                            code_line, width=95, replace_whitespace=False, drop_whitespace=False
                        )
                        or [""]
                    )
                story.append(Preformatted("\n".join(wrapped), styles["ReportCode"]))
        elif line.startswith("|"):
            flush()
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = lines[index].strip().strip("|").split("|")
                if not all(re.fullmatch(r"[\s:\-]+", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            story += table(rows)
            continue
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            story.append(
                paragraph(
                    title, "Chapter" if level == 1 else "Section" if level == 2 else "Subsection"
                )
            )
        elif re.match(r"^(?:- |\d+\. )", line):
            flush()
            text = re.sub(r"^- ", "", line)
            story.append(
                Paragraph(
                    rich(text),
                    ParagraphStyle(
                        "ListItem",
                        parent=styles["ReportBody"],
                        leftIndent=11,
                        firstLineIndent=0,
                        bulletIndent=0,
                    ),
                    bulletText="-" if line.startswith("-") else None,
                )
            )
        elif not line:
            flush()
        else:
            buffer.append(line)
        index += 1
    flush()
    return story


def footer(canvas, document):
    canvas.saveState()
    if document.page == 1:
        canvas.setFillColor(PALE)
        canvas.rect(0, HEIGHT - 18, WIDTH, 18, fill=1, stroke=0)
        canvas.setFillColor(ORANGE)
        canvas.rect(42, HEIGHT - 97, 37, 4, fill=1, stroke=0)
    else:
        canvas.setFont(BOLD, 7.5)
        canvas.setFillColor(GREEN)
        canvas.drawString(42, HEIGHT - 29, "LISTS / CONTEXTUAL WEB DISCOVERY")
        canvas.setFont(BODY, 7)
        canvas.setFillColor(GRAY)
        canvas.drawRightString(WIDTH - 42, HEIGHT - 29, "TECHNICAL DESIGN / NOV 2026")
    canvas.setStrokeColor(colors.HexColor("#d3ded2"))
    canvas.line(42, 34, WIDTH - 42, 34)
    canvas.setFont(BODY, 7)
    canvas.setFillColor(GRAY)
    canvas.drawString(
        42, 21, "Deepak Yadav | Working reference implementation and production roadmap"
    )
    canvas.drawRightString(WIDTH - 42, 21, str(document.page))
    canvas.restoreState()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", default="output/pdf/LISTS_Architecture_and_Production_Roadmap.pdf"
    )
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=53,
        bottomMargin=49,
        title="LISTS: architecture and production roadmap",
        author="Deepak Yadav",
        subject="Contextual web recommendation system",
    )
    story = [
        Spacer(1, 80),
        Paragraph("ENGINEERING DESIGN / VERSION 1.0", styles["Eyebrow"]),
        Paragraph("LISTS.", styles["Cover"]),
        Paragraph("Contextual<br/>web discovery", styles["CoverTitle"]),
        paragraph(
            "End-to-end architecture, research, runnable implementation "
            "and a measurable path to production."
        ),
        Spacer(1, 27),
        paragraph("PREPARED FOR DEEPAK YADAV", "Eyebrow"),
        paragraph("12 November 2026", "Small"),
        Spacer(1, 40),
    ]
    callout = Table(
        [
            [paragraph("IMPLEMENTATION STATUS", "TableHead")],
            [
                paragraph(
                    "Working extension and Python API. Local lexical and MiniLM ONNX ranking. "
                    "Production identity, provider subscription and rollout gates remain explicit."
                )
            ],
        ],
        colWidths=[CONTENT_WIDTH],
    )
    callout.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GREEN),
                ("BACKGROUND", (0, 1), (-1, -1), PALE),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    story += [
        callout,
        PageBreak(),
        paragraph("How to use this report", "Chapter"),
        paragraph(
            "Read the high-level design first. Use the evidence section "
            "to inspect the technical choices, "
            "then use the release gates and runbooks to decide what must happen before deployment."
        ),
        paragraph(
            "This is a modern implementation of the supplied LISTS project brief. "
            "It does not claim "
            "to reproduce historical source code or prove production usage since 2017."
        ),
        Spacer(1, 10),
    ]
    chapters = [
        ("HLD.md", "1", "High-level design"),
        ("RESEARCH.md", "2", "Research and evidence"),
        ("SECURITY_PRIVACY.md", "3", "Security and privacy"),
        ("ROADMAP.md", "4", "Delivery roadmap"),
        ("OPERATIONS.md", "5", "Deployment and operations"),
        ("EVALUATION.md", "6", "Evaluation methodology"),
        ("ADR.md", "7", "Architecture decisions"),
        ("VERIFICATION.md", "8", "Verification record"),
    ]
    for filename, number, title in chapters:
        story.append(paragraph(f"{number}. {title}", "Section"))
        descriptions = {
            "HLD.md": "Use cases, topology, request journey, ranking, contracts and sizing.",
            "RESEARCH.md": "Primary papers and official implementation references.",
            "SECURITY_PRIVACY.md": "Trust boundaries, data sharing, controls and limitations.",
            "ROADMAP.md": "Ownership, sequencing, acceptance criteria and mandatory release gates.",
            "OPERATIONS.md": "Configuration, deployment, SLOs, incidents and rollback.",
            "EVALUATION.md": "Correctness, authored regression and independent relevance.",
            "ADR.md": "Technology choices with reasons and conditions for revisiting them.",
            "VERIFICATION.md": "Observed checks, local measurements and unverified areas.",
        }
        story.append(paragraph(descriptions[filename]))
    for filename, number, title in chapters:
        story.append(PageBreak())
        text = (ROOT / "docs" / filename).read_text()
        text = "# " + number + ". " + title + "\n" + "\n".join(text.splitlines()[1:])
        story += parse_markdown(text)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(str(target.resolve()))


if __name__ == "__main__":
    main()
