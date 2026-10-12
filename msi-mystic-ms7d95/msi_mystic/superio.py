"""Acceso de bajo nivel al SuperIO via /dev/port.

Protocolo (msi-rgb / OpenRGB):
  - Entrar en modo avanzado: outb(base, 0x87) x2
  - Salir: outb(base, 0xAA)
  - Seleccionar dispositivo logico: outb(base, 0x07) ; outb(base+1, dev)
  - Leer/escribir registro: outb(base, reg) ; inb/outb(base+1, ...)
  - ID chip: regs 0x20/0x21 -> 0xD350 (NCT6795) / 0xD450 (NCT6797)

Solo se toca el banco 0x12 (RGB) y el bit 0x10 de 0x09/0x2C.
No tocar otros bancos: riesgo de brick si se escriben registros equivocados.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


PUERTOS_BASE = (0x2E, 0x4E)
REG_DEVID_MSB = 0x20
REG_DEVID_LSB = 0x21

# (id & 0xFFF0) -> nombre. Igual que msi-rgb VALID_MASKS.
CHIPS_VALIDOS = {
    0xD350: "NCT6795",
    0xD450: "NCT6797",
}
MASCARA_ID = 0xFFF0


class SuperIOError(RuntimeError):
    pass


def leer_dmi(campo: str) -> str:
    """Lee /sys/class/dmi/id/<campo>. Devuelve '' si no se puede."""
    try:
        with open(f"/sys/class/dmi/id/{campo}", "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def info_placa() -> dict:
    return {
        "vendor": leer_dmi("board_vendor"),
        "board": leer_dmi("board_name"),
        "version": leer_dmi("board_version"),
        "bios": leer_dmi("bios_version"),
    }


def es_root() -> bool:
    return os.geteuid() == 0


class SuperIO:
    """Maneja /dev/port para un puerto base (0x2E o 0x4E).

    Uso:
        with SuperIO(0x4E) as sio:
            chip = sio.leer_id()
            sio.seleccionar(0x12)
            ...
    Si dry_run=True no toca hardware: usa registros falsos en memoria.
    Sirve para probar la app sin root / sin placa MSI.
    """

    def __init__(self, base: int = 0x4E, dry_run: bool = False):
        if base not in PUERTOS_BASE:
            raise ValueError(f"puerto base invalido: {base:#x}, usa 0x2E o 0x4E")
        self.base = base
        self.dry_run = dry_run
        self._f = None
        self._dev_seleccionado = None
        # Solo dry_run: {(dev, reg): valor}
        self._fake: dict[tuple[int, int], int] = {}
        self._fake_dev: int | None = None
        self._fake_reg: int | None = None
        if dry_run:
            # Simula un NCT6797 en MS-7D95 con valores por defecto
            self._fake[(0x09, 0x2C)] = 0x10
            self._fake[(0x12, 0xE0)] = 0xE0
            self._fake[(0x12, 0xE4)] = 0x00
            self._fake[(0x12, 0xFE)] = 0x19
            self._fake[(0x12, 0xFF)] = 0xE2
            self._fake[(0x12, 0xFD)] = 0x00
            for r in (0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
                      0xF8, 0xF9, 0xFA, 0xFB):
                self._fake[(0x12, r)] = 0xFF

    # -- context manager --
    def __enter__(self) -> "SuperIO":
        if self.dry_run:
            return self
        try:
            self._f = open("/dev/port", "r+b", buffering=0)
        except PermissionError as e:
            raise SuperIOError(
                "No se pudo abrir /dev/port (permiso denegado). "
                "Ejecuta como root: sudo msi-mystic ..."
            ) from e
        except FileNotFoundError as e:
            raise SuperIOError("No existe /dev/port. ¿Kernel sin CONFIG_DEVPORT?") from e
        self.entrar_avanzado()
        return self

    def __exit__(self, *exc):
        try:
            if not self.dry_run and self._f is not None:
                try:
                    self.salir_avanzado()
                finally:
                    self._f.close()
        finally:
            self._f = None
        return False

    # -- primitivas inb/outb --
    def outb(self, puerto: int, dato: int):
        dato &= 0xFF
        if self.dry_run:
            self._dry_outb(puerto, dato)
            return
        assert self._f is not None
        self._f.seek(puerto)
        self._f.write(bytes((dato,)))

    def inb(self, puerto: int) -> int:
        if self.dry_run:
            return self._dry_inb(puerto)
        assert self._f is not None
        self._f.seek(puerto)
        return self._f.read(1)[0]

    # -- modo avanzado --
    def entrar_avanzado(self):
        self.outb(self.base, 0x87)
        self.outb(self.base, 0x87)

    def salir_avanzado(self):
        self.outb(self.base, 0xAA)

    def seleccionar(self, dev: int):
        self.outb(self.base, 0x07)
        self.outb(self.base + 1, dev & 0xFF)
        self._dev_seleccionado = dev & 0xFF

    def leer_reg(self, reg: int) -> int:
        self.outb(self.base, reg & 0xFF)
        return self.inb(self.base + 1)

    def escribir_reg(self, reg: int, valor: int):
        self.outb(self.base, reg & 0xFF)
        self.outb(self.base + 1, valor & 0xFF)

    def leer_id(self) -> int:
        """Lee ID del chip (0x20/0x21). No necesita seleccionar banco."""
        self.outb(self.base, REG_DEVID_MSB)
        msb = self.inb(self.base + 1)
        self.outb(self.base, REG_DEVID_LSB)
        lsb = self.inb(self.base + 1)
        return (msb << 8) | lsb

    def nombre_chip(self, chip_id: int) -> str | None:
        return CHIPS_VALIDOS.get(chip_id & MASCARA_ID)

    # -- emulacion dry_run --
    def _dry_outb(self, puerto: int, dato: int):
        if puerto == self.base:
            # Escribiendo indice: puede ser 0x87/0xAA (modo) o 0x07 o un registro
            if dato in (0x87, 0xAA):
                return
            if dato == 0x07:
                self._fake_reg = 0x07  # siguiente outb(base+1) = dev
                return
            # Si el ultimo fue seleccionar dev, este dato es indice de registro
            self._fake_reg = dato
        elif puerto == self.base + 1:
            if self._fake_reg == 0x07:
                self._fake_dev = dato
                self._fake_reg = None
            elif self._fake_reg in (REG_DEVID_MSB, REG_DEVID_LSB):
                # Lectura de ID se resuelve en _dry_inb; el indice queda guardado
                pass
            else:
                dev = self._fake_dev if self._fake_dev is not None else 0x12
                self._fake[(dev, self._fake_reg)] = dato

    def _dry_inb(self, puerto: int) -> int:
        assert puerto == self.base + 1
        if self._fake_reg == REG_DEVID_MSB:
            return 0xD4  # NCT6797 -> 0xD450
        if self._fake_reg == REG_DEVID_LSB:
            return 0x50
        dev = self._fake_dev if self._fake_dev is not None else 0x12
        return self._fake.get((dev, self._fake_reg or 0), 0x00)


@dataclass
class Deteccion:
    puerto: int
    chip_id: int
    chip_nombre: str


def detectar(puertos: tuple[int, ...] = PUERTOS_BASE, dry_run: bool = False) -> Deteccion | None:
    """Prueba 0x4E primero y luego 0x2E. Devuelve Deteccion o None."""
    # 0x4E suele ser el correcto en MSI AM4; probarlo primero evita toques innecesarios.
    orden = sorted(puertos, key=lambda p: 0 if p == 0x4E else 1)
    for base in orden:
        try:
            with SuperIO(base, dry_run=dry_run) as sio:
                cid = sio.leer_id()
                nombre = sio.nombre_chip(cid)
                if nombre:
                    return Deteccion(puerto=base, chip_id=cid, chip_nombre=nombre)
        except SuperIOError:
            raise
        except OSError:
            continue
    return None
# Alias en ingles por compatibilidad
detect_superio = detectar
