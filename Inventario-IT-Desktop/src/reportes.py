"""
reportes.py – Generador de reportes PDF (reportlab) del Inventario IT.

  - generar_reporte_inventario : listado general (respeta los filtros de la tabla)
  - generar_reporte_garantias  : garantías vencidas y por vencer
  - generar_ficha_equipo       : ficha individual con imagen, historial y firmas
"""
from collections import Counter
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (Image, KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

import database as db

AZUL = colors.HexColor("#1e293b")
GRIS = colors.HexColor("#64748b")
LINEA = colors.HexColor("#cbd5e1")
ZEBRA = colors.HexColor("#f1f5f9")
ESTADO_BG = {"Operativo": "#dcfce7", "En Mantenimiento": "#fef3c7",
             "En Almacén": "#dbeafe", "Dado de baja": "#fee2e2"}

_base = getSampleStyleSheet()
ESTILO_TITULO = ParagraphStyle("titulo", parent=_base["Title"], fontSize=18, textColor=AZUL,
                               alignment=0, spaceAfter=2)
ESTILO_SUB = ParagraphStyle("sub", parent=_base["Normal"], fontSize=9, textColor=GRIS)
ESTILO_H2 = ParagraphStyle("h2", parent=_base["Heading2"], fontSize=12, textColor=AZUL,
                           spaceBefore=12, spaceAfter=4)
ESTILO_CELDA = ParagraphStyle("celda", parent=_base["Normal"], fontSize=7.5, leading=9)
ESTILO_CAB = ParagraphStyle("cab", parent=ESTILO_CELDA, textColor=colors.white,
                            fontName="Helvetica-Bold")
ESTILO_ETQ = ParagraphStyle("etq", parent=ESTILO_CELDA, fontName="Helvetica-Bold",
                            textColor=AZUL, fontSize=8)
ESTILO_VAL = ParagraphStyle("val", parent=ESTILO_CELDA, fontSize=8.5, leading=10.5)


# ───────────────────────── Utilidades ─────────────────────────
def _p(texto, estilo=ESTILO_CELDA):
    return Paragraph(escape("" if texto is None else str(texto)), estilo)


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRIS)
    ancho = doc.pagesize[0]
    canvas.drawString(doc.leftMargin, 1 * cm,
                      f"Inventario IT · generado el {datetime.now():%d/%m/%Y %H:%M}")
    canvas.drawRightString(ancho - doc.rightMargin, 1 * cm, f"Página {doc.page}")
    canvas.restoreState()


def _tabla(cabeceras, filas, anchos, extra=None):
    data = [[Paragraph(escape(c), ESTILO_CAB) for c in cabeceras]]
    data += [[_p(v) for v in fila] for fila in filas]
    t = Table(data, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("GRID", (0, 0), (-1, -1), 0.25, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ] + (extra or [])))
    return t


def _imagen(rel, max_w, max_h):
    ruta = db.ruta_imagen(rel)
    if not ruta or not ruta.is_file():
        return None
    try:
        w, h = ImageReader(str(ruta)).getSize()
        esc = min(max_w / w, max_h / h)
        return Image(str(ruta), width=w * esc, height=h * esc)
    except Exception:
        return None


def _doc(ruta, tamano, titulo, margen=1.5 * cm):
    return SimpleDocTemplate(str(ruta), pagesize=tamano, title=titulo, author="Inventario IT",
                             leftMargin=margen, rightMargin=margen, topMargin=1.5 * cm,
                             bottomMargin=1.8 * cm)


# ───────────────────────── Reporte general ─────────────────────────
def generar_reporte_inventario(ruta, filas, filtros=""):
    """PDF horizontal con resumen + tabla de los equipos recibidos en `filas`."""
    doc = _doc(ruta, landscape(A4), "Reporte de inventario IT")
    hoy = date.today().isoformat()

    por_estado = Counter(f["estado"] for f in filas)
    valor = sum(f["costo"] for f in filas if f["estado"] != "Dado de baja")
    vencidas = sum(1 for f in filas if f["garantia_hasta"] and f["garantia_hasta"] < hoy
                   and f["estado"] != "Dado de baja")

    el = [Paragraph("Reporte de Inventario de Activos IT", ESTILO_TITULO),
          _p(f"Generado el {datetime.now():%d/%m/%Y %H:%M} · Filtros: {filtros or 'ninguno'}", ESTILO_SUB),
          Spacer(1, 10)]

    resumen = Table(
        [["Total", "Operativos", "En mantenimiento", "En almacén", "Dados de baja",
          "Garantías vencidas", "Valor del parque (S/)"],
         [len(filas), por_estado["Operativo"], por_estado["En Mantenimiento"],
          por_estado["En Almacén"], por_estado["Dado de baja"], vencidas, f"{valor:,.0f}"]],
        colWidths=[3.7 * cm] * 7)
    resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 1), (-1, 1), 14),
        ("TEXTCOLOR", (0, 1), (-1, 1), AZUL), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.25, LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el += [resumen, Spacer(1, 8)]

    tipos = sorted(Counter(f["tipo"] for f in filas).items())
    if tipos:
        ancho = min(3.4 * cm, 26 * cm / len(tipos))
        t_tipos = Table([[t for t, _ in tipos], [n for _, n in tipos]], colWidths=[ancho] * len(tipos))
        t_tipos.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ZEBRA), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.25, LINEA)]))
        el += [Paragraph("Distribución por tipo", ESTILO_H2), t_tipos]

    el.append(Paragraph("Detalle de activos", ESTILO_H2))
    cab = ["Código", "Equipo", "Tipo", "Marca / Modelo", "N.º Serie", "Usuario",
           "Departamento", "Estado", "Garantía", "Costo S/"]
    datos, extra = [], []
    for i, f in enumerate(filas, start=1):
        g = f["garantia_hasta"]
        garantia = "—" if not g else ("Vencida" if g < hoy else "Vigente")
        datos.append([f["codigo_activo"], f["nombre_equipo"], f["tipo"], f"{f['marca']} {f['modelo']}",
                      f["num_serie"], f["usuario_asignado"], f["departamento"], f["estado"],
                      garantia, f"{f['costo']:,.2f}"])
        extra.append(("BACKGROUND", (7, i), (7, i), colors.HexColor(ESTADO_BG.get(f["estado"], "#ffffff"))))
    anchos = [1.7, 2.0, 2.6, 4.2, 3.0, 3.6, 2.8, 2.4, 1.8, 2.0]
    el.append(_tabla(cab, datos, [a * cm for a in anchos], extra))
    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return ruta


# ───────────────────────── Reporte de garantías ─────────────────────────
def generar_reporte_garantias(ruta, dias=60):
    """PDF con garantías vencidas y las que vencen en los próximos `dias` días."""
    doc = _doc(ruta, landscape(A4), "Reporte de garantías")
    hoy = date.today()
    limite = (hoy + timedelta(days=dias)).isoformat()
    h = hoy.isoformat()
    filas = [f for f in db.obtener_equipos() if f["garantia_hasta"] and f["estado"] != "Dado de baja"]
    vencidas = sorted((f for f in filas if f["garantia_hasta"] < h), key=lambda f: f["garantia_hasta"])
    por_vencer = sorted((f for f in filas if h <= f["garantia_hasta"] <= limite),
                        key=lambda f: f["garantia_hasta"])

    def seccion(titulo, lista):
        bloque = [Paragraph(f"{titulo} ({len(lista)})", ESTILO_H2)]
        if not lista:
            bloque.append(_p("Sin equipos en esta categoría.", ESTILO_SUB))
            return bloque
        datos = []
        for f in lista:
            d = (date.fromisoformat(f["garantia_hasta"]) - hoy).days
            datos.append([f["codigo_activo"], f["nombre_equipo"], f"{f['marca']} {f['modelo']}",
                          f["num_serie"], f["usuario_asignado"], f["proveedor"],
                          f["garantia_hasta"], f"{d} d" if d >= 0 else f"hace {-d} d"])
        anchos = [1.8, 2.2, 5.0, 3.4, 4.0, 3.6, 2.4, 2.2]
        bloque.append(_tabla(["Código", "Equipo", "Marca / Modelo", "N.º Serie", "Usuario",
                              "Proveedor", "Vence", "Días"], datos, [a * cm for a in anchos]))
        return bloque

    el = [Paragraph("Reporte de Garantías", ESTILO_TITULO),
          _p(f"Generado el {datetime.now():%d/%m/%Y %H:%M} · Ventana de aviso: {dias} días "
             "(no incluye equipos dados de baja)", ESTILO_SUB)]
    el += seccion("Garantías vencidas", vencidas)
    el += seccion(f"Vencen en los próximos {dias} días", por_vencer)
    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return ruta


# ───────────────────────── Ficha individual ─────────────────────────
def generar_ficha_equipo(ruta, equipo_id):
    """PDF A4 con la ficha completa de un activo (imagen, specs, historial, firmas)."""
    e = db.obtener_equipo(equipo_id)
    if e is None:
        raise ValueError("El equipo no existe.")
    doc = _doc(ruta, A4, f"Ficha {e['codigo_activo']}", margen=2 * cm)

    el = [Paragraph(f"Ficha de activo · {escape(e['codigo_activo'])}", ESTILO_TITULO),
          _p(f"{e['nombre_equipo']} — emitida el {date.today():%d/%m/%Y}", ESTILO_SUB),
          Spacer(1, 10)]

    # Cabecera: imagen + datos principales
    img = _imagen(e["imagen_path"], 6.2 * cm, 4.6 * cm) or _p("Sin imagen registrada", ESTILO_VAL)
    principales = [("Tipo", e["tipo"]), ("Marca / Modelo", f"{e['marca']} {e['modelo']}"),
                   ("N.º de serie", e["num_serie"]), ("Estado", e["estado"]),
                   ("Usuario asignado", e["usuario_asignado"] or "—"),
                   ("Departamento", e["departamento"] or "—")]
    datos = Table([[_p(a, ESTILO_ETQ), _p(b, ESTILO_VAL)] for a, b in principales],
                  colWidths=[3.1 * cm, 6.9 * cm])
    datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINEA),
                               ("BACKGROUND", (1, 3), (1, 3),
                                colors.HexColor(ESTADO_BG.get(e["estado"], "#ffffff")))]))
    cabecera = Table([[img, datos]], colWidths=[6.8 * cm, 10.2 * cm])
    cabecera.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
                                  ("ALIGN", (0, 0), (0, 0), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    el.append(cabecera)

    # Especificaciones
    el.append(Paragraph("Especificaciones y datos de adquisición", ESTILO_H2))
    pares = [("Procesador", e["procesador"]), ("RAM", f"{e['ram_gb']} GB" if e["ram_gb"] else ""),
             ("Almacenamiento", e["almacenamiento"]), ("Sistema operativo", e["sistema_operativo"]),
             ("Dirección IP", e["direccion_ip"]), ("Dirección MAC", e["direccion_mac"]),
             ("Ubicación", e["ubicacion"]), ("Proveedor", e["proveedor"]),
             ("Fecha de compra", e["fecha_compra"]), ("Garantía hasta", e["garantia_hasta"]),
             ("Costo", f"S/ {e['costo']:,.2f}"), ("Registrado", e["fecha_registro"])]
    filas = [[_p(pares[i][0], ESTILO_ETQ), _p(pares[i][1] or "—", ESTILO_VAL),
              _p(pares[i + 1][0], ESTILO_ETQ), _p(pares[i + 1][1] or "—", ESTILO_VAL)]
             for i in range(0, len(pares), 2)]
    specs = Table(filas, colWidths=[3 * cm, 5.5 * cm, 3 * cm, 5.5 * cm])
    specs.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, LINEA),
                               ("BACKGROUND", (0, 0), (0, -1), ZEBRA), ("BACKGROUND", (2, 0), (2, -1), ZEBRA),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(specs)

    if e["observaciones"]:
        el += [Paragraph("Observaciones", ESTILO_H2), _p(e["observaciones"], ESTILO_VAL)]

    # Mantenimientos
    mants = db.obtener_mantenimientos(equipo_id, limite=20)
    el.append(Paragraph(f"Mantenimientos ({len(mants)})", ESTILO_H2))
    if mants:
        el.append(_tabla(["Fecha", "Tipo", "Descripción", "Técnico", "Costo S/", "Estado"],
                         [[m["fecha"], m["tipo"], m["descripcion"], m["tecnico"], f"{m['costo']:.2f}",
                           m["estado"]] for m in mants],
                         [a * cm for a in (2.1, 2.1, 6.6, 2.9, 1.5, 1.8)]))
    else:
        el.append(_p("Sin mantenimientos registrados.", ESTILO_SUB))

    # Historial
    hist = db.obtener_historial(equipo_id, limite=15)
    el.append(Paragraph("Últimos movimientos", ESTILO_H2))
    if hist:
        el.append(_tabla(["Fecha", "Acción", "Detalle"],
                         [[h["fecha"], h["accion"], h["detalle"]] for h in hist],
                         [a * cm for a in (3.2, 2.4, 11.4)]))
    else:
        el.append(_p("Sin movimientos registrados.", ESTILO_SUB))

    # Firmas
    firmas = Table([["_______________________", "_______________________"],
                    ["Usuario responsable", "Soporte TI"]], colWidths=[8.5 * cm, 8.5 * cm])
    firmas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("TEXTCOLOR", (0, 1), (-1, 1), GRIS)]))
    el.append(KeepTogether([Spacer(1, 40), firmas]))

    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return ruta
# ───────────────────────── Ficha individual ─────────────────────────
def generar_ficha_equipo(ruta, equipo_id):
    """PDF A4 con la ficha completa de un activo (imagen, specs, historial, firmas)."""
    e = db.obtener_equipo(equipo_id)
    if e is None:
        raise ValueError("El equipo no existe.")
    doc = _doc(ruta, A4, f"Ficha {e['codigo_activo']}", margen=2 * cm)

    el = [Paragraph(f"Ficha de activo · {escape(e['codigo_activo'])}", ESTILO_TITULO),
          _p(f"{e['nombre_equipo']} — emitida el {date.today():%d/%m/%Y}", ESTILO_SUB),
          Spacer(1, 10)]

    # Cabecera: imagen + datos principales
    img = _imagen(e["imagen_path"], 6.2 * cm, 4.6 * cm) or _p("Sin imagen registrada", ESTILO_VAL)
    principales = [("Tipo", e["tipo"]), ("Marca / Modelo", f"{e['marca']} {e['modelo']}"),
                   ("N.º de serie", e["num_serie"]), ("Estado", e["estado"]),
                   ("Usuario asignado", e["usuario_asignado"] or "—"),
                   ("Departamento", e["departamento"] or "—")]
    datos = Table([[_p(a, ESTILO_ETQ), _p(b, ESTILO_VAL)] for a, b in principales],
                  colWidths=[3.1 * cm, 6.9 * cm])
    datos.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINEA),
                               ("BACKGROUND", (1, 3), (1, 3),
                                colors.HexColor(ESTADO_BG.get(e["estado"], "#ffffff")))]))
    cabecera = Table([[img, datos]], colWidths=[6.8 * cm, 10.2 * cm])
    cabecera.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
                                  ("ALIGN", (0, 0), (0, 0), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    el.append(cabecera)

    # Especificaciones
    el.append(Paragraph("Especificaciones y datos de adquisición", ESTILO_H2))
    pares = [("Procesador", e["procesador"]), ("RAM", f"{e['ram_gb']} GB" if e["ram_gb"] else ""),
             ("Almacenamiento", e["almacenamiento"]), ("Sistema operativo", e["sistema_operativo"]),
             ("Dirección IP", e["direccion_ip"]), ("Dirección MAC", e["direccion_mac"]),
             ("Ubicación", e["ubicacion"]), ("Proveedor", e["proveedor"]),
             ("Fecha de compra", e["fecha_compra"]), ("Garantía hasta", e["garantia_hasta"]),
             ("Costo", f"S/ {e['costo']:,.2f}"), ("Registrado", e["fecha_registro"])]
    filas = [[_p(pares[i][0], ESTILO_ETQ), _p(pares[i][1] or "—", ESTILO_VAL),
              _p(pares[i + 1][0], ESTILO_ETQ), _p(pares[i + 1][1] or "—", ESTILO_VAL)]
             for i in range(0, len(pares), 2)]
    specs = Table(filas, colWidths=[3 * cm, 5.5 * cm, 3 * cm, 5.5 * cm])
    specs.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, LINEA),
                               ("BACKGROUND", (0, 0), (0, -1), ZEBRA), ("BACKGROUND", (2, 0), (2, -1), ZEBRA),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el.append(specs)

    if e["observaciones"]:
        el += [Paragraph("Observaciones", ESTILO_H2), _p(e["observaciones"], ESTILO_VAL)]

    # Mantenimientos
    mants = db.obtener_mantenimientos(equipo_id, limite=20)
    el.append(Paragraph(f"Mantenimientos ({len(mants)})", ESTILO_H2))
    if mants:
        el.append(_tabla(["Fecha", "Tipo", "Descripción", "Técnico", "Costo S/", "Estado"],
                         [[m["fecha"], m["tipo"], m["descripcion"], m["tecnico"], f"{m['costo']:.2f}",
                           m["estado"]] for m in mants],
                         [a * cm for a in (2.1, 2.1, 6.6, 2.9, 1.5, 1.8)]))
    else:
        el.append(_p("Sin mantenimientos registrados.", ESTILO_SUB))

    # Historial
    hist = db.obtener_historial(equipo_id, limite=15)
    el.append(Paragraph("Últimos movimientos", ESTILO_H2))
    if hist:
        el.append(_tabla(["Fecha", "Acción", "Detalle"],
                         [[h["fecha"], h["accion"], h["detalle"]] for h in hist],
                         [a * cm for a in (3.2, 2.4, 11.4)]))
    else:
        el.append(_p("Sin movimientos registrados.", ESTILO_SUB))

    # Firmas
    firmas = Table([["_______________________", "_______________________"],
                    ["Usuario responsable", "Soporte TI"]], colWidths=[8.5 * cm, 8.5 * cm])
    firmas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("TEXTCOLOR", (0, 1), (-1, 1), GRIS)]))
    el.append(KeepTogether([Spacer(1, 40), firmas]))

    doc.build(el, onFirstPage=_pie, onLaterPages=_pie)
    return ruta