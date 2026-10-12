"""Controlador MSI-RGB (SuperIO banco 0x12).

Replica la logica de:
  - nagisa/msi-rgb (Rust): secuencia completa con E4/FE/FF/FD + 8 frames
  - OpenRGB MSIRGBController: enable 0xE0, CFG_3 0xFF=0b11100010, FD=0x00

Registros banco 0x12:
  E0: enable (bits 7..5 = 1 => RGB activo)
  E4: bit0=disable, bit3=pulso suave, bits2..0=blink ((blink+1)&7, 0=siempre on)
  F0-F3: rojo, 4 bytes x 2 nibbles = 8 frames (frame0 = nibble bajo de F0 ...)
  F4-F7: verde, F8-FB: azul. Cada nibble 0x0-0xF (4 bits por color).
  FE: duracion paso bits 7..0
  FF: bit0=duracion bit8, bit1=1 (header on), bits4..2=invert b/g/r,
      bits7..5=fade (1=sin fade, 0=fade en ese canal, solo algunas placas)
  FD: 0x00 desactiva modo rainbow (OpenRGB)

Color estatico: los 8 frames iguales.
  nibble = canal8bits >> 4 ; u32 = nibble * 0x11111111
  Ej: #FF0000 -> R nibble 0xF -> 0xFFFFFFFF, G/B 0x00000000.

MS-7D95 (PRO B550M-P GEN3): invert=False segun tabla OpenRGB.
"""
from __future__ import annotations

from dataclasses import dataclass

from .superio import SuperIO


BANCO_RGB = 0x12
BANCO_CFG = 0x09
REG_CFG_09_2C = 0x2C

REG_ENABLE = 0xE0
REG_CFG1 = 0xE4
REG_RED = (0xF0, 0xF1, 0xF2, 0xF3)
REG_GREEN = (0xF4, 0xF5, 0xF6, 0xF7)
REG_BLUE = (0xF8, 0xF9, 0xFA, 0xFB)
REG_FE = 0xFE
REG_FF = 0xFF
REG_FD = 0xFD

MASCARA_ENABLE = 0xE0


@dataclass
class ColorRGB:
    r: int
    g: int
    b: int

    def __post_init__(self):
        for v in (self.r, self.g, self.b):
            if not 0 <= v <= 255:
                raise ValueError("cada canal debe estar en 0..255")

    @classmethod
    def desde_hex(cls, s: str) -> "ColorRGB":
        s = s.strip().lstrip("#")
        if len(s) == 3:  # "f00" -> "ff0000"
            s = "".join(c * 2 for c in s)
        if len(s) != 6:
            raise ValueError(f"color hex invalido: {s!r}, usa RRGGBB (ej. FF0000)")
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
        except ValueError as e:
            raise ValueError(f"color hex invalido: {s!r}") from e
        return cls(r, g, b)

    def a_hex(self) -> str:
        return f"{self.r:02X}{self.g:02X}{self.b:02X}"


def _expandir_nibble(n: int) -> int:
    """Repite un nibble (0-15) 8 veces -> u32. Ej: 0xF -> 0xFFFFFFFF."""
    n &= 0xF
    return (n * 0x11111111) & 0xFFFFFFFF


def _u32_a_bytes(v: int) -> tuple[int, int, int, int]:
    return ((v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


class MSIRGB:
    """Controlador de color. Necesita un SuperIO ya abierto (with)."""

    def __init__(self, sio: SuperIO):
        self.sio = sio

    # -- bajo nivel --
    def _preparar(self):
        # Paso requerido para que funcione el pulso (OpenRGB + msi-rgb):
        # banco 0x09, reg 0x2C, activar bit 0x10.
        self.sio.seleccionar(BANCO_CFG)
        c = self.sio.leer_reg(REG_CFG_09_2C)
        if c & 0x10 != 0x10:
            self.sio.escribir_reg(REG_CFG_09_2C, c | 0x10)
        # Seleccionar banco RGB
        self.sio.seleccionar(BANCO_RGB)
        # Activar RGB si no lo esta (preserva bits bajos)
        d = self.sio.leer_reg(REG_ENABLE)
        if d & MASCARA_ENABLE != MASCARA_ENABLE:
            self.sio.escribir_reg(REG_ENABLE, 0xE0 | (d & ~MASCARA_ENABLE & 0xFF))
        # Desactivar modo rainbow interno
        self.sio.escribir_reg(REG_FD, 0x00)

    def _escribir_canal(self, regs: tuple[int, int, int, int], u32: int):
        b0, b1, b2, b3 = _u32_a_bytes(u32)
        for reg, val in zip(regs, (b0, b1, b2, b3)):
            self.sio.escribir_reg(reg, val)

    # -- API publica --
    def set_estatico(
        self,
        color: ColorRGB,
        pulse: bool = False,
        blink: int = 0,
        duracion: int = 25,
        invertir: tuple[bool, bool, bool] = (False, False, False),
        apagar: bool = False,
    ):
        """Fija un color estatico (los 8 frames iguales).

        pulse: pulso suave. blink: 0=siempre on, 1..6 parpadeo (6=lento).
        duracion: 0..511 (25 por defecto). invertir: (r,g,b).
        apagar: True apaga el subsistema RGB (E4 bit0).
        """
        if not 0 <= blink <= 6:
            raise ValueError("blink debe estar en 0..6")
        if not 0 <= duracion <= 511:
            raise ValueError("duracion debe estar en 0..511")
        self._preparar()

        e4 = (1 if apagar else 0) | (0b1000 if pulse else 0) | (0 if blink == 0 else ((blink + 1) & 0b111))
        self.sio.escribir_reg(REG_CFG1, e4)
        self.sio.escribir_reg(REG_FE, duracion & 0xFF)

        inv_r, inv_g, inv_b = invertir
        # Ojo: en FF los bits de invert son b=0x10, g=0x08, r=0x04
        ff_inv = (0x10 if inv_b else 0) | (0x08 if inv_g else 0) | (0x04 if inv_r else 0)
        ff_fade = 0b11100000  # sin fade
        ff = ((duracion >> 8) & 0x01) | 0b10 | ff_inv | ff_fade
        self.sio.escribir_reg(REG_FF, ff)

        r32 = _expandir_nibble(color.r >> 4)
        g32 = _expandir_nibble(color.g >> 4)
        b32 = _expandir_nibble(color.b >> 4)
        self._escribir_canal(REG_RED, r32)
        self._escribir_canal(REG_GREEN, g32)
        self._escribir_canal(REG_BLUE, b32)

    def set_frames(
        self,
        r32: int,
        g32: int,
        b32: int,
        pulse: bool = False,
        blink: int = 0,
        duracion: int = 25,
        invertir: tuple[bool, bool, bool] = (False, False, False),
    ):
        """Modo avanzado: 8 frames por canal como u32 (cada nibble = un frame).

        Ej: r32=0xF0000000 solo enciende rojo en el frame 0.
        Util para efectos hardware sin bucle software.
        """
        self._preparar()
        e4 = (0b1000 if pulse else 0) | (0 if blink == 0 else ((blink + 1) & 0b111))
        self.sio.escribir_reg(REG_CFG1, e4)
        self.sio.escribir_reg(REG_FE, duracion & 0xFF)
        inv_r, inv_g, inv_b = invertir
        ff_inv = (0x10 if inv_b else 0) | (0x08 if inv_g else 0) | (0x04 if inv_r else 0)
        ff = ((duracion >> 8) & 0x01) | 0b10 | ff_inv | 0b11100000
        self.sio.escribir_reg(REG_FF, ff)
        self._escribir_canal(REG_RED, r32 & 0xFFFFFFFF)
        self._escribir_canal(REG_GREEN, g32 & 0xFFFFFFFF)
        self._escribir_canal(REG_BLUE, b32 & 0xFFFFFFFF)

    def apagar(self):
        self.set_estatico(ColorRGB(0, 0, 0), apagar=True)

    def leer_estado(self) -> dict:
        """Lee los registros RGB actuales (requiere banco 0x12). Solo lectura."""
        self.sio.seleccionar(BANCO_RGB)
        regs = {}
        for r in (REG_ENABLE, REG_CFG1, REG_FE, REG_FF, REG_FD,
                  *REG_RED, *REG_GREEN, *REG_BLUE):
            regs[f"{r:02X}"] = self.sio.leer_reg(r)
        return regs

    @staticmethod
    def estado_a_color(estado: dict) -> ColorRGB:
        """Aproxima el color estatico desde F0/F4/F8 (nibble alto del frame 0)."""
        def nibble(regs):
            # F0 contiene frames 0,1: byte = (f1<<4)|f0? Segun msi-rgb la secuencia
            # al escribir u32 big-endian es 10 32 54 76, asi que frame0 = nibble bajo de F0.
            return estado[regs] & 0x0F
        r = (nibble("F0") << 4) | nibble("F0")
        g = (nibble("F4") << 4) | nibble("F4")
        b = (nibble("F8") << 4) | nibble("F8")
        # Expandir 4->8 bits aproximado: v*17
        return ColorRGB(min(255, r), min(255, g), min(255, b))
