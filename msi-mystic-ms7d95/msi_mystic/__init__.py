"""MSI Mystic Light para MS-7D95 (PRO B550M-P GEN3) en Linux.

Backend SuperIO NCT6795/NCT6797, banco 0x12.
Puerto desde msi-rgb (nagisa) + MSIRGBController (OpenRGB).
"""
from .superio import SuperIO, detect_superio, SuperIOError, leer_dmi
from .controller import MSIRGB, ColorRGB

__all__ = ["SuperIO", "detect_superio", "SuperIOError", "leer_dmi", "MSIRGB", "ColorRGB"]
__version__ = "1.0.0"
