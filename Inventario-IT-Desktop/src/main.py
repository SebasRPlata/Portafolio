"""
main.py – Sistema de Control, Auditoría e Inventario de Equipos (IT Asset Management)
Interfaz con CustomTkinter: CRUD completo, imagen por dispositivo, búsqueda y filtros,
tarjetas de estadísticas, historial de auditoría, mantenimientos y exportación a CSV.

Ejecutar:  python src/main.py
Requiere:  pip install customtkinter pillow
"""
import csv
import webbrowser
import reportes
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps

import database as db

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

IMG_W, IMG_H = 300, 190
ESTADO_TAG = {"Operativo": "ok", "En Mantenimiento": "mant", "En Almacén": "alm", "Dado de baja": "baja"}

PALETAS = {
    "light": dict(fila="#ffffff", texto="#0f172a", cabecera="#1e293b", sel="#2563eb",
                  tags={"ok": "#ecfdf5", "mant": "#fffbeb", "alm": "#eff6ff", "baja": "#fef2f2"}),
    "dark": dict(fila="#1e293b", texto="#e2e8f0", cabecera="#0f172a", sel="#2563eb",
                 tags={"ok": "#14352b", "mant": "#3a2f10", "alm": "#14263f", "baja": "#3b1a1a"}),
}

# (clave, etiqueta, tipo de widget, valores)
CAMPOS_FORM = [
    ("codigo_activo", "Código de activo", "readonly", None),
    ("estado", "Estado *", "combo_ro", db.ESTADOS),
    ("nombre_equipo", "Nombre del equipo *", "entry", None),
    ("tipo", "Tipo *", "combo", db.TIPOS),
    ("marca", "Marca *", "entry", None),
    ("modelo", "Modelo *", "entry", None),
    ("num_serie", "N.º de serie *", "entry", None),
    ("proveedor", "Proveedor", "entry", None),
    ("procesador", "Procesador", "entry", None),
    ("ram_gb", "RAM (GB)", "entry", None),
    ("almacenamiento", "Almacenamiento", "entry", None),
    ("sistema_operativo", "Sistema operativo", "entry", None),
    ("direccion_ip", "Dirección IP", "entry", None),
    ("direccion_mac", "Dirección MAC", "entry", None),
    ("usuario_asignado", "Usuario asignado", "entry", None),
    ("departamento", "Departamento", "combo", db.DEPARTAMENTOS),
    ("ubicacion", "Ubicación", "entry", None),
    ("costo", "Costo (S/)", "entry", None),
    ("fecha_compra", "Compra (AAAA-MM-DD)", "entry", None),
    ("garantia_hasta", "Garantía (AAAA-MM-DD)", "entry", None),
]

COLUMNAS = [  # (id, título, ancho)
    ("codigo", "Código", 80), ("equipo", "Equipo", 95), ("tipo", "Tipo", 110),
    ("marca", "Marca / Modelo", 190), ("serie", "N.º Serie", 115), ("usuario", "Usuario", 160),
    ("depto", "Departamento", 120), ("estado", "Estado", 115), ("garantia", "Garantía", 75),
    ("img", "📷", 40),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Inventario IT · Control, Auditoría y Gestión de Activos")
        self.geometry("1360x820")
        self.minsize(1180, 720)

        db.inicializar_bd()

        self.modo = "light"
        self.id_actual = None          # equipo cargado en el formulario
        self.img_rel_actual = ""       # imagen guardada del equipo cargado
        self.img_pendiente = None      # imagen elegida, aún sin guardar
        self.img_quitar = False
        self.campos = {}
        self.orden = (None, False)
        self._ctk_img = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._construir_encabezado()
        self._construir_tarjetas()
        self._construir_cuerpo()
        self._aplicar_estilo_tabla()
        self.refrescar()
        self._nuevo()

    # ───────────────────────── Encabezado ─────────────────────────
    def _construir_encabezado(self):
        barra = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=0, height=68)
        barra.grid(row=0, column=0, sticky="ew")
        barra.grid_propagate(False)
        barra.grid_columnconfigure(1, weight=1)

        textos = ctk.CTkFrame(barra, fg_color="transparent")
        textos.grid(row=0, column=0, padx=22, pady=8, sticky="w")
        ctk.CTkLabel(textos, text="🖥️  Inventario IT", text_color="white",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(textos, text="Control, auditoría y gestión de activos tecnológicos",
                     text_color="#94a3b8", font=ctk.CTkFont(size=12)).pack(anchor="w")

        derecha = ctk.CTkFrame(barra, fg_color="transparent")
        derecha.grid(row=0, column=2, padx=22, sticky="e")
        self.sw_tema = ctk.CTkSwitch(derecha, text="Modo oscuro", text_color="white",
                                     command=self._cambiar_tema)
        self.sw_tema.pack(side="right", padx=(18, 0))
        try:  # logo opcional (assets/rivasplata.jpg)
            logo = Image.open(db.BASE_DIR / "assets" / "rivasplata.jpg")
            logo = ImageOps.contain(logo.convert("RGB"), (120, 46))
            self._logo = ctk.CTkImage(light_image=logo, dark_image=logo, size=logo.size)
            ctk.CTkLabel(derecha, image=self._logo, text="").pack(side="right")
        except Exception:
            pass

    # ───────────────────────── Tarjetas ─────────────────────────
    def _construir_tarjetas(self):
        fila = ctk.CTkFrame(self, fg_color="transparent")
        fila.grid(row=1, column=0, sticky="ew", padx=18, pady=(14, 6))
        self.lbl_stats, self.lbl_sub = {}, {}
        tarjetas = [
            ("total", "Total de activos", "#2563eb"),
            ("Operativo", "Operativos", "#16a34a"),
            ("En Mantenimiento", "En mantenimiento", "#d97706"),
            ("Dado de baja", "Dados de baja", "#dc2626"),
            ("vencidas", "Garantías vencidas", "#9333ea"),
            ("valor", "Valor del parque", "#0f766e"),
        ]
        for i, (clave, titulo, color) in enumerate(tarjetas):
            fila.grid_columnconfigure(i, weight=1, uniform="tarjeta")
            c = ctk.CTkFrame(fila, corner_radius=12, border_width=1, border_color=("#e2e8f0", "#334155"))
            c.grid(row=0, column=i, sticky="ew", padx=5)
            ctk.CTkLabel(c, text=titulo, font=ctk.CTkFont(size=12),
                         text_color=("#64748b", "#94a3b8")).pack(anchor="w", padx=14, pady=(10, 0))
            self.lbl_stats[clave] = ctk.CTkLabel(c, text="0", text_color=color,
                                                 font=ctk.CTkFont(size=26, weight="bold"))
            self.lbl_stats[clave].pack(anchor="w", padx=14)
            self.lbl_sub[clave] = ctk.CTkLabel(c, text=" ", font=ctk.CTkFont(size=11),
                                               text_color=("#94a3b8", "#64748b"))
            self.lbl_sub[clave].pack(anchor="w", padx=14, pady=(0, 8))

    def _actualizar_tarjetas(self):
        s = db.estadisticas()
        pe = s["por_estado"]
        self.lbl_stats["total"].configure(text=str(s["total"]))
        self.lbl_sub["total"].configure(text=f"{pe.get('En Almacén', 0)} en almacén")
        for est in ("Operativo", "En Mantenimiento", "Dado de baja"):
            self.lbl_stats[est].configure(text=str(pe.get(est, 0)))
        self.lbl_stats["vencidas"].configure(text=str(s["vencidas"]))
        self.lbl_sub["vencidas"].configure(text=f"{s['por_vencer']} vencen en 60 días")
        self.lbl_stats["valor"].configure(text=f"S/ {s['valor']:,.0f}")
        self.lbl_sub["valor"].configure(text="sin contar bajas")

    # ───────────────────────── Cuerpo ─────────────────────────
    def _construir_cuerpo(self):
        cuerpo = ctk.CTkFrame(self, fg_color="transparent")
        cuerpo.grid(row=2, column=0, sticky="nsew", padx=18, pady=(6, 16))
        cuerpo.grid_columnconfigure(0, weight=1)
        cuerpo.grid_columnconfigure(1, weight=0, minsize=470)
        cuerpo.grid_rowconfigure(0, weight=1)
        self._construir_panel_tabla(cuerpo)
        self._construir_panel_ficha(cuerpo)

    def _construir_panel_tabla(self, padre):
        panel = ctk.CTkFrame(padre, corner_radius=12)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        barra = ctk.CTkFrame(panel, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        barra.grid_columnconfigure(0, weight=1)

        self.var_busqueda = tk.StringVar()
        ctk.CTkEntry(barra, textvariable=self.var_busqueda, height=34,
                     placeholder_text="🔎  Buscar por código, serie, usuario, IP, departamento..."
                     ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.cb_tipo = ctk.CTkComboBox(barra, values=["Todos"], width=150, height=34,
                                       state="readonly", command=lambda _v: self.refrescar())
        self.cb_tipo.grid(row=0, column=1, padx=4)
        self.cb_tipo.set("Todos")
        self.cb_estado = ctk.CTkComboBox(barra, values=["Todos"] + db.ESTADOS, width=150, height=34,
                                         state="readonly", command=lambda _v: self.refrescar())
        self.cb_estado.grid(row=0, column=2, padx=4)
        self.cb_estado.set("Todos")
        ctk.CTkButton(barra, text="📄 PDF", width=70, height=34, fg_color="#7c3aed",
                      hover_color="#6d28d9", command=self._menu_reportes
                      ).grid(row=0, column=5, padx=(4, 0))
        ctk.CTkButton(barra, text="Limpiar", width=70, height=34, fg_color="#64748b",
                      hover_color="#475569", command=self._limpiar_filtros).grid(row=0, column=3, padx=4)
        ctk.CTkButton(barra, text="⬇ CSV", width=70, height=34, fg_color="#0f766e",
                      hover_color="#115e59", command=self._exportar_csv).grid(row=0, column=4, padx=(4, 0))
        self.var_busqueda.trace_add("write", lambda *_a: self.refrescar())

        marco = ctk.CTkFrame(panel, fg_color="transparent")
        marco.grid(row=1, column=0, sticky="nsew", padx=12)
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(marco, columns=[c[0] for c in COLUMNAS], show="headings",
                                 selectmode="browse")
        for cid, titulo, ancho in COLUMNAS:
            self.tree.heading(cid, text=titulo, command=lambda c=cid: self._ordenar(c))
            self.tree.column(cid, width=ancho, minwidth=40,
                             anchor="center" if cid in ("estado", "garantia", "img", "codigo", "equipo") else "w")
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.tree.yview)
        sx = ttk.Scrollbar(marco, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._al_seleccionar)

        self.lbl_conteo = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=12),
                                       text_color=("#64748b", "#94a3b8"))
        self.lbl_conteo.grid(row=2, column=0, sticky="w", padx=14, pady=(6, 10))

    def _construir_panel_ficha(self, padre):
        panel = ctk.CTkFrame(padre, corner_radius=12, width=470)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(panel, text="Ficha del activo", font=ctk.CTkFont(size=16, weight="bold")
                     ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 0))

        form = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        form.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        form.grid_columnconfigure((0, 1), weight=1, uniform="col")

        # Imagen del dispositivo
        self.lbl_img = ctk.CTkLabel(form, text="", corner_radius=8)
        self.lbl_img.grid(row=0, column=0, columnspan=2, pady=(4, 6))
        ctk.CTkButton(form, text="📁 Subir imagen", height=30, command=self._elegir_imagen
                      ).grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=(0, 10))
        ctk.CTkButton(form, text="🗑 Quitar imagen", height=30, fg_color="#64748b",
                      hover_color="#475569", command=self._quitar_imagen
                      ).grid(row=1, column=1, sticky="ew", padx=(4, 8), pady=(0, 10))

        fuente = ctk.CTkFont(size=11, weight="bold")
        fila = 2
        for i, (clave, etiqueta, tipo, valores) in enumerate(CAMPOS_FORM):
            r, c = fila + (i // 2) * 2, i % 2
            ctk.CTkLabel(form, text=etiqueta, font=fuente, anchor="w",
                         text_color=("#334155", "#cbd5e1")).grid(row=r, column=c, sticky="w",
                                                                  padx=10, pady=(4, 0))
            if tipo == "combo":
                w = ctk.CTkComboBox(form, values=valores, height=30)
            elif tipo == "combo_ro":
                w = ctk.CTkComboBox(form, values=valores, height=30, state="readonly")
            else:
                w = ctk.CTkEntry(form, height=30)
            w.grid(row=r + 1, column=c, sticky="ew", padx=(10 if c == 0 else 4, 4 if c == 0 else 10), pady=(0, 2))
            self.campos[clave] = w

        r_obs = fila + (len(CAMPOS_FORM) // 2) * 2
        ctk.CTkLabel(form, text="Observaciones", font=fuente, anchor="w",
                     text_color=("#334155", "#cbd5e1")).grid(row=r_obs, column=0, columnspan=2,
                                                              sticky="w", padx=10, pady=(6, 0))
        self.campos["observaciones"] = ctk.CTkTextbox(form, height=70, border_width=1)
        self.campos["observaciones"].grid(row=r_obs + 1, column=0, columnspan=2, sticky="ew",
                                          padx=10, pady=(0, 8))

        # Botones de acción (siempre visibles)
        acciones = ctk.CTkFrame(panel, fg_color="transparent")
        acciones.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        acciones.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="b")
        self.btn_nuevo = ctk.CTkButton(acciones, text="✚ Nuevo", fg_color="#64748b",
                                       hover_color="#475569", command=self._nuevo)
        self.btn_guardar = ctk.CTkButton(acciones, text="💾 Guardar", command=self._guardar)
        self.btn_actualizar = ctk.CTkButton(acciones, text="✏ Actualizar", fg_color="#16a34a",
                                            hover_color="#15803d", command=self._actualizar)
        self.btn_eliminar = ctk.CTkButton(acciones, text="🗑 Eliminar", fg_color="#dc2626",
                                          hover_color="#b91c1c", command=self._eliminar)
        for i, b in enumerate((self.btn_nuevo, self.btn_guardar, self.btn_actualizar, self.btn_eliminar)):
            b.grid(row=0, column=i, sticky="ew", padx=3, pady=3)
        self.btn_mant = ctk.CTkButton(acciones, text="🛠 Registrar mantenimiento", fg_color="#d97706",
                                      hover_color="#b45309", command=self._dialogo_mantenimiento)
        self.btn_mant.grid(row=1, column=0, columnspan=2, sticky="ew", padx=3, pady=3)
        ctk.CTkButton(acciones, text="📜 Historial", fg_color="#7c3aed", hover_color="#6d28d9",
                      command=self._ventana_historial).grid(row=1, column=2, columnspan=2,
                                                            sticky="ew", padx=3, pady=3)

    # ───────────────────────── Estilo de tabla ─────────────────────────
    def _aplicar_estilo_tabla(self):
        p = PALETAS[self.modo]
        e = ttk.Style(self)
        e.theme_use("clam")
        e.configure("Treeview", background=p["fila"], fieldbackground=p["fila"], foreground=p["texto"],
                    rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        e.configure("Treeview.Heading", background=p["cabecera"], foreground="#ffffff",
                    font=("Segoe UI", 10, "bold"), relief="flat", padding=6)
        e.map("Treeview.Heading", background=[("active", "#334155")])
        # Workaround: permite que los colores por etiqueta (tags) funcionen en Tk 8.6.9+
        fondo = [x for x in e.map("Treeview", query_opt="background") if x[:2] != ("!disabled", "!selected")]
        e.map("Treeview", background=fondo + [("selected", p["sel"])],
              foreground=[("selected", "#ffffff")])
        for tag, color in p["tags"].items():
            self.tree.tag_configure(tag, background=color)

    def _cambiar_tema(self):
        self.modo = "dark" if self.sw_tema.get() else "light"
        ctk.set_appearance_mode(self.modo)
        self._aplicar_estilo_tabla()

    # ───────────────────────── Tabla / filtros ─────────────────────────
    def refrescar(self):
        tipos = ["Todos"] + db.listar_tipos()
        self.cb_tipo.configure(values=tipos)
        if self.cb_tipo.get() not in tipos:
            self.cb_tipo.set("Todos")

        filas = db.obtener_equipos(self.var_busqueda.get(), self.cb_tipo.get(), self.cb_estado.get())
        hoy = date.today().isoformat()
        self.tree.delete(*self.tree.get_children())
        for f in filas:
            g = f["garantia_hasta"]
            garantia = "—" if not g else ("Vencida" if g < hoy else "Vigente")
            self.tree.insert("", "end", iid=str(f["id"]), tags=(ESTADO_TAG.get(f["estado"], "ok"),),
                             values=(f["codigo_activo"], f["nombre_equipo"], f["tipo"],
                                     f"{f['marca']} {f['modelo']}", f["num_serie"],
                                     f["usuario_asignado"], f["departamento"], f["estado"],
                                     garantia, "📷" if f["imagen_path"] else ""))
        self.lbl_conteo.configure(text=f"{len(filas)} activo(s) mostrado(s)")
        self._actualizar_tarjetas()
        if self.id_actual and self.tree.exists(str(self.id_actual)):
            self.tree.selection_set(str(self.id_actual))
            self.tree.see(str(self.id_actual))

    def _limpiar_filtros(self):
        self.cb_tipo.set("Todos")
        self.cb_estado.set("Todos")
        self.var_busqueda.set("")
        self.refrescar()

    def _ordenar(self, col):
        inverso = self.orden[0] == col and not self.orden[1]
        items = [(self.tree.set(k, col).lower(), k) for k in self.tree.get_children("")]
        items.sort(reverse=inverso)
        for i, (_v, k) in enumerate(items):
            self.tree.move(k, "", i)
        self.orden = (col, inverso)

    def _al_seleccionar(self, _evento=None):
        sel = self.tree.selection()
        if not sel or int(sel[0]) == self.id_actual:
            return
        self._cargar(int(sel[0]))

    def _exportar_csv(self):
        filas = db.obtener_equipos(self.var_busqueda.get(), self.cb_tipo.get(), self.cb_estado.get())
        if not filas:
            messagebox.showinfo("Exportar", "No hay equipos para exportar con los filtros actuales.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=f"inventario_{date.today():%Y%m%d}.csv")
        if not ruta:
            return
        claves = [k for k in filas[0].keys() if k != "imagen_path"]
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(claves)
            for r in filas:
                w.writerow([r[k] for k in claves])
        messagebox.showinfo("Exportar", f"Se exportaron {len(filas)} equipos a:\n{ruta}")

    # ───────────────────────── Formulario ─────────────────────────
    def _set(self, clave, valor):
        w = self.campos[clave]
        valor = "" if valor is None else str(valor)
        if isinstance(w, ctk.CTkTextbox):
            w.delete("1.0", "end")
            w.insert("1.0", valor)
        elif isinstance(w, ctk.CTkComboBox):
            w.set(valor)
        else:
            w.configure(state="normal")
            w.delete(0, "end")
            w.insert(0, valor)
            if clave == "codigo_activo":
                w.configure(state="disabled")

    def _get(self, clave):
        w = self.campos[clave]
        return w.get("1.0", "end-1c").strip() if isinstance(w, ctk.CTkTextbox) else w.get().strip()

    def _leer_form(self):
        return {clave: self._get(clave) for clave in self.campos}

    def _actualizar_botones(self):
        cargado = self.id_actual is not None
        self.btn_guardar.configure(state="disabled" if cargado else "normal")
        for b in (self.btn_actualizar, self.btn_eliminar, self.btn_mant):
            b.configure(state="normal" if cargado else "disabled")

    def _nuevo(self):
        self.id_actual = None
        for clave in self.campos:
            self._set(clave, "")
        self._set("estado", "Operativo")
        self._set("codigo_activo", db.siguiente_codigo())
        self.img_rel_actual, self.img_pendiente, self.img_quitar = "", None, False
        self._mostrar_imagen(None)
        self.tree.selection_remove(self.tree.selection())
        self._actualizar_botones()
        self.campos["nombre_equipo"].focus()

    def _cargar(self, equipo_id):
        fila = db.obtener_equipo(equipo_id)
        if fila is None:
            return
        self.id_actual = equipo_id
        for clave in self.campos:
            valor = fila[clave]
            if clave in ("ram_gb", "costo") and not valor:
                valor = ""
            elif clave == "costo":
                valor = f"{valor:.2f}"
            self._set(clave, valor)
        self.img_rel_actual = fila["imagen_path"] or ""
        self.img_pendiente, self.img_quitar = None, False
        self._mostrar_imagen(db.ruta_imagen(self.img_rel_actual))
        self._actualizar_botones()

    # ───────────────────────── Imagen ─────────────────────────
    def _placeholder(self):
        img = Image.new("RGB", (IMG_W, IMG_H), "#cbd5e1")
        d = ImageDraw.Draw(img)
        txt = "Sin imagen"
        x0, y0, x1, y1 = d.textbbox((0, 0), txt)
        d.text(((IMG_W - (x1 - x0)) // 2, (IMG_H - (y1 - y0)) // 2), txt, fill="#475569")
        return img

    def _mostrar_imagen(self, ruta):
        try:
            if ruta and Path(ruta).is_file():
                img = ImageOps.contain(Image.open(ruta).convert("RGB"), (IMG_W, IMG_H))
            else:
                img = self._placeholder()
        except Exception:
            img = self._placeholder()
        self._ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
        self.lbl_img.configure(image=self._ctk_img, text="")

    def _elegir_imagen(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar imagen del dispositivo",
            filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            with Image.open(ruta) as im:
                im.verify()
        except Exception:
            messagebox.showerror("Imagen", "El archivo seleccionado no es una imagen válida.")
            return
        self.img_pendiente, self.img_quitar = ruta, False
        self._mostrar_imagen(ruta)

    def _quitar_imagen(self):
        self.img_pendiente = None
        self.img_quitar = bool(self.img_rel_actual)
        self._mostrar_imagen(None)

    # ───────────────────────── CRUD ─────────────────────────
    def _guardar(self):
        datos = self._leer_form()
        error = db.validar(datos)
        if error:
            messagebox.showwarning("Datos incompletos", error)
            return
        codigo = db.siguiente_codigo()
        datos["codigo_activo"] = codigo
        nueva = None
        if self.img_pendiente:
            nueva = db.guardar_imagen(self.img_pendiente, codigo)
        datos["imagen_path"] = nueva or ""

        ok, msg, nuevo_id = db.crear_equipo(datos)
        if not ok:
            if nueva:
                db.borrar_imagen(nueva)
            messagebox.showerror("No se pudo guardar", msg)
            return
        self.id_actual = nuevo_id
        self.img_rel_actual, self.img_pendiente, self.img_quitar = nueva or "", None, False
        self.refrescar()
        self._cargar(nuevo_id)
        messagebox.showinfo("Éxito", msg)

    def _actualizar(self):
        if not self.id_actual:
            return
        datos = self._leer_form()
        error = db.validar(datos)
        if error:
            messagebox.showwarning("Datos incompletos", error)
            return
        vieja, nueva = self.img_rel_actual, None
        datos["imagen_path"] = vieja
        if self.img_pendiente:
            nueva = db.guardar_imagen(self.img_pendiente, datos["codigo_activo"] or "ACT")
            datos["imagen_path"] = nueva
        elif self.img_quitar:
            datos["imagen_path"] = ""

        ok, msg = db.actualizar_equipo(self.id_actual, datos)
        if not ok:
            if nueva:
                db.borrar_imagen(nueva)
            messagebox.showerror("No se pudo actualizar", msg)
            return
        if vieja and datos["imagen_path"] != vieja:
            db.borrar_imagen(vieja)
        self.refrescar()
        self._cargar(self.id_actual)
        messagebox.showinfo("Éxito", msg)

    def _eliminar(self):
        if not self.id_actual:
            return
        nombre = self._get("nombre_equipo")
        if not messagebox.askyesno("Confirmar eliminación",
                                   f"¿Eliminar definitivamente «{nombre}»?\n"
                                   "El registro en el historial se conservará."):
            return
        ok, msg = db.eliminar_equipo(self.id_actual)
        if not ok:
            messagebox.showerror("Error", msg)
            return
        self._nuevo()
        self.refrescar()
        messagebox.showinfo("Eliminado", msg)
    
    # ───────────────────────── Reportes PDF ─────────────────────────
    def _menu_reportes(self):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Reporte del inventario (filtros actuales)", command=self._pdf_inventario)
        menu.add_command(label="Reporte de garantías", command=self._pdf_garantias)
        menu.add_command(label="Ficha del activo seleccionado", command=self._pdf_ficha,
                         state="normal" if self.id_actual else "disabled")
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _generar_pdf(self, nombre, funcion):
        ruta = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                            initialfile=f"{nombre}_{date.today():%Y%m%d}.pdf")
        if not ruta:
            return
        try:
            funcion(ruta)
        except Exception as e:
            messagebox.showerror("Reporte PDF", f"No se pudo generar el PDF:\n{e}")
            return
        if messagebox.askyesno("Reporte PDF", "PDF generado correctamente.\n¿Quieres abrirlo ahora?"):
            webbrowser.open(Path(ruta).resolve().as_uri())

    def _pdf_inventario(self):
        filas = db.obtener_equipos(self.var_busqueda.get(), self.cb_tipo.get(), self.cb_estado.get())
        filtros = ", ".join(x for x in (
            f"texto «{self.var_busqueda.get()}»" if self.var_busqueda.get() else "",
            f"tipo {self.cb_tipo.get()}" if self.cb_tipo.get() != "Todos" else "",
            f"estado {self.cb_estado.get()}" if self.cb_estado.get() != "Todos" else "") if x)
        self._generar_pdf("inventario_it", lambda r: reportes.generar_reporte_inventario(r, filas, filtros))

    def _pdf_garantias(self):
        self._generar_pdf("garantias_it", reportes.generar_reporte_garantias)

    def _pdf_ficha(self):
        if self.id_actual:
            eq = self.id_actual
            self._generar_pdf(f"ficha_{self._get('codigo_activo')}",
                              lambda r: reportes.generar_ficha_equipo(r, eq))
    # ───────────────────────── Mantenimiento ─────────────────────────
    def _dialogo_mantenimiento(self):
        if not self.id_actual:
            return
        equipo_id = self.id_actual
        win = ctk.CTkToplevel(self)
        win.title("Registrar mantenimiento")
        win.geometry("460x470")
        win.resizable(False, False)
        win.transient(self)
        win.after(150, win.grab_set)

        ctk.CTkLabel(win, text=f"{self._get('codigo_activo')} · {self._get('nombre_equipo')}",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(padx=20, pady=(18, 8), anchor="w")

        def etiqueta(t):
            ctk.CTkLabel(win, text=t, font=ctk.CTkFont(size=11, weight="bold")).pack(padx=20, anchor="w")

        etiqueta("Tipo")
        cb_tipo = ctk.CTkComboBox(win, values=db.TIPOS_MANTENIMIENTO, state="readonly")
        cb_tipo.set("Preventivo")
        cb_tipo.pack(padx=20, pady=(0, 8), fill="x")
        etiqueta("Estado del trabajo (si queda «En proceso», el equipo pasa a «En Mantenimiento»)")
        cb_estado = ctk.CTkComboBox(win, values=db.ESTADOS_MANTENIMIENTO, state="readonly")
        cb_estado.set("Completado")
        cb_estado.pack(padx=20, pady=(0, 8), fill="x")
        etiqueta("Técnico")
        ent_tec = ctk.CTkEntry(win)
        ent_tec.pack(padx=20, pady=(0, 8), fill="x")
        etiqueta("Costo (S/)")
        ent_costo = ctk.CTkEntry(win, placeholder_text="0.00")
        ent_costo.pack(padx=20, pady=(0, 8), fill="x")
        etiqueta("Descripción del trabajo *")
        txt = ctk.CTkTextbox(win, height=90, border_width=1)
        txt.pack(padx=20, pady=(0, 12), fill="x")

        def guardar():
            ok, msg = db.registrar_mantenimiento(equipo_id, cb_tipo.get(), txt.get("1.0", "end-1c"),
                                                 ent_tec.get(), ent_costo.get() or 0, cb_estado.get())
            if not ok:
                messagebox.showwarning("Mantenimiento", msg, parent=win)
                return
            win.destroy()
            self.refrescar()
            self._cargar(equipo_id)
            messagebox.showinfo("Mantenimiento", msg)

        ctk.CTkButton(win, text="Guardar mantenimiento", fg_color="#d97706", hover_color="#b45309",
                      command=guardar).pack(padx=20, pady=4, fill="x")

    # ───────────────────────── Historial ─────────────────────────
    def _tabla_simple(self, padre, columnas):
        marco = ctk.CTkFrame(padre, fg_color="transparent")
        marco.pack(fill="both", expand=True)
        marco.grid_columnconfigure(0, weight=1)
        marco.grid_rowconfigure(0, weight=1)
        tree = ttk.Treeview(marco, columns=[c[0] for c in columnas], show="headings")
        for cid, titulo, ancho in columnas:
            tree.heading(cid, text=titulo)
            tree.column(cid, width=ancho, anchor="w")
        sb = ttk.Scrollbar(marco, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        return tree

    def _ventana_historial(self):
        eq_id = self.id_actual
        titulo = f"Historial · {self._get('codigo_activo')}" if eq_id else "Historial general de auditoría"
        win = ctk.CTkToplevel(self)
        win.title(titulo)
        win.geometry("1000x540")
        win.after(120, win.lift)

        ctk.CTkLabel(win, text=titulo, font=ctk.CTkFont(size=16, weight="bold")
                     ).pack(anchor="w", padx=18, pady=(14, 0))
        tabs = ctk.CTkTabview(win)
        tabs.pack(fill="both", expand=True, padx=14, pady=10)

        t1 = self._tabla_simple(tabs.add("Cambios y auditoría"), [
            ("fecha", "Fecha", 140), ("codigo", "Activo", 80), ("accion", "Acción", 100),
            ("detalle", "Detalle", 560), ("usuario", "Usuario SO", 100)])
        for h in db.obtener_historial(eq_id):
            t1.insert("", "end", values=(h["fecha"], h["codigo_activo"], h["accion"],
                                         h["detalle"], h["usuario_sistema"]))

        t2 = self._tabla_simple(tabs.add("Mantenimientos"), [
            ("fecha", "Fecha", 85), ("codigo", "Activo", 80), ("equipo", "Equipo", 100),
            ("tipo", "Tipo", 90), ("desc", "Descripción", 340), ("tec", "Técnico", 110),
            ("costo", "Costo S/", 70), ("estado", "Estado", 90)])
        for m in db.obtener_mantenimientos(eq_id):
            t2.insert("", "end", values=(m["fecha"], m["codigo_activo"], m["nombre_equipo"], m["tipo"],
                                         m["descripcion"], m["tecnico"], f"{m['costo']:.2f}", m["estado"]))


if __name__ == "__main__":
    App().mainloop()