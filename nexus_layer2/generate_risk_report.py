"""
Nexus Layer 5 - Executive Risk Report PDF Generator
Produces a comprehensive PDF from nexus_data.json.
Uses reportlab for PDF generation with charts and tables.
"""

import sys, json
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, Image
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing, Rect, String, Circle
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics import renderPDF
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("[!] reportlab not installed. Install with: pip install reportlab")

SCRIPT_DIR = Path(__file__).resolve().parent
NEXUS_DATA = SCRIPT_DIR / "nexus_data.json"
OUTPUT_PDF = SCRIPT_DIR / "nexus_risk_report.pdf"


def load_nexus_data():
    with open(NEXUS_DATA, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        'NexusTitle', parent=styles['Title'],
        fontSize=28, textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=30, alignment=TA_CENTER
    ))
    styles.add(ParagraphStyle(
        'NexusSubtitle', parent=styles['Normal'],
        fontSize=14, textColor=colors.HexColor('#6c757d'),
        alignment=TA_CENTER, spaceAfter=20
    ))
    styles.add(ParagraphStyle(
        'SectionHead', parent=styles['Heading1'],
        fontSize=18, textColor=colors.HexColor('#0f3460'),
        spaceBefore=20, spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        'SubSection', parent=styles['Heading2'],
        fontSize=14, textColor=colors.HexColor('#16213e'),
        spaceBefore=12, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        'BodyText2', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#333333'),
        leading=14
    ))
    styles.add(ParagraphStyle(
        'AlertText', parent=styles['Normal'],
        fontSize=10, textColor=colors.HexColor('#dc3545'),
        leading=14
    ))
    styles.add(ParagraphStyle(
        'CellText', parent=styles['Normal'],
        fontSize=8, textColor=colors.HexColor('#333333'),
        leading=10
    ))
    return styles


def risk_color(level):
    return {
        "critical": colors.HexColor('#dc3545'),
        "high": colors.HexColor('#fd7e14'),
        "medium": colors.HexColor('#ffc107'),
        "low": colors.HexColor('#28a745'),
    }.get(level, colors.HexColor('#6c757d'))


def make_risk_badge(level):
    return f'<font color="{risk_color(level).hexval()}">[{level.upper()}]</font>'


def build_cover_page(story, styles, data):
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("NEXUS", styles['NexusTitle']))
    story.append(Paragraph("Causal Intelligence Risk Report", styles['NexusSubtitle']))
    story.append(Spacer(1, 0.5 * inch))

    meta = data.get("meta", {})
    story.append(Paragraph(
        f"Repository: {meta.get('repository', 'N/A')}", styles['NexusSubtitle']
    ))
    story.append(Paragraph(
        f"Generated: {meta.get('generated_at', 'N/A')[:19]}", styles['NexusSubtitle']
    ))
    story.append(Paragraph(
        f"Total DPRs: {meta.get('total_dprs', 0)} | "
        f"Nodes: {meta.get('total_nodes', 0)} | "
        f"Relationships: {meta.get('total_relationships', 0)}",
        styles['NexusSubtitle']
    ))

    # Org risk score
    org_score = data.get("org_risk_score", 0)
    story.append(Spacer(1, 0.5 * inch))
    score_color = '#28a745' if org_score < 30 else '#ffc107' if org_score < 60 else '#dc3545'
    story.append(Paragraph(
        f'<font size=36 color="{score_color}">{org_score}</font>'
        f'<font size=14 color="#6c757d">/100 Organizational Risk Score</font>',
        ParagraphStyle('ScoreStyle', alignment=TA_CENTER)
    ))
    story.append(PageBreak())


def build_executive_summary(story, styles, data):
    story.append(Paragraph("1. Executive Summary", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    dprs = data.get("dprs", [])
    alerts = data.get("decay_alerts", [])
    runs = data.get("monitoring_runs", [])

    critical = sum(1 for d in dprs if d.get("blast_radius") == "critical")
    high_decay = sum(1 for d in dprs if d.get("decay_risk") == "high")
    active_decay = sum(1 for a in alerts if a.get("already_decaying"))

    story.append(Paragraph(
        f"This report analyzes <b>{len(dprs)}</b> architectural Decision Provenance Records "
        f"from the PostgreSQL repository. The analysis reveals <b>{critical}</b> decisions with "
        f"critical blast radius, <b>{high_decay}</b> with high assumption decay risk, and "
        f"<b>{active_decay}</b> actively decaying assumptions.",
        styles['BodyText2']
    ))
    story.append(Spacer(1, 10))

    if runs:
        latest = runs[-1]
        story.append(Paragraph(
            f"Latest monitoring run ({latest.get('run_at', 'N/A')[:19]}): "
            f"Scanned {latest.get('commits_scanned', 0)} commits, "
            f"evaluated {latest.get('dprs_evaluated', 0)} DPRs, "
            f"raised {latest.get('new_alerts', 0)} new alerts.",
            styles['BodyText2']
        ))
    story.append(Spacer(1, 15))


def build_dpr_table(story, styles, data):
    story.append(Paragraph("2. Decision Provenance Records", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    dprs = data.get("dprs", [])
    header = ['ID', 'Title', 'Component', 'Blast', 'Decay', 'Deps']
    rows = [header]
    for d in dprs:
        rows.append([
            d['id'],
            Paragraph(d['title'][:40], styles['CellText']),
            d['component'],
            d['blast_radius'].upper(),
            d['decay_risk'].upper(),
            str(len(d.get('causal_out', []))),
        ])

    t = Table(rows, colWidths=[50, 140, 65, 50, 50, 35])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f3460')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))


def build_decay_alerts(story, styles, data):
    story.append(Paragraph("3. Active Assumption Decay Alerts", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    alerts = data.get("decay_alerts", [])
    for a in alerts:
        if a.get("already_decaying"):
            story.append(Paragraph(
                f'<font color="#dc3545"><b>DECAYING</b></font> — '
                f'<b>{a["dpr_id"]}: {a.get("title", "")}</b>',
                styles['BodyText2']
            ))
            story.append(Paragraph(
                f'Evidence: {a.get("decay_evidence", "N/A")[:200]}',
                styles['BodyText2']
            ))
            story.append(Spacer(1, 8))

    # Show monitoring results if available
    dprs = data.get("dprs", [])
    monitored = [d for d in dprs if (d.get("decay_alert") or {}).get("live_confidence") is not None]
    if monitored:
        story.append(Paragraph("Live Monitoring Results", styles['SubSection']))
        header = ['DPR', 'Confidence', 'Holds?', 'Trend']
        rows = [header]
        for d in monitored:
            alert = d["decay_alert"]
            rows.append([
                d["id"],
                f'{alert.get("live_confidence", 0):.2f}',
                "Yes" if alert.get("live_still_holds") else "No",
                alert.get("live_reasoning", "")[:60] if alert.get("live_reasoning") else "",
            ])
        t = Table(rows, colWidths=[55, 65, 40, 230])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fd7e14')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
    story.append(Spacer(1, 15))


def build_knowledge_concentration(story, styles, data):
    story.append(PageBreak())
    story.append(Paragraph("4. Knowledge Concentration & SPOF Risk", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    kc = data.get("knowledge_concentration", {})
    if not kc:
        story.append(Paragraph("No knowledge concentration data available.", styles['BodyText2']))
        return

    # Human profiles
    story.append(Paragraph("Top Contributors by Bus Factor Risk", styles['SubSection']))
    header = ['Name', 'DPRs', 'Components', 'Risk Score']
    rows = [header]
    for h in kc.get("human_profiles", [])[:8]:
        rows.append([
            h['name'],
            str(h['dpr_count']),
            str(h['component_count']),
            f"{h['bus_factor_risk_score']:.1f}",
        ])
    t = Table(rows, colWidths=[120, 45, 75, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))

    # Component SPOF
    story.append(Paragraph("Component SPOF Scores", styles['SubSection']))
    header = ['Component', 'DPRs', 'Humans', 'SPOF Score']
    rows = [header]
    for c in kc.get("component_profiles", []):
        rows.append([
            c['component'],
            str(c['dpr_count']),
            str(c['unique_humans']),
            f"{c['spof_score']:.1f}",
        ])
    t = Table(rows, colWidths=[100, 45, 55, 70])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16213e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dee2e6')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 15))


def build_counterfactuals(story, styles, data):
    story.append(PageBreak())
    story.append(Paragraph("5. Counterfactual Analysis", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    traces = data.get("counterfactual_traces", [])
    if not traces:
        story.append(Paragraph("No counterfactual traces generated yet.", styles['BodyText2']))
        return

    for t_entry in traces:
        result = t_entry.get("result", {})
        verdict = result.get("verdict", "unknown").upper()
        conf = result.get("confidence", 0)
        v_color = '#28a745' if verdict == 'BETTER' else '#dc3545' if verdict == 'WORSE' else '#ffc107'

        story.append(Paragraph(
            f'<b>{t_entry["id"]}</b>: {t_entry["question"]}',
            styles['SubSection']
        ))
        story.append(Paragraph(
            f'<font color="{v_color}"><b>Verdict: {verdict}</b></font> '
            f'(confidence: {conf:.0%}) | '
            f'Downstream impact: {t_entry.get("downstream_count", 0)} DPRs',
            styles['BodyText2']
        ))
        narrative = result.get("timeline_narrative", "")
        if narrative:
            story.append(Paragraph(f'<i>{narrative[:300]}</i>', styles['BodyText2']))

        # New problems
        problems = result.get("new_problems", [])
        if problems:
            story.append(Paragraph("New problems:", styles['BodyText2']))
            for p in problems[:3]:
                story.append(Paragraph(f"  \u2022 {p[:120]}", styles['BodyText2']))

        story.append(Spacer(1, 12))


def build_recommendations(story, styles, data):
    story.append(PageBreak())
    story.append(Paragraph("6. Recommendations", styles['SectionHead']))
    story.append(HRFlowable(width="100%", color=colors.HexColor('#0f3460')))
    story.append(Spacer(1, 10))

    dprs = data.get("dprs", [])
    alerts = data.get("decay_alerts", [])
    kc = data.get("knowledge_concentration", {})

    # Priority 1: Actively decaying
    decaying = [a for a in alerts if a.get("already_decaying")]
    if decaying:
        story.append(Paragraph(
            f'<font color="#dc3545"><b>CRITICAL:</b></font> '
            f'{len(decaying)} assumptions actively decaying. '
            f'Immediate architectural review recommended for: '
            f'{", ".join(a["dpr_id"] for a in decaying)}.',
            styles['BodyText2']
        ))
        story.append(Spacer(1, 8))

    # Priority 2: Bus factor
    top_humans = kc.get("top_spof_humans", [])
    if top_humans:
        story.append(Paragraph(
            f'<font color="#fd7e14"><b>HIGH:</b></font> '
            f'Knowledge concentration risk. Top contributor '
            f'<b>{top_humans[0]}</b> is involved in '
            f'{kc.get("human_profiles", [{}])[0].get("dpr_count", 0)} DPRs. '
            f'Cross-training recommended.',
            styles['BodyText2']
        ))
        story.append(Spacer(1, 8))

    # Priority 3: Critical blast radius
    critical = [d for d in dprs if d.get("blast_radius") == "critical"]
    if critical:
        story.append(Paragraph(
            f'<font color="#ffc107"><b>MEDIUM:</b></font> '
            f'{len(critical)} DPRs have critical blast radius. '
            f'Changes to these decisions cascade across the entire system: '
            f'{", ".join(d["id"] for d in critical)}.',
            styles['BodyText2']
        ))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f'<i>Report generated by Nexus Causal Intelligence Engine at '
        f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</i>',
        ParagraphStyle('Footer', fontSize=8, textColor=colors.HexColor('#adb5bd'),
                        alignment=TA_CENTER)
    ))


def generate_report():
    if not HAS_REPORTLAB:
        print("[!] reportlab required. Install with: pip install reportlab")
        return None

    print("=" * 60)
    print("  NEXUS - Executive Risk Report Generator")
    print("=" * 60)

    data = load_nexus_data()
    styles = create_styles()

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF), pagesize=A4,
        topMargin=30*mm, bottomMargin=20*mm,
        leftMargin=20*mm, rightMargin=20*mm,
        title="Nexus Causal Intelligence Risk Report",
        author="Nexus Engine"
    )

    story = []
    build_cover_page(story, styles, data)
    build_executive_summary(story, styles, data)
    build_dpr_table(story, styles, data)
    build_decay_alerts(story, styles, data)
    build_knowledge_concentration(story, styles, data)
    build_counterfactuals(story, styles, data)
    build_recommendations(story, styles, data)

    doc.build(story)
    size = OUTPUT_PDF.stat().st_size
    print(f"\n[+] Written: {OUTPUT_PDF}")
    print(f"    Size: {size:,} bytes")
    print(f"    Pages: ~{max(7, size // 4000)}")
    print("=" * 60)
    return str(OUTPUT_PDF)


if __name__ == "__main__":
    generate_report()
