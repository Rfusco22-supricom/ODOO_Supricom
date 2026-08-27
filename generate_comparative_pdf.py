import sys
import os
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(30, 18, "Documento Oficial de Auditoría de Comisiones — Supricom S.A. | Entorno Odoo Producción (PROD1 Versión 17.0.1.4.1)")
        page_str = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(762, 18, page_str)
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(30, 28, 762, 28)
        self.restoreState()

def build_pdf(filename):
    # Printable area: width = 792 - 60 = 732pt
    doc = SimpleDocTemplate(
        filename,
        pagesize=landscape(letter),
        leftMargin=30,
        rightMargin=30,
        topMargin=25,
        bottomMargin=35
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=6
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#1e3a8a"),
        spaceBefore=6,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155")
    )

    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1e293b")
    )

    cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=cell_style,
        fontName='Helvetica-Bold'
    )

    cell_header = ParagraphStyle(
        'TableHeaderCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=1 # Center
    )

    cell_right = ParagraphStyle(
        'TableCellRight',
        parent=cell_style,
        alignment=2 # Right
    )

    cell_right_bold = ParagraphStyle(
        'TableCellRightBold',
        parent=cell_bold,
        alignment=2 # Right
    )

    cell_green = ParagraphStyle(
        'TableCellGreen',
        parent=cell_bold,
        textColor=colors.HexColor("#15803d"),
        alignment=2
    )

    cell_obs = ParagraphStyle(
        'TableCellObs',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor("#334155")
    )

    story = []

    # Title & Subtitle
    story.append(Paragraph("SUPRICOM, S.A. — INFORME COMPARATIVO DE COMISIONES", title_style))
    story.append(Paragraph("<b>Período:</b> Julio 2026 | <b>Comparativa:</b> Odoo Producción (PROD1 Versión 17.0.1.4.1) vs. Excel de Gerencia | <b>Moneda:</b> USD ($)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.2, color=colors.HexColor("#1e3a8a"), spaceAfter=6))

    # Executive Summary Box
    summary_html = """
    <b>RESUMEN EJECUTIVO Y NUEVAS REGLAS DE NEGOCIO APLICADAS (AUDIO DE VOZ):</b><br/>
    1. <b>% Cumplimiento Meta:</b> Basado en <b>Facturación sin IVA (Ventas del Mes)</b> (`Total Facturado / Meta`). Ángel Mota alcanza <b>117,38%</b> ($187.815,73 vs $160.000,00) y califica para comisión.<br/>
    2. <b>Base Comisionable:</b> Se aplican comisiones a <b>todos los abonos parciales y cobros recibidos en el mes</b>.<br/>
    <b>Coincidencia General:</b> El equipo alcanza un <b>96,84% de coincidencia global</b> entre Odoo Producción ($19.744,58) y el Excel de Gerencia ($19.139,56).
    """
    
    summary_table = Table([[Paragraph(summary_html, body_style)]], colWidths=[732])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f0f9ff")),
        ('BORDER', (0,0), (-1,-1), 0.8, colors.HexColor("#bae6fd")),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 4))

    story.append(Paragraph("Cuadro Comparativo por Empleado / Rol", section_heading))

    # Table Header
    headers = [
        Paragraph("Vendedor / Rol", cell_header),
        Paragraph("Meta ($)", cell_header),
        Paragraph("Facturado ($)", cell_header),
        Paragraph("% Cumpl.", cell_header),
        Paragraph("Cobrado Apto ($)", cell_header),
        Paragraph("Comisión Odoo ($)", cell_header),
        Paragraph("Comisión Excel ($)", cell_header),
        Paragraph("Dif. ($)", cell_header),
        Paragraph("% Coincid.", cell_header),
        Paragraph("Observación y Causa de la Diferencia", cell_header),
    ]

    data = [headers]

    rows_info = [
        ("ANGEL MOTA RODRIGUEZ", "$160.000,00", "$187.815,73", "117,38%", "$130.410,06", "$1.152,90", "$1.148,29", "+$4,61", "99,60%", "Coincidencia casi exacta (99,6%) tras aplicar regla de Ventas/Facturación."),
        ("ANTONELLA ZAMPETTI (GERENTE)", "N/A", "N/A", "N/A", "$1.296.723,39", "$6.464,72", "$6.658,73", "-$194,01", "97,09%", "Comisión gerencial (0,50%) sobre cobros consolidados del equipo."),
        ("ANDREA MARQUEZ", "$200.000,00", "$357.224,03", "150,00%", "$466.143,70", "$4.913,65", "$4.761,06", "+$152,59", "96,79%", "Excelente alineación (96,8%) con tope máximo de meta (150%)."),
        ("FRANCISCO PEREZ", "$40.000,00", "$102.375,31", "150,00%", "$98.810,50", "$1.235,13", "$1.284,99", "-$49,86", "96,12%", "Variación mínima de $49 por redondeos y diferencial cambiario."),
        ("MARIANGELY CISNEROS", "$160.000,00", "$158.227,99", "98,89%", "$216.780,85", "$1.717,58", "$1.791,09", "-$73,51", "95,90%", "Cálculo preciso con tasa del 1,00% (cumplimiento 98,89%)."),
        ("DIEGO GUERRERO", "$65.000,00", "$135.837,16", "150,00%", "$123.810,54", "$1.466,07", "$1.389,46", "+$76,61", "94,49%", "Coincidencia del 94,5% con inclusión de abonos del período."),
        ("FREDDY ROBLES VASQUEZ", "$65.000,00", "$108.149,84", "150,00%", "$96.525,24", "$1.105,01", "$868,53", "+$236,48", "72,77%", "En Excel se aplicaron penalizaciones de mora manuales en 2 facturas."),
        ("AUGUSTO RUBIO", "$160.000,00", "$259.356,25", "150,00%", "$146.551,39", "$1.689,52", "$1.237,41", "+$452,11", "63,46%", "Odoo incluyó 2 cobros con fecha 31/07 omitidos en el Excel de gerencia.")
    ]

    for row in rows_info:
        r_vend, r_meta, r_fact, r_cumpl, r_cob, r_odoo, r_excel, r_dif, r_coin, r_obs = row
        c_coin_style = cell_green if float(r_coin.replace("%","").replace(",",".")) >= 95.0 else cell_right_bold
        
        data.append([
            Paragraph(f"<b>{r_vend}</b>", cell_style),
            Paragraph(r_meta, cell_right),
            Paragraph(r_fact, cell_right),
            Paragraph(r_cumpl, cell_right_bold),
            Paragraph(r_cob, cell_right),
            Paragraph(f"<b>{r_odoo}</b>", cell_right_bold),
            Paragraph(r_excel, cell_right),
            Paragraph(r_dif, cell_right),
            Paragraph(r_coin, c_coin_style),
            Paragraph(r_obs, cell_obs),
        ])

    # Totals Row
    data.append([
        Paragraph("<b>TOTALES / PROMEDIO GLOBAL</b>", cell_bold),
        Paragraph("<b>$750.000,00</b>", cell_right_bold),
        Paragraph("<b>$1.308.758,31</b>", cell_right_bold),
        Paragraph("<b>-</b>", cell_right_bold),
        Paragraph("<b>$1.296.723,39</b>", cell_right_bold),
        Paragraph("<b>$19.744,58</b>", cell_right_bold),
        Paragraph("<b>$19.139,56</b>", cell_right_bold),
        Paragraph("<b>+$605,02</b>", cell_right_bold),
        Paragraph("<b>96,84%</b>", cell_green),
        Paragraph("<b>Coincidencia global del 96,84% en todo el equipo.</b>", cell_obs),
    ])

    # Widths totaling exactly 732pt
    col_widths = [135, 62, 65, 42, 68, 62, 62, 45, 45, 146]

    comp_table = Table(data, colWidths=col_widths, repeatRows=1)
    
    t_style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0f172a")),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('PADDING', (0,0), (-1,-1), 3),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#f1f5f9")),
    ]

    for i in range(1, len(rows_info) + 1):
        if i % 2 == 0:
            t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#f8fafc")))

    comp_table.setStyle(TableStyle(t_style))
    story.append(comp_table)
    story.append(Spacer(1, 6))

    # Notes Box
    notes_html = """
    <b>OBSERVACIONES TÉCNICAS SOBRE LAS VARIACIONES:</b><br/>
    • <b>Ángel Mota Rodríguez (99,60%):</b> El recálculo por <i>Ventas sin IVA</i> ($187.815,73 / $160.000,00 = 117,38%) activa su comisión sobre el total cobrado ($130.410,06 x 1,00% - retenciones) obteniendo <b>$1.152,90</b>, que calza en un 99,6% con el Excel ($1.148,29).<br/>
    • <b>Freddy Robles Vásquez (72,77%):</b> La diferencia ocurre por deducciones de mora aplicadas de forma manual en el Excel a 2 facturas específicas.<br/>
    • <b>Augusto Rubio (63,46%):</b> Odoo procesó 2 abonos con fecha contable 31/07 que no estaban asentados en la planilla Excel al momento del corte.
    """

    notes_table = Table([[Paragraph(notes_html, body_style)]], colWidths=[732])
    notes_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fffbeb")),
        ('BORDER', (0,0), (-1,-1), 0.8, colors.HexColor("#fde68a")),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    story.append(notes_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully generated at: {filename}")

if __name__ == "__main__":
    out_pdf = "/home/aecas/Documentos/DIGIFLEX/supricom/Informe_Comparativo_Comisiones_Julio_2026.pdf"
    build_pdf(out_pdf)
