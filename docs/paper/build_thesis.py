"""Render the source-bound thesis and coverage figure without rerunning research."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
from pathlib import Path

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics import renderSVG
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Preformatted,
)

ROOT = Path(__file__).resolve().parents[2]
GREEN = colors.HexColor('#285445')
INK = colors.HexColor('#263B32')
MUTED = colors.HexColor('#657369')
PALE = colors.HexColor('#F0F3E9')
WIDTH = 524
METRICS = ('employment', 'gdp', 'school', 'immunization', 'mortality', 'life_expectancy')
LABELS = ('Employment', 'GDP index', 'Enrollment', 'DTP', 'Mortality', 'Life expectancy')
SEEDS = (11, 29, 47)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ascii_text(text):
    for a, b in {'\u2014': '-', '\u2013': '-', '\u2011': '-', '\u2019': "'", '\u2018': "'",
                 '\u201c': '"', '\u201d': '"', '\u2192': '->', '\u00a0': ' ', '\u00b1': '+/-'}.items():
        text = text.replace(a, b)
    return text


def inline(text):
    text = html.escape(ascii_text(text))
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a color="#285445" href="\2">\1</a>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'<font name="Courier" size="7.7">\1</font>', text)
    return re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name='BodyResearch', fontName='Helvetica', fontSize=9.1, leading=13.3,
                         textColor=INK, spaceAfter=8, splitLongWords=True))
    s.add(ParagraphStyle(name='ResearchH1', fontName='Times-Roman', fontSize=20, leading=23,
                         textColor=GREEN, spaceBefore=15, spaceAfter=9, keepWithNext=True))
    s.add(ParagraphStyle(name='ResearchH2', fontName='Helvetica-Bold', fontSize=11, leading=14,
                         textColor=GREEN, spaceBefore=11, spaceAfter=6, keepWithNext=True))
    s.add(ParagraphStyle(name='ResearchCell', fontName='Helvetica', fontSize=7.7, leading=10.4,
                         textColor=INK, splitLongWords=True))
    s.add(ParagraphStyle(name='ResearchSmall', fontName='Helvetica', fontSize=7.6, leading=10.5,
                         textColor=MUTED, spaceAfter=8, splitLongWords=True))
    return s


def table(data, widths, s):
    wrapped = [[Paragraph(inline(str(cell)), s['ResearchCell']) for cell in row] for row in data]
    t = Table(wrapped, colWidths=widths, repeatRows=1, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PALE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), .6, GREEN),
        ('LINEBELOW', (0, 1), (-1, -1), .25, colors.HexColor('#DDE3D8')),
        ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def markdown_flow(text, s):
    lines = text.splitlines()
    flow, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('# '):
            i += 1
            continue
        if line.startswith('```'):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(ascii_text(lines[i]))
                i += 1
            flow.append(Preformatted('\n'.join(code), ParagraphStyle('code', fontName='Courier', fontSize=7, leading=10)))
            i += 1
            continue
        if line.startswith('## '):
            flow.append(Paragraph(inline(line[3:]), s['ResearchH1']))
            i += 1
            continue
        if line.startswith('### '):
            flow.append(Paragraph(inline(line[4:]), s['ResearchH2']))
            i += 1
            continue
        if line.startswith('|'):
            data = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if any(re.sub(r'[-: ]', '', c) for c in cells):
                    data.append(cells)
                i += 1
            n = len(data[0])
            widths = [WIDTH / n] * n
            if n >= 4:
                widths = [WIDTH * .18] + [WIDTH * .82 / (n - 1)] * (n - 1)
            flow.extend([table(data, widths, s), Spacer(1, 9)])
            continue
        bullet = line.startswith('- ')
        paragraph = [line[2:] if bullet else line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith(('#', '|', '```', '- ')):
            paragraph.append(lines[i].strip())
            i += 1
        flow.append(Paragraph(inline(' '.join(paragraph)), s['BodyResearch'], bulletText='-' if bullet else None))
    return flow


def coverage_figure(scores):
    lookup = {(r['model'], r['metric']): r for r in scores if r['group'] == 'all'}
    data = [[lookup[f'network_{seed}', metric]['coverage_90'] * 100 for metric in METRICS] for seed in SEEDS]
    d = Drawing(WIDTH, 246)
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 42, 43, 473, 164
    chart.data = data
    chart.categoryAxis.categoryNames = list(LABELS)
    chart.categoryAxis.labels.fontName = 'Helvetica'
    chart.categoryAxis.labels.fontSize = 7.4
    chart.categoryAxis.labels.dy = -2
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontSize = 7.5
    chart.valueAxis.gridStrokeColor = colors.HexColor('#E1E7DB')
    chart.valueAxis.visibleGrid = True
    palette = (GREEN, colors.HexColor('#819D89'), colors.HexColor('#BE855E'))
    for j, color in enumerate(palette):
        chart.bars[j].fillColor = color
        chart.bars[j].strokeColor = None
        d.add(Rect(44 + j * 116, 228, 9, 7, fillColor=color, strokeColor=None))
        d.add(String(58 + j * 116, 228, f'Seed {SEEDS[j]}', fontName='Helvetica', fontSize=8, fillColor=INK))
    d.add(chart)
    y = 43 + 164 * .9
    d.add(Line(42, y, 515, y, strokeColor=colors.HexColor('#9C543D'), strokeWidth=1, strokeDashArray=[4, 3]))
    d.add(String(398, y + 5, 'Nominal 90%', fontName='Helvetica', fontSize=7.7, fillColor=colors.HexColor('#9C543D')))
    d.add(String(2, 211, '%', fontName='Helvetica', fontSize=8, fillColor=INK))
    return d, lookup, data


def build(output, publication_source):
    s = styles()
    thesis = ROOT / 'docs/THESIS.md'
    score_path = ROOT / 'client/public/data/history-scores.json'
    index = json.loads((ROOT / 'client/public/data/index.json').read_text())
    source = index['source_commit']
    scores = json.loads(score_path.read_text())
    assert scores['completed_configurations'] == 66 and scores['prediction_rows'] == 42097
    figure, lookup, data = coverage_figure(scores['scores'])
    output.parent.mkdir(parents=True, exist_ok=True)
    csv_path = output.parent / 'historical-coverage.csv'
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['metric', 'seed', 'coverage_percent', 'eligible_predictions', 'nominal_percent', 'scientific_source', 'run_id', 'score_file_sha256'])
        writer.writeheader()
        for j, seed in enumerate(SEEDS):
            for k, metric in enumerate(METRICS):
                writer.writerow(dict(metric=metric, seed=seed, coverage_percent=data[j][k],
                    eligible_predictions=lookup[f'network_{seed}', metric]['n'], nominal_percent=90,
                    scientific_source=source, run_id='history-final-clean-20261112', score_file_sha256=sha(score_path)))
    renderSVG.drawToFile(figure, str(output.parent / 'historical-coverage.svg'))

    body = s['BodyResearch']
    flow = [Spacer(1, 58), Paragraph('AFTERSHOCK<br/>ATLAS', ParagraphStyle('cover', fontName='Times-Roman', fontSize=46, leading=47, textColor=GREEN)),
            Spacer(1, 16), Paragraph('Pandemic trajectories, measurement<br/>and the limits of comparison', ParagraphStyle('subtitle', fontName='Helvetica', fontSize=16, leading=23, textColor=INK)),
            Spacer(1, 24), Paragraph('RESEARCH PREVIEW / 12 NOVEMBER 2026', s['ResearchSmall']),
            Paragraph('<b>Full acceptance is incomplete.</b>', body),
            Paragraph('This paper preserves failed forecasts, unsupported comparisons and missing evidence. It provides population-level research and no clinical or personal-risk recommendations.', body), Spacer(1, 18)]
    flow.append(table([['Evidence identity', 'Frozen value'], ['Scientific executable', source], ['Snapshot publication', publication_source],
        ['Diagnostic', 'history-final-clean-20261112 / passed / 19 tamper cases rejected'],
        ['Full profile', 'history-final-full-20261112 / exit 1 / seven incomplete gates'],
        ['Source partitions', '22 core + 2 survey + 43 historical partitions; not independent samples']], [138, 386], s))
    flow.extend([Spacer(1, 14), Paragraph('Original source code is MIT licensed. WHO excess-mortality-derived material retains CC BY-NC-SA 3.0 IGO terms; other data retain their source-specific licenses. See the repository DATA_RIGHTS.md. This noncommercial paper contains no respondent records or individual genomes.', s['ResearchSmall']), PageBreak(),
        Paragraph('Read the uncertainty first', s['ResearchH1']),
        Paragraph('Every learned outcome undercovers its nominal interval in the historical exercise. Mortality and life expectancy have eligible archived targets only for 2022. Better CRPS does not establish reliable uncertainty.', body), figure])
    table_rows = [['Historical outcome', 'Eligible targets per seed', 'Coverage across three seeds']]
    for k, metric in enumerate(METRICS):
        values = [row[k] for row in data]
        table_rows.append([LABELS[k], lookup['network_11', metric]['n'], f'{min(values):.2f}% to {max(values):.2f}%'])
    flow.extend([table(table_rows, [176, 145, 203], s), Spacer(1, 9),
        Paragraph('Figure 1. Empirical coverage of nominal 90% historical predictive intervals. The seed range is not a confidence interval. Raw values are in the companion historical-coverage.csv. Run: history-final-clean-20261112. Source: ' + source + '.', s['ResearchSmall']),
        Paragraph('The learned GDP CRPS is 41.27% worse than its validation-selected baseline. Only routine DTP meets the registered practical improvement criterion. These exploratory comparisons reuse previously inspected calendar outcomes and do not isolate causal pandemic effects.', body), PageBreak()])
    flow.extend(markdown_flow(thesis.read_text(), s))
    flow.extend([Spacer(1, 10), Paragraph('Artifact provenance', s['ResearchH1']),
        Paragraph('Scientific source: ' + source + '. Snapshot publication: ' + publication_source + '. Thesis Markdown SHA256: ' + sha(thesis) + '. Score partition SHA256: ' + sha(score_path) + '.', s['ResearchSmall'])])
    links = list(dict.fromkeys(re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', thesis.read_text())))
    flow.append(table([['Reference', 'Primary source URL'], *[list(pair) for pair in links]], [150, 374], s))

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GREEN)
        canvas.rect(0, 782, 612, 10, fill=1, stroke=0)
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(MUTED)
        if doc.page > 1:
            canvas.drawString(44, 765, 'AFTERSHOCK ATLAS / RESEARCH PREVIEW')
            canvas.drawRightString(568, 765, source[:12])
        canvas.drawString(44, 24, 'Full acceptance incomplete / Nonclinical population research')
        canvas.drawRightString(568, 24, str(doc.page))
        canvas.restoreState()
    # Platypus frames add six points of padding inside each document margin.
    document = SimpleDocTemplate(str(output), pagesize=letter, leftMargin=38, rightMargin=38,
        topMargin=41, bottomMargin=37, title='Aftershock Atlas: trajectories and the limits of comparison',
        author='Aftershock Atlas', subject='Source-bound research preview; full acceptance incomplete')
    document.build(flow, onFirstPage=frame, onLaterPages=frame)
    receipt = {'scientific_source': source, 'publication_source': publication_source, 'thesis_markdown_sha256': sha(thesis),
        'score_partition_sha256': sha(score_path), 'figure_data_sha256': sha(csv_path), 'authoring_code_sha256': sha(Path(__file__)),
        'pdf_sha256': sha(output), 'full_acceptance': False, 'figure_rows': 18}
    (output.parent / 'ARTIFACT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/paper/aftershock-thesis.pdf')
    parser.add_argument('--publication-source', default=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    args = parser.parse_args()
    build(args.output, args.publication_source)
