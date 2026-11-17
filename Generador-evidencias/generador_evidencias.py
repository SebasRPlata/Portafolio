"""Generador automático de evidencias PDF.

by Sebastian Taype - Todos los derechos reservados.

Lee una factura electrónica (PDF de SUNAT), extrae N° de factura, trabajo
realizado y sede, y genera un PDF A4 con el encabezado de la empresa y las
fotos de evidencia (2 por página).

Requisitos:  pip install pypdf reportlab pillow
Uso:         python generador_evidencias.py
Logo:        coloca "logo.png" en la misma carpeta (opcional).
"""

from __future__ import annotations

import io
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from xml.sax.saxutils import escape

from PIL import Image, ImageOps, ImageTk
from pypdf import PdfReader
from reportlab.lib.colors import HexColor, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

# ============================== CONFIGURACIÓN ===============================
EMPRESA = {
    "nombre": "SERVICIOS GENERALES RIVAS PLATA S.A.C.S.",
    "ruc": "20616734696",
    "direccion": "Cal. Mar de las Antillas Mza. C Lote. 22 Asc. El Porvenir de Vitarte "
                 "(frente al parque Porvenir), Lima - Lima - Ate",
    "telefono": "935-683-942",
    "correos": "sgrivasplatasacs@gmail.com / sjr65066@gmail.com",
}
RUTA_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")

# --- Diseño del PDF (puntos; A4 = 595 x 842) ---
ANCHO, ALTO = A4
MARGEN = 56
ANCHO_UTIL = ANCHO - 2 * MARGEN
LOGO_TAMANO = 80
TEXTO_X = MARGEN + LOGO_TAMANO + 14
TEXTO_ANCHO = ANCHO - MARGEN - TEXTO_X
FOTOS_POR_PAGINA = 2
FOTO_ANCHO_MAX, FOTO_ALTO_MAX = 190, 320
LADO_MAX_PX = 1600
CALIDAD_JPEG = 85
COLOR_LINEA = HexColor("#B9A98B")
COLOR_PIE = HexColor("#555555")

ESTILO_EMPRESA = ParagraphStyle("empresa", fontName="Helvetica-Bold", fontSize=13, leading=16)
ESTILO_CONTACTO = ParagraphStyle("contacto", fontName="Helvetica", fontSize=8.5, leading=11.5,
                                 textColor=HexColor("#333333"))
ESTILO_DATO = ParagraphStyle("dato", fontName="Helvetica", fontSize=10.5, leading=15.5)


# ============================ EXTRACCIÓN DE DATOS ===========================
_FIN = r"(?=Valor de Venta|ICBPER|Sub Total|SON:|$)"
_RE_FACTURA = re.compile(r"\b([EF]\d{3}-\d+)\b")
_RE_TABLA = re.compile(
    r"(?:UNIDAD|Descripción)[\s\S]*?\d+\.\d{2}\s+(?:UNIDAD|SERV|GLOBAL)?\s*([\s\S]*?)" + _FIN,
    re.IGNORECASE)
_RE_SERVICIO = re.compile(r"(SERVICIO[\s\S]*?)" + _FIN, re.IGNORECASE)
_RE_IMPORTES_FINALES = re.compile(r"(?:\s+\d+(?:[.,]\d+)?)+\s*$")
_RE_SEDE_FINAL = re.compile(
    r"\s*[-–—]?\s*SEDE\s+([A-ZÁÉÍÓÚÑ]+(?: [A-ZÁÉÍÓÚÑ]+){0,3})\s*$", re.IGNORECASE)


def _normalizar(texto: str) -> str:
    return " ".join(texto.split())


def _a_oracion(texto: str) -> str:
    """Si el texto viene en MAYÚSCULAS lo pasa a minúsculas con la 1.ª letra en mayúscula."""
    letras = [ch for ch in texto if ch.isalpha()]
    if letras and sum(ch.isupper() for ch in letras) / len(letras) > 0.7:
        texto = texto.lower()
    return texto[:1].upper() + texto[1:]


def limpiar_descripcion(texto: str) -> tuple[str, str]:
    """Deja la descripción limpia y separa la sede.

    Quita los importes del final ("350.00 0.00") y el sufijo "- SEDE XXXX".
    Devuelve (trabajo, sede); la sede es "" si no aparece.
    """
    texto = _normalizar(texto)
    texto = _RE_IMPORTES_FINALES.sub("", texto)
    sede = ""
    m = _RE_SEDE_FINAL.search(texto)
    if m:
        sede = m.group(1).strip().title()
        texto = texto[:m.start()]
    texto = texto.rstrip(" -–—,;")
    return _a_oracion(texto), sede


def _descripcion_por_lineas(texto: str) -> str:
    capturadas, capturando = [], False
    for linea in texto.splitlines():
        mayus = linea.upper()
        if not capturando:
            capturando = "UNIDAD" in mayus
            continue
        if any(m in mayus for m in ("VALOR DE VENTA", "ICBPER", "SON:")):
            break
        if linea.strip():
            capturadas.append(linea.strip())
    return _normalizar(" ".join(capturadas))


def _buscar(patron: re.Pattern, texto: str) -> str:
    m = patron.search(texto)
    return _normalizar(m.group(1)) if m else ""


def parsear_texto(texto: str) -> tuple[str, str, str]:
    """Devuelve (factura, trabajo, sede) a partir del texto de la factura."""
    m = _RE_FACTURA.search(texto)
    factura = m.group(1) if m else ""

    bruto = ""
    for obtener in (lambda t: _buscar(_RE_TABLA, t), _descripcion_por_lineas,
                    lambda t: _buscar(_RE_SERVICIO, t)):
        bruto = obtener(texto)
        if len(bruto) >= 5:
            break

    trabajo, sede = limpiar_descripcion(bruto)
    return factura, trabajo, sede or "Lima"


def extraer_datos(ruta_pdf: str) -> tuple[str, str, str]:
    lector = PdfReader(ruta_pdf)
    texto = "\n".join((p.extract_text() or "") for p in lector.pages)
    return parsear_texto(texto)


# ============================== GENERACIÓN PDF ==============================
def _parrafo(c, texto, estilo, x, y_superior, ancho) -> float:
    """Dibuja un párrafo desde y_superior y devuelve la Y de su borde inferior."""
    p = Paragraph(texto, estilo)
    _, alto = p.wrap(ancho, ALTO)
    p.drawOn(c, x, y_superior - alto)
    return y_superior - alto


def _encabezado(c, factura: str, trabajo: str, sede: str) -> float:
    y_tope = ALTO - MARGEN
    if os.path.exists(RUTA_LOGO):
        c.drawImage(RUTA_LOGO, MARGEN, y_tope - LOGO_TAMANO, width=LOGO_TAMANO,
                    height=LOGO_TAMANO, preserveAspectRatio=True, anchor="c", mask="auto")

    y = _parrafo(c, escape(EMPRESA["nombre"]), ESTILO_EMPRESA, TEXTO_X, y_tope, TEXTO_ANCHO)
    for linea in (f"RUC: {EMPRESA['ruc']}", EMPRESA["direccion"],
                  f"Teléfono: {EMPRESA['telefono']}", EMPRESA["correos"]):
        y = _parrafo(c, escape(linea), ESTILO_CONTACTO, TEXTO_X, y, TEXTO_ANCHO)

    y_linea = min(y, y_tope - LOGO_TAMANO) - 10
    c.setStrokeColor(COLOR_LINEA)
    c.setLineWidth(0.8)
    c.line(MARGEN, y_linea, ANCHO - MARGEN, y_linea)

    y = y_linea - 14
    for etiqueta, valor in (("Factura N°:", factura), ("Trabajo Realizado:", trabajo),
                            ("Sede:", sede)):
        y = _parrafo(c, f"<b>{etiqueta}</b> {escape(valor)}", ESTILO_DATO, MARGEN, y, ANCHO_UTIL)
    return y


def _foto(c, ruta: str, columna: int, y_superior: float) -> None:
    with Image.open(ruta) as original:
        img = ImageOps.exif_transpose(original).convert("RGB")  # corrige rotación del celular
    img.thumbnail((LADO_MAX_PX, LADO_MAX_PX))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    buffer.seek(0)

    escala = min(FOTO_ANCHO_MAX / img.width, FOTO_ALTO_MAX / img.height)
    ancho, alto = img.width * escala, img.height * escala
    ancho_col = ANCHO_UTIL / FOTOS_POR_PAGINA
    centro_x = MARGEN + ancho_col * columna + ancho_col / 2
    c.drawImage(ImageReader(buffer), centro_x - ancho / 2, y_superior - alto,
                width=ancho, height=alto)


def generar_pdf(ruta_salida: str, factura: str, trabajo: str, sede: str, imagenes: list[str]) -> None:
    if not imagenes:
        raise ValueError("Se necesita al menos una imagen de evidencia.")

    total = -(-len(imagenes) // FOTOS_POR_PAGINA)
    c = canvas.Canvas(ruta_salida, pagesize=A4)
    c.setTitle(f"Evidencias - Factura {factura}")
    c.setAuthor(EMPRESA["nombre"])

    for pagina in range(total):
        y_fotos = _encabezado(c, factura, trabajo, sede) - 18 if pagina == 0 else ALTO - MARGEN
        lote = imagenes[pagina * FOTOS_POR_PAGINA:(pagina + 1) * FOTOS_POR_PAGINA]
        for columna, ruta in enumerate(lote):
            _foto(c, ruta, columna, y_fotos)

        c.setFont("Helvetica", 8)
        c.setFillColor(COLOR_PIE)
        c.drawCentredString(ANCHO / 2, 26, f"Página {pagina + 1} de {total}")
        c.setFillColor(black)
        c.showPage()
    c.save()


# ================================ INTERFAZ ==================================
COLOR_FONDO = "#F1F4F9"
COLOR_TARJETA = "#FFFFFF"
COLOR_BORDE = "#D8DEE9"
COLOR_HEADER = "#14213D"
COLOR_ACENTO = "#1E88E5"
COLOR_ACENTO_HOVER = "#1565C0"
COLOR_OK = "#2E7D32"
COLOR_TEXTO = "#1F2937"
COLOR_TEXTO_SUAVE = "#6B7280"
FUENTE = "Segoe UI"


def _boton(padre, texto, comando, primario=False, ancho=None):
    """Botón plano con efecto al pasar el mouse."""
    base = COLOR_ACENTO if primario else "#E8EDF5"
    hover = COLOR_ACENTO_HOVER if primario else "#D5DDEB"
    boton = tk.Button(
        padre, text=texto, command=comando, relief="flat", bd=0, cursor="hand2",
        bg=base, fg="white" if primario else COLOR_TEXTO,
        activebackground=hover, activeforeground="white" if primario else COLOR_TEXTO,
        font=(FUENTE, 10, "bold" if primario else "normal"), padx=14, pady=7, width=ancho)
    boton.bind("<Enter>", lambda _e: boton.config(bg=hover))
    boton.bind("<Leave>", lambda _e: boton.config(bg=base))
    return boton


MINIATURA_ANCHO, MINIATURA_ALTO = 84, 112


class GeneradorEvidenciasApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.rutas_imagenes: list[str] = []
        self.seleccion: int | None = None
        self._miniaturas: dict[str, ImageTk.PhotoImage] = {}

        root.title("Generador de Evidencias")
        root.geometry("780x720")
        root.minsize(680, 600)
        root.configure(bg=COLOR_FONDO)

        self._crear_encabezado()

        # Barra inferior (se empaqueta primero para que siempre quede visible)
        pie = tk.Frame(root, bg=COLOR_FONDO)
        pie.pack(side="bottom", fill="x", padx=24, pady=(4, 8))
        self.estado = tk.Label(pie, text="Listo. Empieza seleccionando la factura.",
                               bg=COLOR_FONDO, fg=COLOR_TEXTO_SUAVE, font=(FUENTE, 9), anchor="w")
        self.estado.pack(side="left")
        tk.Label(pie, text="by Sebastian Taype  ·  Todos los derechos reservados",
                 bg=COLOR_FONDO, fg=COLOR_TEXTO_SUAVE, font=(FUENTE, 8)).pack(side="right")
        self.btn_generar = _boton(root, "GENERAR PDF DE EVIDENCIAS", self.generar, primario=True)
        self.btn_generar.config(font=(FUENTE, 12, "bold"), pady=12)
        self.btn_generar.pack(side="bottom", fill="x", padx=24)

        cuerpo = tk.Frame(root, bg=COLOR_FONDO)
        cuerpo.pack(fill="both", expand=True, padx=24, pady=(12, 10))
        self._crear_tarjeta_factura(cuerpo)
        self._crear_tarjeta_fotos(cuerpo)
        self._refrescar_lista()

    # ---------- construcción de la interfaz ----------
    def _crear_encabezado(self) -> None:
        barra = tk.Frame(self.root, bg=COLOR_HEADER)
        barra.pack(fill="x")
        tk.Label(barra, text="Generador de Evidencias", bg=COLOR_HEADER, fg="white",
                 font=(FUENTE, 16, "bold")).pack(side="left", padx=24, pady=14)
        tk.Label(barra, text=EMPRESA["nombre"], bg=COLOR_HEADER, fg="#AEB8CC",
                 font=(FUENTE, 9)).pack(side="right", padx=24)

    def _tarjeta(self, padre, numero: str, titulo: str, expandir=False) -> tk.Frame:
        tarjeta = tk.Frame(padre, bg=COLOR_TARJETA, highlightbackground=COLOR_BORDE,
                           highlightthickness=1)
        tarjeta.pack(fill="both" if expandir else "x", expand=expandir, pady=(0, 10))
        cabecera = tk.Frame(tarjeta, bg=COLOR_TARJETA)
        cabecera.pack(fill="x", padx=16, pady=(10, 6))
        tk.Label(cabecera, text=numero, bg=COLOR_ACENTO, fg="white", width=2,
                 font=(FUENTE, 10, "bold")).pack(side="left")
        tk.Label(cabecera, text=titulo, bg=COLOR_TARJETA, fg=COLOR_TEXTO,
                 font=(FUENTE, 12, "bold")).pack(side="left", padx=10)
        interior = tk.Frame(tarjeta, bg=COLOR_TARJETA)
        interior.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return interior

    def _etiqueta(self, padre, texto: str, **pack) -> None:
        tk.Label(padre, text=texto, bg=COLOR_TARJETA, fg=COLOR_TEXTO_SUAVE,
                 font=(FUENTE, 9), anchor="w").pack(fill="x", pady=(6, 2), **pack)

    def _entrada(self, padre) -> tk.Entry:
        entrada = tk.Entry(padre, font=(FUENTE, 10), relief="flat", fg=COLOR_TEXTO,
                           highlightbackground=COLOR_BORDE, highlightcolor=COLOR_ACENTO,
                           highlightthickness=1, bd=0)
        entrada.pack(fill="x", ipady=5)
        return entrada

    def _crear_tarjeta_factura(self, padre) -> None:
        interior = self._tarjeta(padre, "1", "Factura electrónica")
        fila = tk.Frame(interior, bg=COLOR_TARJETA)
        fila.pack(fill="x")
        _boton(fila, "Seleccionar PDF…", self.cargar_pdf).pack(side="left")
        self.lbl_pdf = tk.Label(fila, text="Ningún archivo seleccionado", bg=COLOR_TARJETA,
                                fg=COLOR_TEXTO_SUAVE, font=(FUENTE, 9))
        self.lbl_pdf.pack(side="left", padx=12)

        # Factura y sede en la misma fila para ahorrar espacio
        fila = tk.Frame(interior, bg=COLOR_TARJETA)
        fila.pack(fill="x")
        izq = tk.Frame(fila, bg=COLOR_TARJETA)
        izq.pack(side="left", fill="x", expand=True, padx=(0, 8))
        der = tk.Frame(fila, bg=COLOR_TARJETA)
        der.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._etiqueta(izq, "Factura / Ref N°")
        self.ent_factura = self._entrada(izq)
        self._etiqueta(der, "Sede")
        self.ent_sede = self._entrada(der)

        self._etiqueta(interior, "Trabajo realizado (puedes editarlo)")
        self.txt_trabajo = tk.Text(
            interior, height=3, wrap="word", font=(FUENTE, 10), relief="flat", fg=COLOR_TEXTO,
            highlightbackground=COLOR_BORDE, highlightcolor=COLOR_ACENTO, highlightthickness=1,
            bd=0, padx=6, pady=5)
        self.txt_trabajo.pack(fill="x")

    def _crear_tarjeta_fotos(self, padre) -> None:
        interior = self._tarjeta(padre, "2", "Fotos de evidencia", expandir=True)
        botones = tk.Frame(interior, bg=COLOR_TARJETA)
        botones.pack(fill="x")
        _boton(botones, "Agregar fotos…", self.agregar_imagenes).pack(side="left")
        _boton(botones, "Quitar", self.quitar_imagen).pack(side="left", padx=(8, 0))
        _boton(botones, "Limpiar", self.limpiar_imagenes).pack(side="left", padx=(8, 0))
        _boton(botones, "▶", lambda: self.mover(1), ancho=2).pack(side="right")
        _boton(botones, "◀", lambda: self.mover(-1), ancho=2).pack(side="right", padx=(0, 8))

        marco = tk.Frame(interior, bg="#F8FAFC", highlightbackground=COLOR_BORDE,
                         highlightthickness=1)
        marco.pack(fill="both", expand=True, pady=(8, 0))
        scroll = tk.Scrollbar(marco, orient="horizontal")
        scroll.pack(side="bottom", fill="x")
        self.lienzo = tk.Canvas(marco, bg="#F8FAFC", height=MINIATURA_ALTO + 56,
                                highlightthickness=0, xscrollcommand=scroll.set)
        self.lienzo.pack(side="top", fill="both", expand=True)
        scroll.config(command=self.lienzo.xview)

        self.tira = tk.Frame(self.lienzo, bg="#F8FAFC")
        self.lienzo.create_window((0, 0), window=self.tira, anchor="nw")
        self.tira.bind("<Configure>",
                       lambda _e: self.lienzo.configure(scrollregion=self.lienzo.bbox("all")))
        self.lienzo.bind("<MouseWheel>", self._rueda)

        self.lbl_img = tk.Label(interior, text="0 fotos", bg=COLOR_TARJETA,
                                fg=COLOR_TEXTO_SUAVE, font=(FUENTE, 9), anchor="w")
        self.lbl_img.pack(fill="x", pady=(6, 0))

    # ---------- utilidades ----------
    def _mensaje(self, texto: str, color: str = COLOR_TEXTO_SUAVE) -> None:
        self.estado.config(text=texto, fg=color)

    @staticmethod
    def _poner(entrada: tk.Entry, valor: str) -> None:
        entrada.delete(0, tk.END)
        entrada.insert(0, valor)

    def _rueda(self, evento) -> None:
        self.lienzo.xview_scroll(-1 if evento.delta > 0 else 1, "units")

    def _miniatura(self, ruta: str):
        """Crea (y guarda en caché) la miniatura de una foto, con la rotación corregida."""
        if ruta not in self._miniaturas:
            try:
                with Image.open(ruta) as original:
                    original.draft("RGB", (MINIATURA_ANCHO * 2, MINIATURA_ALTO * 2))
                    img = ImageOps.exif_transpose(original).convert("RGB")
                img.thumbnail((MINIATURA_ANCHO, MINIATURA_ALTO))
            except Exception:
                img = Image.new("RGB", (MINIATURA_ANCHO, MINIATURA_ALTO), "#CBD5E1")
            self._miniaturas[ruta] = ImageTk.PhotoImage(img)
        return self._miniaturas[ruta]

    def _seleccionar(self, indice: int) -> None:
        self.seleccion = indice
        self._refrescar_lista()

    def _refrescar_lista(self) -> None:
        for hijo in self.tira.winfo_children():
            hijo.destroy()

        total = len(self.rutas_imagenes)
        if total == 0:
            self.seleccion = None
            tk.Label(self.tira, text="Aún no hay fotos.\nPulsa «Agregar fotos…» para subirlas.",
                     bg="#F8FAFC", fg=COLOR_TEXTO_SUAVE, font=(FUENTE, 10), justify="left",
                     ).pack(padx=20, pady=(MINIATURA_ALTO // 2, 0))
        for i, ruta in enumerate(self.rutas_imagenes):
            elegido = i == self.seleccion
            tarjeta = tk.Frame(self.tira, bg="white", highlightthickness=2,
                               highlightbackground=COLOR_ACENTO if elegido else COLOR_BORDE)
            tarjeta.pack(side="left", padx=6, pady=8, anchor="n")
            marco_img = tk.Frame(tarjeta, bg="white", width=MINIATURA_ANCHO + 8,
                                 height=MINIATURA_ALTO + 8)
            marco_img.pack_propagate(False)
            marco_img.pack(padx=2, pady=2)
            tk.Label(marco_img, image=self._miniatura(ruta), bg="white").pack(expand=True)
            nombre = os.path.basename(ruta)
            nombre = nombre if len(nombre) <= 14 else nombre[:11] + "…"
            tk.Label(tarjeta, text=f"{i + 1}. {nombre}", bg="white", fg=COLOR_TEXTO,
                     font=(FUENTE, 8)).pack(pady=(0, 4))
            for widget in (tarjeta, marco_img, *tarjeta.winfo_children(), *marco_img.winfo_children()):
                widget.bind("<Button-1>", lambda _e, n=i: self._seleccionar(n))
                widget.bind("<MouseWheel>", self._rueda)

        paginas = -(-total // FOTOS_POR_PAGINA) if total else 0
        self.lbl_img.config(
            text=f"{total} foto(s)  ·  {paginas} página(s) de evidencias"
                 + ("   ·   haz clic en una foto para seleccionarla y usa ◀ ▶ para ordenarla"
                    if total else ""),
            fg=COLOR_OK if total else COLOR_TEXTO_SUAVE)

    # ---------- acciones ----------
    def cargar_pdf(self) -> None:
        ruta = filedialog.askopenfilename(filetypes=[("Archivos PDF", "*.pdf")])
        if not ruta:
            return
        self.lbl_pdf.config(text=os.path.basename(ruta), fg=COLOR_OK)
        try:
            factura, trabajo, sede = extraer_datos(ruta)
        except Exception as error:
            messagebox.showwarning(
                "Aviso", f"No se pudo leer automáticamente el PDF:\n{error}\n\n"
                         "Completa los campos manualmente.")
            return
        self._poner(self.ent_factura, factura)
        self._poner(self.ent_sede, sede)
        self.txt_trabajo.delete("1.0", tk.END)
        self.txt_trabajo.insert("1.0", trabajo)
        self._mensaje("Datos de la factura cargados. Revísalos y agrega las fotos.", COLOR_OK)

    def agregar_imagenes(self) -> None:
        rutas = filedialog.askopenfilenames(filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        for ruta in rutas:
            if ruta not in self.rutas_imagenes:
                self.rutas_imagenes.append(ruta)
        self._refrescar_lista()

    def quitar_imagen(self) -> None:
        if self.seleccion is None:
            return
        del self.rutas_imagenes[self.seleccion]
        self.seleccion = min(self.seleccion, len(self.rutas_imagenes) - 1) if self.rutas_imagenes else None
        self._refrescar_lista()

    def limpiar_imagenes(self) -> None:
        self.rutas_imagenes.clear()
        self.seleccion = None
        self._refrescar_lista()

    def mover(self, delta: int) -> None:
        i = self.seleccion
        if i is None:
            return
        j = i + delta
        if 0 <= j < len(self.rutas_imagenes):
            self.rutas_imagenes[i], self.rutas_imagenes[j] = self.rutas_imagenes[j], self.rutas_imagenes[i]
            self.seleccion = j
            self._refrescar_lista()

    def generar(self) -> None:
        if not self.rutas_imagenes:
            messagebox.showerror("Error", "Agrega al menos una foto de evidencia.")
            return

        factura = self.ent_factura.get().strip() or "S/N"
        trabajo = _normalizar(self.txt_trabajo.get("1.0", tk.END)) or "Servicio General"
        sede = self.ent_sede.get().strip() or "Lima"

        ruta = filedialog.asksaveasfilename(
            defaultextension=".pdf", initialfile=f"EVIDENCIAS_FACTURA_{factura.split('-')[-1]}.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        try:
            generar_pdf(ruta, factura, trabajo, sede, self.rutas_imagenes)
        except Exception as error:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{error}")
            return

        self._mensaje(f"PDF generado: {ruta}", COLOR_OK)
        if messagebox.askyesno("¡Listo!", "PDF generado correctamente.\n\n¿Quieres abrirlo ahora?"):
            try:
                os.startfile(ruta)  # Windows
            except AttributeError:
                import subprocess, sys
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", ruta])


if __name__ == "__main__":
    ventana = tk.Tk()
    GeneradorEvidenciasApp(ventana)
    ventana.mainloop()