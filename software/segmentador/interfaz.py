"""Ventana del Segmentador de Clientes (Tkinter).

A la izquierda la tabla de clientes con búsqueda y filtros, y el formulario para
agregar, editar o eliminar. A la derecha la gráfica, que se vuelve a dibujar sola
con cada cambio, y el panel para recalcular los grupos con K-means. La ventana no
valida nada por su cuenta: todo pasa por segmentador.datos, que es la única regla.
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from . import NOMBRE, VERSION, graficas
from .datos import Almacen, ErrorValidacion
from .formato import numero
from .modelo import K_DEFECTO, K_MAXIMO, K_MINIMO

ROJO = "#A4262C"
GRIS = "#5f5e5a"
TODOS = "Todos"
# Campo del formulario -> (etiqueta, ancho, fila, columna)
CAMPOS = {
    "cliente": ("Código *", 9, 0, 0),
    "pais": ("País *", 13, 0, 1),
    "recencia_dias": ("Recencia (días) *", 9, 0, 2),
    "frecuencia": ("Frecuencia *", 9, 0, 3),
    "valor_total": ("Valor total (£) *", 9, 2, 0),
    "unidades": ("Unidades", 9, 2, 1),
    "productos_distintos": ("Productos", 9, 2, 2),
    "devoluciones": ("Devoluciones", 9, 2, 3),
}
# Columna de la tabla -> (encabezado, ancho, alineación)
COLUMNAS_TABLA = {
    "cliente": ("Cliente", 56, "w"),
    "pais": ("País", 114, "w"),
    "recencia_dias": ("Recencia", 64, "e"),
    "frecuencia": ("Frecuencia", 72, "e"),
    "valor_total": ("Valor (£)", 84, "e"),
    "grupo": ("Grupo", 46, "center"),
    "estado": ("Estado", 62, "w"),
}


def modo_claro(ventana):
    """En macOS con modo oscuro, Tk pinta la ventana oscura; se fija la apariencia clara para que se vea
    igual que en Windows y los textos grises se lean."""
    if ventana.tk.call("tk", "windowingsystem") == "aqua":
        ventana.update_idletasks()  # Tk exige la ventana creada antes de cambiar la apariencia
        try:
            ventana.tk.call("::tk::unsupported::MacWindowStyle", "appearance", ventana, "aqua")
        except tk.TclError:
            pass


class Aplicacion(ttk.Frame):
    def __init__(self, raiz, almacen):
        super().__init__(raiz, padding=8)
        self.raiz = raiz
        self.almacen = almacen
        self.campos = {c: tk.StringVar() for c in CAMPOS}
        self.buscar = tk.StringVar()
        self.filtro_grupo = tk.StringVar(value=TODOS)
        self.filtro_estado = tk.StringVar(value=TODOS)
        self.tipo = tk.StringVar(value=graficas.TIPOS["grupos"][0])
        self.k = tk.StringVar(value=str(almacen.modelo.k))
        self.seleccion = None      # código del cliente que se está editando
        self.grupos_por_etiqueta = {}
        self.orden = ("cliente", False)

        raiz.title(f"{NOMBRE} {VERSION}")
        modo_claro(raiz)
        ancho = min(1260, raiz.winfo_screenwidth() - 20)
        alto = min(800, raiz.winfo_screenheight() - 60)
        raiz.geometry(f"{ancho}x{alto}")
        raiz.minsize(1100, 700)
        self.grid(sticky="nsew")
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._panel_izquierdo().grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        self._panel_derecho().grid(row=0, column=1, sticky="nsew")
        self.barra_estado = ttk.Label(self, anchor="w", foreground=GRIS)
        self.barra_estado.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        raiz.bind("<Control-z>", lambda e: self.deshacer())
        raiz.bind("<Command-z>", lambda e: self.deshacer())
        self.refrescar(f"Datos guardados en {almacen.ruta}")

    # ---------- construcción ----------

    def _panel_izquierdo(self):
        panel = ttk.Frame(self)
        panel.rowconfigure(0, weight=1)

        lista = ttk.LabelFrame(panel, text="Clientes", padding=6)
        lista.grid(row=0, column=0, sticky="nsew")
        lista.columnconfigure(0, weight=1)
        lista.rowconfigure(2, weight=1)
        filtros = ttk.Frame(lista)
        filtros.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(filtros, text="Buscar (código o país)").grid(row=0, column=0, sticky="w")
        ttk.Label(filtros, text="Grupo").grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Label(filtros, text="Estado").grid(row=0, column=2, sticky="w", padx=(6, 0))
        e_buscar = ttk.Entry(filtros, textvariable=self.buscar, width=14)
        e_buscar.grid(row=1, column=0, sticky="ew")
        e_buscar.bind("<KeyRelease>", lambda e: self.llenar_tabla())
        self.c_grupo = ttk.Combobox(filtros, textvariable=self.filtro_grupo, state="readonly", width=19)
        self.c_grupo.grid(row=1, column=1, padx=(6, 0))
        self.c_grupo.bind("<<ComboboxSelected>>", lambda e: self.llenar_tabla())
        c_estado = ttk.Combobox(filtros, textvariable=self.filtro_estado, state="readonly", width=8,
                                values=(TODOS, "Activo", "Inactivo"))
        c_estado.grid(row=1, column=2, padx=(6, 0))
        c_estado.bind("<<ComboboxSelected>>", lambda e: self.llenar_tabla())
        filtros.columnconfigure(0, weight=1)

        self.conteo = ttk.Label(lista, foreground=GRIS)
        self.conteo.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 2))
        self.arbol = ttk.Treeview(lista, columns=tuple(COLUMNAS_TABLA), show="headings", height=11,
                                  selectmode="browse")
        for col, (texto, ancho, ali) in COLUMNAS_TABLA.items():
            self.arbol.heading(col, text=texto, command=lambda c=col: self.ordenar(c))
            self.arbol.column(col, width=ancho, anchor=ali, stretch=col == "pais")
        self.arbol.grid(row=2, column=0, sticky="nsew")
        barra = ttk.Scrollbar(lista, orient="vertical", command=self.arbol.yview)
        barra.grid(row=2, column=1, sticky="ns")
        self.arbol.configure(yscrollcommand=barra.set)
        self.arbol.bind("<<TreeviewSelect>>", self._al_seleccionar)

        form = ttk.LabelFrame(panel, text="Agregar o editar cliente", padding=6)
        form.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.entradas = {}
        for campo, (texto, ancho, fila, col) in CAMPOS.items():
            ttk.Label(form, text=texto).grid(row=fila, column=col, sticky="w", padx=(0, 6))
            if campo == "pais":
                entrada = ttk.Combobox(form, textvariable=self.campos[campo], width=ancho)
            else:
                entrada = ttk.Entry(form, textvariable=self.campos[campo], width=ancho)
            entrada.grid(row=fila + 1, column=col, sticky="ew", padx=(0, 6), pady=(0, 4))
            entrada.bind("<Return>", lambda e: self.guardar())
            self.entradas[campo] = entrada
        ayuda = ("* obligatorio. El valor acepta coma o punto decimal. Estado, mercado y grupo se calculan "
                 "solos; el grupo lo asigna el modelo K-means vigente.")
        ttk.Label(form, text=ayuda, foreground=GRIS, wraplength=440).grid(row=4, column=0, columnspan=4, sticky="w")
        botones = ttk.Frame(form)
        botones.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        self.b_guardar = ttk.Button(botones, text="Agregar", command=self.guardar)
        self.b_guardar.pack(side="left")
        self.b_eliminar = ttk.Button(botones, text="Eliminar", command=self.eliminar, state="disabled")
        self.b_eliminar.pack(side="left", padx=6)
        ttk.Button(botones, text="Limpiar", command=self.limpiar_formulario).pack(side="left")
        self.aviso = ttk.Label(form, foreground=ROJO, wraplength=440)
        self.aviso.grid(row=6, column=0, columnspan=4, sticky="w", pady=(4, 0))

        acciones = ttk.LabelFrame(panel, text="Datos", padding=6)
        acciones.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        for i, (texto, accion) in enumerate((("Deshacer", self.deshacer),
                                             ("Restaurar originales", self.restaurar),
                                             ("Ver bitácora", self.ver_bitacora),
                                             ("Importar CSV", self.importar),
                                             ("Exportar CSV", self.exportar_csv))):
            boton = ttk.Button(acciones, text=texto, command=accion)
            boton.grid(row=i // 3, column=i % 3, sticky="ew", padx=2, pady=2)
        acciones.columnconfigure((0, 1, 2), weight=1)
        return panel

    def _panel_derecho(self):
        panel = ttk.Frame(self)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        selector = ttk.Frame(panel)
        selector.grid(row=0, column=0, sticky="ew")
        ttk.Label(selector, text="Gráfica:").pack(side="left", padx=(0, 6))
        c_tipo = ttk.Combobox(selector, textvariable=self.tipo, state="readonly", width=28,
                              values=[nombre for nombre, _ in graficas.TIPOS.values()])
        c_tipo.pack(side="left")
        c_tipo.bind("<<ComboboxSelected>>", lambda e: self.redibujar())
        ttk.Button(selector, text="Exportar gráfica (PNG o PDF)", command=self.exportar_grafica).pack(side="right")
        self.explicacion = ttk.Label(panel, foreground=GRIS, wraplength=700)
        self.explicacion.grid(row=1, column=0, sticky="w", pady=(4, 2))
        self.figura = Figure(figsize=(7.4, 4.2), dpi=100, facecolor="white")
        self.lienzo = FigureCanvasTkAgg(self.figura, master=panel)
        self.lienzo.get_tk_widget().grid(row=2, column=0, sticky="nsew")
        self.lienzo.mpl_connect("resize_event", lambda e: graficas.ubicar(self.figura, self.clave_tipo()))

        grupos = ttk.LabelFrame(panel, text="Grupos (K-means)", padding=6)
        grupos.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        grupos.columnconfigure(3, weight=1)
        ttk.Label(grupos, text=f"Número de grupos k ({K_MINIMO} a {K_MAXIMO}):").grid(row=0, column=0, sticky="w")
        self.s_k = ttk.Spinbox(grupos, from_=K_MINIMO, to=K_MAXIMO, textvariable=self.k, width=4)
        self.s_k.grid(row=0, column=1, padx=6)
        self.s_k.bind("<Return>", lambda e: self.recalcular())
        ttk.Button(grupos, text="Recalcular grupos (K-means)", command=self.recalcular).grid(row=0, column=2)
        self.metricas = ttk.Label(grupos, font=("", 0, "bold"))
        self.metricas.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        columnas = {"grupo": ("Grupo", 46, "center"), "nombre": ("Nombre", 158, "w"),
                    "clientes": ("Clientes", 62, "e"), "pct_clientes": ("% clientes", 74, "e"),
                    "pct_valor": ("% valor", 62, "e"), "recencia": ("Recencia", 74, "e"),
                    "frecuencia": ("Frecuencia", 76, "e"), "valor": ("Valor (£)", 82, "e")}
        self.perfil = ttk.Treeview(grupos, columns=tuple(columnas), show="headings", height=K_DEFECTO,
                                   selectmode="none")
        for col, (texto, ancho, ali) in columnas.items():
            self.perfil.heading(col, text=texto)
            self.perfil.column(col, width=ancho, anchor=ali, stretch=col == "nombre")
        self.perfil.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        nota = ("Recencia, frecuencia y valor son medianas del grupo. El modelo usa log(1 + x) de las tres, "
                "estandarizadas. Silueta: de -1 a 1, más alta es mejor; Davies-Bouldin: más bajo es mejor.")
        ttk.Label(grupos, text=nota, foreground=GRIS, wraplength=680).grid(row=3, column=0, columnspan=4,
                                                                           sticky="w", pady=(4, 0))
        return panel

    # ---------- refresco ----------

    def refrescar(self, mensaje=None):
        """Recarga filtros, tabla, gráfica y panel de grupos desde la base."""
        modelo = self.almacen.modelo
        self.grupos_por_etiqueta = {modelo.etiqueta(g): g for g in range(1, modelo.k + 1)}
        opciones = [TODOS] + list(self.grupos_por_etiqueta)
        self.c_grupo.configure(values=opciones)
        if self.filtro_grupo.get() not in opciones:
            self.filtro_grupo.set(TODOS)
        self.entradas["pais"].configure(values=self.almacen.paises())
        self.llenar_tabla()
        self.llenar_perfil()
        if self.seleccion and not self.almacen.cliente(self.seleccion):
            self.limpiar_formulario()
        self.redibujar()
        if mensaje:
            self.barra_estado.configure(text=mensaje)

    def llenar_tabla(self):
        estado = self.filtro_estado.get()
        filas = self.almacen.clientes(texto=self.buscar.get(),
                                      grupo=self.grupos_por_etiqueta.get(self.filtro_grupo.get()),
                                      estado=None if estado == TODOS else estado,
                                      orden=self.orden[0], descendente=self.orden[1])
        self.arbol.delete(*self.arbol.get_children())
        for f in filas:
            self.arbol.insert("", "end", iid=f["cliente"],
                              values=(f["cliente"], f["pais"], f["recencia_dias"], f["frecuencia"],
                                      numero(f["valor_total"], 2), f["grupo"], f["estado"]))
        self.conteo.configure(text=f"Mostrando {numero(len(filas))} de {numero(self.almacen.cantidad())} clientes. "
                                   "Los filtros no cambian las gráficas.")
        if self.seleccion and self.arbol.exists(self.seleccion):
            self.arbol.selection_set(self.seleccion)
            self.arbol.see(self.seleccion)

    def llenar_perfil(self):
        modelo = self.almacen.modelo
        self.perfil.delete(*self.perfil.get_children())
        for p in self.almacen.perfil():
            vacio = p["clientes"] == 0
            self.perfil.insert("", "end", values=(
                p["grupo"], p["nombre"], numero(p["clientes"]), f"{numero(p['pct_clientes'], 1)} %",
                f"{numero(p['pct_valor'], 1)} %",
                "" if vacio else f"{numero(p['recencia_mediana'])} días",
                "" if vacio else numero(p["frecuencia_mediana"], 1 if p["frecuencia_mediana"] % 1 else 0),
                "" if vacio else numero(p["valor_mediano"], 2)))
        self.perfil.configure(height=modelo.k)
        silueta = "sin dato" if modelo.silueta is None else numero(modelo.silueta, 3)
        db = "sin dato" if modelo.davies_bouldin is None else numero(modelo.davies_bouldin, 3)
        self.metricas.configure(text=f"Modelo vigente: k = {modelo.k} · silueta {silueta} · Davies-Bouldin {db}")
        self.k.set(str(modelo.k))

    def redibujar(self):
        tipo = self.clave_tipo()
        lectura = graficas.dibujar(self.figura, tipo, self.almacen.clientes(), self.almacen.modelo)
        self.lienzo.draw_idle()
        self.explicacion.configure(text=graficas.TIPOS[tipo][1])
        return lectura

    def clave_tipo(self):
        for clave, (nombre, _) in graficas.TIPOS.items():
            if nombre == self.tipo.get():
                return clave
        return "grupos"

    def poner_tipo(self, clave):
        self.tipo.set(graficas.TIPOS[clave][0])
        self.redibujar()

    # ---------- acciones ----------

    def _intentar(self, accion, exito):
        """Corre una escritura; si la base la rechaza, muestra el motivo sin cerrar nada."""
        try:
            resultado = accion()
        except ErrorValidacion as e:
            self.aviso.configure(text=str(e))
            self.raiz.bell()
            return False
        self.aviso.configure(text="")
        self.refrescar(exito(resultado) if callable(exito) else exito)
        return True

    def _datos_formulario(self):
        return {c: v.get() for c, v in self.campos.items()}

    def guardar(self):
        datos = self._datos_formulario()
        etiqueta = self.almacen.modelo.etiqueta
        if self.seleccion:
            codigo = self.seleccion
            ok = self._intentar(lambda: self.almacen.actualizar(codigo, datos),
                                lambda f: f"Se actualizó el cliente {codigo}: {etiqueta(f['grupo'])}, "
                                          f"{f['estado'].lower()}.")
        else:
            ok = self._intentar(lambda: self.almacen.agregar(datos),
                                lambda f: f"Se agregó el cliente {f['cliente']} ({f['pais']}, {f['mercado']}): "
                                          f"quedó en {etiqueta(f['grupo'])}, {f['estado'].lower()}.")
        if ok:
            self.limpiar_formulario()

    def eliminar(self):
        if not self.seleccion:
            return
        codigo = self.seleccion
        if messagebox.askyesno("Eliminar", f"¿Eliminar el cliente {codigo}? Puede deshacerlo después.",
                               parent=self.raiz):
            if self._intentar(lambda: self.almacen.eliminar(codigo), f"Se eliminó el cliente {codigo}."):
                self.limpiar_formulario()

    def recalcular(self):
        self.raiz.configure(cursor="watch")
        self.barra_estado.configure(text="Calculando K-means con 20 inicios distintos...")
        self.raiz.update_idletasks()
        try:
            self._intentar(lambda: self.almacen.recalcular(self.k.get()),
                           lambda m: f"Se recalcularon los grupos con k = {m.k}: silueta {numero(m.silueta, 3)}, "
                                     f"Davies-Bouldin {numero(m.davies_bouldin, 3)}. Puede deshacerlo.")
        finally:
            self.raiz.configure(cursor="")

    def deshacer(self):
        hecho = self.almacen.deshacer()
        self.refrescar(f"Se deshizo: {hecho}" if hecho else "No hay cambios para deshacer.")

    def restaurar(self):
        if messagebox.askyesno("Restaurar", "¿Volver a los clientes y grupos originales del análisis? "
                               "Puede deshacerlo después.", parent=self.raiz):
            self.almacen.restaurar_originales()
            self.limpiar_formulario()
            self.refrescar("Se restauraron los clientes y los grupos originales del análisis.")

    def importar(self):
        ruta = filedialog.askopenfilename(parent=self.raiz, title="Importar CSV",
                                          filetypes=[("CSV", "*.csv"), ("Texto", "*.txt"), ("Todos", "*.*")])
        if ruta and not self._intentar(lambda: self.almacen.importar_csv(ruta),
                                       lambda n: f"Se importaron {numero(n)} clientes; los grupos los asignó "
                                                 "el modelo vigente."):
            messagebox.showerror("Importar CSV", self.aviso.cget("text"), parent=self.raiz)

    def exportar_csv(self):
        ruta = filedialog.asksaveasfilename(parent=self.raiz, title="Exportar CSV", defaultextension=".csv",
                                            initialfile="clientes_segmentados.csv", filetypes=[("CSV", "*.csv")])
        if ruta:
            self.almacen.exportar_csv(ruta)
            self.barra_estado.configure(text=f"Clientes exportados a {ruta}")

    def exportar_grafica(self):
        tipo = self.clave_tipo()
        ruta = filedialog.asksaveasfilename(parent=self.raiz, title="Exportar gráfica", defaultextension=".png",
                                            initialfile=f"grafica-{tipo}.png",
                                            filetypes=[("Imagen PNG", "*.png"), ("Documento PDF", "*.pdf")])
        if ruta:
            graficas.exportar(ruta, tipo, self.almacen.clientes(), self.almacen.modelo)
            self.barra_estado.configure(text=f"Gráfica guardada en {ruta}")

    def ordenar(self, columna):
        actual, descendente = self.orden
        self.orden = (columna, not descendente if columna == actual else False)
        self.llenar_tabla()

    def ver_bitacora(self):
        v = tk.Toplevel(self.raiz)
        v.title("Bitácora y trazabilidad")
        modo_claro(v)
        v.geometry("860x480")
        marco = ttk.Frame(v, padding=10)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Fuente de los datos", font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(marco, text=self.almacen.fuente, wraplength=820, justify="left").pack(anchor="w", pady=(2, 8))
        cambios = self.almacen.diferencias_con_originales()
        ttk.Label(marco, text="Diferencias con los datos originales del análisis",
                  font=("", 12, "bold")).pack(anchor="w")
        texto = "\n".join(cambios) if cambios else "Ninguna: los clientes y los grupos son los del análisis."
        ttk.Label(marco, wraplength=820, justify="left", text=texto).pack(anchor="w", pady=(2, 8))
        ttk.Label(marco, text="Historial de cambios", font=("", 12, "bold")).pack(anchor="w")
        arbol = ttk.Treeview(marco, columns=("fecha", "accion", "detalle"), show="headings")
        for col, texto, ancho in (("fecha", "Fecha", 140), ("accion", "Acción", 150), ("detalle", "Detalle", 540)):
            arbol.heading(col, text=texto)
            arbol.column(col, width=ancho, anchor="w", stretch=col == "detalle")
        for f in self.almacen.bitacora():
            arbol.insert("", "end", values=(f["fecha"], f["accion"] + (" (deshecho)" if f["deshecho"] else ""),
                                            f["detalle"]))
        arbol.pack(fill="both", expand=True)
        return v

    def _al_seleccionar(self, _evento=None):
        sel = self.arbol.selection()
        if not sel or sel[0] == self.seleccion:
            return
        cliente = self.almacen.cliente(sel[0])
        if not cliente:
            return
        self.seleccion = cliente["cliente"]
        for campo, variable in self.campos.items():
            valor = cliente[campo]
            variable.set(numero(valor, 2).replace(".", "") if campo == "valor_total" else str(valor))
        self.entradas["cliente"].configure(state="disabled")
        self.b_guardar.configure(text="Guardar cambios")
        self.b_eliminar.configure(state="normal")
        self.aviso.configure(text="")

    def limpiar_formulario(self):
        self.seleccion = None
        for variable in self.campos.values():
            variable.set("")
        self.entradas["cliente"].configure(state="normal")
        self.b_guardar.configure(text="Agregar")
        self.b_eliminar.configure(state="disabled")
        if self.arbol.selection():
            self.arbol.selection_remove(self.arbol.selection())
        self.entradas["cliente"].focus_set()


def abrir(ruta_datos=None):
    """Punto de entrada de la ventana."""
    raiz = tk.Tk()
    almacen = Almacen(ruta_datos)
    Aplicacion(raiz, almacen)
    raiz.protocol("WM_DELETE_WINDOW", lambda: (almacen.cerrar(), raiz.destroy()))
    raiz.mainloop()
