"""GUI Qt6 (PySide6) para MSI Mystic Light MS-7D95. Tema oscuro minimalista.

Ejecutar sin sudo (el lanzador eleva solo conservando el display):
  ./msi-mystic --gui
"""
from __future__ import annotations

import colorsys
import json
import os
import subprocess
import sys
import threading
import time

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSlider, QCheckBox, QComboBox,
        QTextEdit, QColorDialog, QGridLayout, QMessageBox,
        QLineEdit, QFrame, QSizePolicy,
    )
    from PySide6.QtCore import Qt, Signal, QObject, Slot
    from PySide6.QtGui import QColor, QIcon, QPalette
except ImportError:
    print("ERROR: falta PySide6. Instala con: pip install PySide6", file=sys.stderr)
    sys.exit(1)

from .superio import SuperIO, detectar, es_root, info_placa, SuperIOError
from .controller import MSIRGB, ColorRGB


REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "msi-mystic")
COLORES_PATH = os.path.join(CONFIG_DIR, "colores.json")
MAX_PERSONALIZADOS = 6


def cargar_personalizados() -> list[str]:
    """Devuelve la lista de HEX guardados (0..6)."""
    try:
        with open(COLORES_PATH, "r", encoding="utf-8") as f:
            datos = f.read().strip()
        if not datos:
            return []
        lista = json.loads(datos)
        limpios = []
        for h in lista[:MAX_PERSONALIZADOS]:
            try:
                limpios.append(ColorRGB.desde_hex(str(h)).a_hex())
            except ValueError:
                continue
        return limpios
    except (OSError, ValueError):
        return []


def guardar_personalizados(colores: list[str]):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = COLORES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(colores[:MAX_PERSONALIZADOS], f)
    os.replace(tmp, COLORES_PATH)

PRESETS = [
    ("Rojo", "FF0000"), ("Naranja", "FF7700"), ("Amarillo", "FFFF00"),
    ("Verde", "00FF00"), ("Cian", "00FFFF"), ("Azul", "0077FF"),
    ("Violeta", "8B7BFF"), ("Magenta", "FF00FF"), ("Blanco", "FFFFFF"),
]

# -- tema negro puro + acento verde --
FONDO = "#000000"
TARJETA = "#0b0b0d"
BORDE = "#1e1e23"
TEXTO = "#f2f2f4"
APAGADO = "#8a8a93"
ACENTO = "#00e676"
ACENTO2 = "#00e676"
PELIGRO = "#ff5f6b"

QSS = f"""
* {{ font-size: 13px; }}
QMainWindow, QWidget#central {{ background: {FONDO}; }}
QLabel {{ color: {TEXTO}; background: transparent; }}
QLabel#titulo {{ font-size: 16px; font-weight: 700; }}
QLabel#sub {{ color: {APAGADO}; font-size: 12px; }}
QLabel#seccion {{ color: {APAGADO}; font-size: 11px; font-weight: 700;
  letter-spacing: 1px; }}
QFrame#tarjeta {{ background: {TARJETA}; border: 1px solid {BORDE};
  border-radius: 14px; }}
QLabel#vista {{
  border-radius: 60px;
  border: 2px solid {BORDE};
}}
QLineEdit, QComboBox, QTextEdit {{
  background: #131315; color: {TEXTO};
  border: 1px solid {BORDE}; border-radius: 9px; padding: 7px 10px;
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACENTO}; }}
QPushButton {{
  color: {TEXTO}; background: #141416;
  border: 1px solid {BORDE}; border-radius: 10px; padding: 9px 14px;
}}
QPushButton:hover {{ border: 1px solid {ACENTO}; }}
QPushButton#primario {{
  background: {ACENTO}; border: 1px solid {ACENTO};
  color: #03130a; font-weight: 700;
}}
QPushButton#primario:hover {{ background: #33f08a; }}
QPushButton#peligro {{ color: {PELIGRO}; }}
QPushButton#dot {{
  border-radius: 15px; padding: 0px; min-width: 30px; max-width: 30px;
  min-height: 30px; max-height: 30px; border: 2px solid {BORDE};
}}
QPushButton#dot:hover {{ border: 2px solid white; }}
QPushButton#mini {{
  background: transparent; border: none; color: {APAGADO}; padding: 4px;
}}
QPushButton#mini:hover {{ color: {TEXTO}; }}
QCheckBox {{ color: {TEXTO}; spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px;
  border: 1px solid {BORDE}; background: #131315; }}
QCheckBox::indicator:checked {{ background: {ACENTO}; border: 1px solid {ACENTO}; }}
QSlider::groove:horizontal {{ height: 6px; border-radius: 3px;
  background: #1c1c21; }}
QSlider::handle:horizontal {{
  width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
  background: white; border: none;
}}
QSlider#slR::groove:horizontal {{ background: #4a2430; }}
QSlider#slG::groove:horizontal {{ background: #1f4030; }}
QSlider#slB::groove:horizontal {{ background: #233a55; }}
QSlider#slR::handle:horizontal {{ background: #ff6b7a; }}
QSlider#slG::handle:horizontal {{ background: #4ade80; }}
QSlider#slB::handle:horizontal {{ background: #60a5fa; }}
QToolTip {{ background: #131315; color: {TEXTO}; border: 1px solid {BORDE}; }}
"""


def icono_app() -> QIcon:
    ic = QIcon.fromTheme("msi-mystic")
    if not ic.isNull():
        return ic
    for p in (os.path.join(REPO_DIR, "icons", "msi-mystic.svg"),
              os.path.expanduser("~/.local/share/icons/hicolor/scalable/apps/msi-mystic.svg")):
        if os.path.exists(p):
            ic2 = QIcon(p)
            if not ic2.isNull():
                return ic2
    return QIcon()


class Puente(QObject):
    log = Signal(str)


class Ventana(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mystic Light · MS-7D95")
        self.setWindowIcon(icono_app())
        self.resize(430, 700)
        self.puente = Puente()
        self.puente.log.connect(self._anadir_log)
        self.color = ColorRGB(0, 119, 255)
        self.puerto = "auto"
        self.personales = cargar_personalizados()
        self.hilo_efecto: threading.Thread | None = None
        self.parar_efecto = threading.Event()
        self._construir_ui()
        self._mostrar_info()

    # -- UI --
    def _tarjeta(self) -> tuple[QFrame, QVBoxLayout]:
        f = QFrame()
        f.setObjectName("tarjeta")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        return f, lay

    def _construir_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        # Cabecera
        cab = QHBoxLayout()
        self.lbl_dot = QLabel("●")
        self.lbl_dot.setStyleSheet(f"color: {APAGADO}; font-size: 14px;")
        titulo = QLabel("Mystic Light")
        titulo.setObjectName("titulo")
        cab.addWidget(self.lbl_dot)
        cab.addWidget(titulo)
        cab.addStretch(1)
        self.btn_root_mini = QPushButton("root")
        self.btn_root_mini.setObjectName("mini")
        self.btn_root_mini.setToolTip("Reiniciar como root (pkexec)")
        self.btn_root_mini.clicked.connect(self._reiniciar_root)
        cab.addWidget(self.btn_root_mini)
        lay.addLayout(cab)

        self.lbl_placa = QLabel("Detectando placa…")
        self.lbl_placa.setObjectName("sub")
        self.lbl_placa.setWordWrap(True)
        lay.addWidget(self.lbl_placa)

        # Vista previa + HEX
        t_prev, l_prev = self._tarjeta()
        centro = QHBoxLayout()
        centro.addStretch(1)
        self.vista = QLabel()
        self.vista.setObjectName("vista")
        self.vista.setFixedSize(120, 120)
        self.vista.setAlignment(Qt.AlignCenter)
        centro.addWidget(self.vista)
        centro.addStretch(1)
        l_prev.addLayout(centro)
        fila_hex = QHBoxLayout()
        self.txt_hex = QLineEdit("0077FF")
        self.txt_hex.setMaxLength(7)
        self.txt_hex.setAlignment(Qt.AlignCenter)
        self.txt_hex.editingFinished.connect(self._desde_hex)
        self.btn_paleta = QPushButton("Paleta")
        self.btn_paleta.clicked.connect(self._elegir_color)
        fila_hex.addWidget(self.txt_hex)
        fila_hex.addWidget(self.btn_paleta)
        l_prev.addLayout(fila_hex)
        lay.addWidget(t_prev)

        # Canales
        t_ch, l_ch = self._tarjeta()
        lab = QLabel("COLOR")
        lab.setObjectName("seccion")
        l_ch.addWidget(lab)
        self.sliders: dict[str, tuple[QSlider, QLabel]] = {}
        for nombre, canal, obj in (("R", "r", "slR"), ("G", "g", "slG"), ("B", "b", "slB")):
            fila = QHBoxLayout()
            tag = QLabel(nombre)
            tag.setFixedWidth(14)
            fila.addWidget(tag)
            sl = QSlider(Qt.Horizontal)
            sl.setObjectName(obj)
            sl.setRange(0, 255)
            sl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            sl.valueChanged.connect(self._desde_sliders)
            fila.addWidget(sl)
            val = QLabel("0")
            val.setFixedWidth(30)
            val.setAlignment(Qt.AlignRight)
            val.setStyleSheet(f"color: {APAGADO};")
            fila.addWidget(val)
            l_ch.addLayout(fila)
            self.sliders[canal] = (sl, val)
        lay.addWidget(t_ch)

        # Presets
        t_pre, l_pre = self._tarjeta()
        lab2 = QLabel("PRESETS")
        lab2.setObjectName("seccion")
        l_pre.addWidget(lab2)
        gp = QGridLayout()
        gp.setSpacing(8)
        for i, (nombre, hexv) in enumerate(PRESETS):
            b = QPushButton()
            b.setObjectName("dot")
            b.setFixedSize(30, 30)
            b.setToolTip(nombre)
            b.setStyleSheet(f"#dot {{ background: #{hexv}; }}")
            b.clicked.connect(lambda _=False, h=hexv: self._fijar_hex(h))
            gp.addWidget(b, i // 5, i % 5)
        l_pre.addLayout(gp)
        lay.addWidget(t_pre)

        # Colores personales (hasta 6, se guardan en ~/.config/msi-mystic/)
        t_mios, l_mios = self._tarjeta()
        fila_mios = QHBoxLayout()
        lab3 = QLabel("MIS COLORES")
        lab3.setObjectName("seccion")
        fila_mios.addWidget(lab3)
        fila_mios.addStretch(1)
        self.lbl_cuenta = QLabel("")
        self.lbl_cuenta.setStyleSheet(f"color: {APAGADO}; font-size: 11px;")
        fila_mios.addWidget(self.lbl_cuenta)
        l_mios.addLayout(fila_mios)
        gm = QGridLayout()
        gm.setSpacing(8)
        self.slot_btns: list[QPushButton] = []
        for i in range(MAX_PERSONALIZADOS):
            b = QPushButton()
            b.setObjectName("dot")
            b.setFixedSize(30, 30)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.clicked.connect(lambda _=False, idx=i: self._click_slot(idx))
            b.customContextMenuRequested.connect(lambda _=None, idx=i: self._borrar_slot(idx))
            gm.addWidget(b, 0, i)
            self.slot_btns.append(b)
        l_mios.addLayout(gm)
        lay.addWidget(t_mios)
        self._refrescar_slots()

        # Acciones principales
        fila_btn = QHBoxLayout()
        self.btn_aplicar = QPushButton("Aplicar")
        self.btn_aplicar.setObjectName("primario")
        self.btn_aplicar.clicked.connect(self._aplicar)
        fila_btn.addWidget(self.btn_aplicar)
        self.btn_apagar = QPushButton("Apagar")
        self.btn_apagar.setObjectName("peligro")
        self.btn_apagar.clicked.connect(self._apagar)
        fila_btn.addWidget(self.btn_apagar)
        self.btn_rainbow = QPushButton("Arcoíris")
        self.btn_rainbow.clicked.connect(self._toggle_rainbow)
        fila_btn.addWidget(self.btn_rainbow)
        lay.addLayout(fila_btn)

        # Avanzado (colapsable)
        self.btn_av = QPushButton("⚙ Avanzado ▸")
        self.btn_av.setObjectName("mini")
        self.btn_av.clicked.connect(self._toggle_avanzado)
        lay.addWidget(self.btn_av)
        self.panel_av = QWidget()
        lav = QVBoxLayout(self.panel_av)
        lav.setContentsMargins(0, 0, 0, 0)
        t_hw, l_hw = self._tarjeta()
        self.chk_pulso = QCheckBox("Pulso suave")
        l_hw.addWidget(self.chk_pulso)
        f1 = QHBoxLayout()
        f1.addWidget(QLabel("Blink"))
        self.cmb_blink = QComboBox()
        self.cmb_blink.addItems(["Siempre on", "1", "2", "3", "4", "5", "6 lento"])
        f1.addWidget(self.cmb_blink)
        f1.addWidget(QLabel("Duración"))
        self.spin_dur = QComboBox()
        self.spin_dur.setEditable(True)
        self.spin_dur.addItems(["25", "60", "120", "250", "511"])
        self.spin_dur.setCurrentText("25")
        f1.addWidget(self.spin_dur)
        l_hw.addLayout(f1)
        f2 = QHBoxLayout()
        f2.addWidget(QLabel("Puerto"))
        self.cmb_port = QComboBox()
        self.cmb_port.addItems(["auto", "4e", "2e"])
        self.cmb_port.currentTextChanged.connect(lambda t: setattr(self, "puerto", t))
        f2.addWidget(self.cmb_port)
        self.chk_inv_r = QCheckBox("Inv R")
        self.chk_inv_g = QCheckBox("Inv G")
        self.chk_inv_b = QCheckBox("Inv B")
        f2.addWidget(self.chk_inv_r)
        f2.addWidget(self.chk_inv_g)
        f2.addWidget(self.chk_inv_b)
        l_hw.addLayout(f2)
        f3 = QHBoxLayout()
        self.btn_detect = QPushButton("Detectar hardware")
        self.btn_detect.setObjectName("mini")
        self.btn_detect.clicked.connect(self._detectar)
        f3.addWidget(self.btn_detect)
        f3.addStretch(1)
        l_hw.addLayout(f3)
        lav.addWidget(t_hw)
        self.panel_av.setVisible(False)
        lay.addWidget(self.panel_av)

        # Registro (colapsable)
        self.btn_log = QPushButton("Registro ▸")
        self.btn_log.setObjectName("mini")
        self.btn_log.clicked.connect(self._toggle_log)
        lay.addWidget(self.btn_log)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        self.log.setVisible(False)
        lay.addWidget(self.log)

        lay.addStretch(1)
        self._refrescar_vista()

    def _toggle_avanzado(self):
        vis = not self.panel_av.isVisible()
        self.panel_av.setVisible(vis)
        self.btn_av.setText("⚙ Avanzado ▾" if vis else "⚙ Avanzado ▸")

    def _toggle_log(self):
        vis = not self.log.isVisible()
        self.log.setVisible(vis)
        self.btn_log.setText("Registro ▾" if vis else "Registro ▸")

    # -- helpers --
    def _anadir_log(self, s: str):
        self.log.append(s)
        if not self.log.isVisible():
            self.btn_log.setText("Registro ▸ •")

    def logea(self, s: str):
        self.puente.log.emit(s)

    def _mostrar_info(self):
        info = info_placa()
        self.lbl_placa.setText(f"{info['board']} · BIOS {info['bios']}")
        if es_root():
            self.lbl_dot.setStyleSheet("color: #4ade80; font-size: 14px;")
            self.lbl_dot.setToolTip("Root: acceso a /dev/port disponible")
            self.btn_root_mini.setVisible(False)
        else:
            self.lbl_dot.setStyleSheet("color: #fbbf24; font-size: 14px;")
            self.lbl_dot.setToolTip("Sin root: pulsa «root» para elevar con pkexec")
        if "7D95" not in info["board"]:
            self.logea(f"AVISO: placa {info['board']!r} no es MS-7D95. "
                       "El protocolo suele ser compatible, pero verifica antes de aplicar.")

    def _fijar_hex(self, h: str):
        try:
            self.color = ColorRGB.desde_hex(h)
        except ValueError as e:
            self.logea(f"ERROR: {e}")
            return
        self._refrescar_vista()

    def _refrescar_slots(self):
        for i, b in enumerate(self.slot_btns):
            if i < len(self.personales):
                h = self.personales[i]
                b.setText("")
                b.setStyleSheet(f"#dot {{ background: #{h}; border: 2px solid #1e1e23; }}")
                b.setToolTip(f"#{h} — clic: usar · clic derecho: borrar")
            else:
                b.setText("+")
                b.setStyleSheet(f"#dot {{ background: transparent; border: 2px dashed #333338; "
                                f"color: #66666e; font-size: 16px; }}")
                b.setToolTip("Guardar el color actual aquí")
        self.lbl_cuenta.setText(f"{len(self.personales)}/{MAX_PERSONALIZADOS}")

    def _click_slot(self, i: int):
        if i < len(self.personales):
            self._fijar_hex(self.personales[i])
        else:
            h = self.color.a_hex()
            if h in self.personales:
                self.logea(f"#{h} ya está guardado.")
                return
            self.personales.append(h)
            guardar_personalizados(self.personales)
            self._refrescar_slots()
            self.logea(f"Guardado #{h} en el hueco {i + 1}.")

    def _borrar_slot(self, i: int):
        if i < len(self.personales):
            h = self.personales.pop(i)
            guardar_personalizados(self.personales)
            self._refrescar_slots()
            self.logea(f"Borrado #{h}.")

    def _desde_hex(self):
        try:
            self.color = ColorRGB.desde_hex(self.txt_hex.text())
            self._refrescar_vista()
        except ValueError:
            self.txt_hex.setText(self.color.a_hex())

    def _refrescar_vista(self):
        c = self.color
        lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255
        fg = "#000000" if lum > 0.6 else "#f2f2f4"
        self.vista.setStyleSheet(
            f"#vista {{ background: #{c.a_hex()}; border: 2px solid #1e1e23; "
            f"color: {fg}; font-weight: 700; }}")
        self.vista.setText(f"#{c.a_hex()}")
        if self.txt_hex.text().strip("#").upper() != c.a_hex():
            self.txt_hex.setText(c.a_hex())
        for canal, val in (("r", c.r), ("g", c.g), ("b", c.b)):
            sl, lab = self.sliders[canal]
            sl.blockSignals(True)
            sl.setValue(val)
            sl.blockSignals(False)
            lab.setText(str(val))

    def _desde_sliders(self):
        r = self.sliders["r"][0].value()
        g = self.sliders["g"][0].value()
        b = self.sliders["b"][0].value()
        self.color = ColorRGB(r, g, b)
        self._refrescar_vista()

    def _elegir_color(self):
        ini = QColor(f"#{self.color.a_hex()}")
        c = QColorDialog.getColor(ini, self, "Elegir color")
        if c.isValid():
            self.color = ColorRGB(c.red(), c.green(), c.blue())
            self._refrescar_vista()

    def _resolver_puerto(self) -> int | None:
        return None if self.puerto == "auto" else int(self.puerto, 16)

    def _abrir_sio(self) -> SuperIO:
        pedido = self._resolver_puerto()
        if pedido is not None:
            return SuperIO(pedido)
        det = detectar()
        if det is None:
            raise SuperIOError("No se encontro NCT6795/NCT6797 en 0x2E/0x4E.")
        self.logea(f"SuperIO {det.chip_nombre} en {det.puerto:#04x}")
        return SuperIO(det.puerto)

    def _duracion(self) -> int:
        try:
            d = int(self.spin_dur.currentText())
        except ValueError:
            return 25
        return max(0, min(511, d))

    def _opciones_hw(self):
        return dict(
            pulse=self.chk_pulso.isChecked(),
            blink=self.cmb_blink.currentIndex(),
            duracion=self._duracion(),
            invertir=(self.chk_inv_r.isChecked(),
                      self.chk_inv_g.isChecked(),
                      self.chk_inv_b.isChecked()),
        )

    @Slot()
    def _aplicar(self):
        try:
            self.color = ColorRGB.desde_hex(self.txt_hex.text())
            self._refrescar_vista()
        except ValueError as e:
            QMessageBox.warning(self, "Color inválido", str(e))
            return
        self._parar_efecto_si_hay()
        try:
            with self._abrir_sio() as sio:
                MSIRGB(sio).set_estatico(self.color, **self._opciones_hw())
            self.logea(f"OK: #{self.color.a_hex()} aplicado.")
        except SuperIOError as e:
            QMessageBox.critical(self, "Error SuperIO", str(e))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(e))

    @Slot()
    def _apagar(self):
        self._parar_efecto_si_hay()
        try:
            with self._abrir_sio() as sio:
                MSIRGB(sio).apagar()
            self.logea("OK: RGB apagado.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", str(e))

    @Slot()
    def _detectar(self):
        info = info_placa()
        self.logea(f"Placa: {info['vendor']} {info['board']} BIOS {info['bios']}")
        for base in (0x4E, 0x2E):
            try:
                with SuperIO(base) as sio:
                    cid = sio.leer_id()
                    nombre = sio.nombre_chip(cid)
                    self.logea(f"puerto {base:#04x}: ID {cid:#06x} -> "
                               + (nombre or "no compatible"))
                    if nombre:
                        estado = MSIRGB(sio).leer_estado()
                        regs = " ".join(f"{k}={v:02X}" for k, v in sorted(estado.items()))
                        self.logea(f"  banco 0x12: {regs}")
            except SuperIOError as e:
                self.logea(f"puerto {base:#04x}: {e}")
                return

    def _reiniciar_root(self):
        prog = sys.executable
        env = {
            "WAYLAND_DISPLAY": os.environ.get("WAYLAND_DISPLAY", "wayland-1"),
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"),
            "DISPLAY": os.environ.get("DISPLAY", ":1"),
            "XAUTHORITY": os.environ.get("XAUTHORITY", os.path.expanduser("~/.Xauthority")),
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "wayland"),
            "PYTHONPATH": REPO_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""),
        }
        args = ["pkexec", "env"] + [f"{k}={v}" for k, v in env.items()] + [prog, "-m", "msi_mystic.gui"]
        try:
            subprocess.Popen(args)
            QApplication.quit()
        except FileNotFoundError:
            QMessageBox.warning(self, "pkexec no encontrado",
                                "Ejecuta en terminal (sin sudo, el lanzador eleva solo):\n"
                                "  ./msi-mystic --gui")

    # -- arcoiris en hilo --
    def _toggle_rainbow(self):
        if self.hilo_efecto and self.hilo_efecto.is_alive():
            self._parar_efecto_si_hay()
            self.btn_rainbow.setText("Arcoíris")
            return
        self.parar_efecto.clear()
        self.hilo_efecto = threading.Thread(target=self._bucle_rainbow, daemon=True)
        self.hilo_efecto.start()
        self.btn_rainbow.setText("■ Parar")

    def _parar_efecto_si_hay(self):
        if self.hilo_efecto and self.hilo_efecto.is_alive():
            self.parar_efecto.set()
            self.hilo_efecto.join(timeout=2)

    def _bucle_rainbow(self):
        try:
            with self._abrir_sio() as sio:
                ctl = MSIRGB(sio)
                i = 0
                while not self.parar_efecto.is_set():
                    h = (i % 360) / 360.0
                    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
                    ctl.set_estatico(ColorRGB(int(r * 255), int(g * 255), int(b * 255)),
                                     duracion=5)
                    i += 2
                    time.sleep(1 / 30)
        except Exception as e:  # noqa: BLE001
            self.logea(f"ERROR arcoiris: {e}")
        self.puente.log.emit("Arcoiris detenido.")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(FONDO))
    pal.setColor(QPalette.WindowText, QColor(TEXTO))
    pal.setColor(QPalette.Base, QColor("#131315"))
    pal.setColor(QPalette.AlternateBase, QColor(TARJETA))
    pal.setColor(QPalette.Text, QColor(TEXTO))
    pal.setColor(QPalette.Button, QColor("#141416"))
    pal.setColor(QPalette.ButtonText, QColor(TEXTO))
    pal.setColor(QPalette.Highlight, QColor(ACENTO))
    pal.setColor(QPalette.HighlightedText, QColor("#03130a"))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
    app.setWindowIcon(icono_app())
    v = Ventana()
    v.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
