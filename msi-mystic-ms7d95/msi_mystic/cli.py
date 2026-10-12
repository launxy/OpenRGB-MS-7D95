"""CLI: msi-mystic detect|set|off|rainbow|breathing.

Ejemplos:
  sudo msi-mystic detect --verbose
  sudo msi-mystic set --color FF0000
  sudo msi-mystic set --color 00FF88 --pulse --duracion 100
  sudo msi-mystic off
  sudo msi-mystic rainbow --brillo 80 --velocidad 30
  sudo msi-mystic breathing --color 0088FF --velocidad 20
"""
from __future__ import annotations

import argparse
import colorsys
import sys
import time

from .superio import SuperIO, detectar, es_root, info_placa, SuperIOError
from .controller import MSIRGB, ColorRGB


def _parse_invert(s: str | None) -> tuple[bool, bool, bool]:
    if not s:
        return (False, False, False)
    partes = {p.strip().lower() for p in s.split(",") if p.strip()}
    desconocido = partes - {"r", "g", "b"}
    if desconocido:
        raise ValueError(f"--invert invalido: {desconocido}, usa r,g,b")
    return ("r" in partes, "g" in partes, "b" in partes)


def _resolver_puerto(args) -> int | None:
    if args.port == "auto":
        return None
    return int(args.port, 16)


def _abrir(args) -> tuple[SuperIO, int]:
    """Devuelve (SuperIO abierto, puerto). Maneja --dry-run y autodeteccion."""
    dry = bool(getattr(args, "dry_run", False))
    if not dry and not es_root():
        print("ERROR: necesitas root para tocar /dev/port.", file=sys.stderr)
        print("Usa: sudo msi-mystic ...  o  --dry-run para probar sin hardware.", file=sys.stderr)
        sys.exit(2)
    pedido = _resolver_puerto(args)
    if pedido is not None:
        return SuperIO(pedido, dry_run=dry), pedido
    det = detectar(dry_run=dry)
    if det is None:
        print("ERROR: no se encontro NCT6795/NCT6797 en 0x2E/0x4E.", file=sys.stderr)
        print("Prueba --port 2e o --port 4e manualmente, o --dry-run.", file=sys.stderr)
        sys.exit(3)
    print(f"SuperIO {det.chip_nombre} (ID {det.chip_id:#06x}) en puerto {det.puerto:#04x}")
    return SuperIO(det.puerto, dry_run=dry), det.puerto


def _aviso_placa(forzar: bool):
    info = info_placa()
    print(f"Placa: {info['vendor']} {info['board']} (BIOS {info['bios']})")
    if "7D95" not in info["board"] and "Micro-Star" not in info["vendor"] and "MSI" not in info["vendor"]:
        print("AVISO: esta placa no parece una MSI MS-7D95.", file=sys.stderr)
        if not forzar:
            print("Usa --force para continuar de todos modos.", file=sys.stderr)
            sys.exit(4)
    elif "7D95" not in info["board"]:
        print("AVISO: placa MSI pero no MS-7D95. El protocolo deberia valer, pero usa --force.", file=sys.stderr)
        if not forzar:
            # No bloqueamos: muchas MSI comparten protocolo. Solo avisamos.
            pass


def cmd_detect(args):
    _aviso_placa(args.force)
    dry = bool(args.dry_run)
    puertos = (0x2E, 0x4E) if _resolver_puerto(args) is None else (_resolver_puerto(args),)
    for base in sorted(puertos, key=lambda p: 0 if p == 0x4E else 1):
        try:
            with SuperIO(base, dry_run=dry) as sio:
                cid = sio.leer_id()
                nombre = sio.nombre_chip(cid)
                tag = f"OK ({nombre})" if nombre else "no compatible"
                print(f"puerto {base:#04x}: ID {cid:#06x} -> {tag}")
                if nombre and args.verbose:
                    ctl = MSIRGB(sio)
                    estado = ctl.leer_estado()
                    print("  registros banco 0x12:")
                    for k in sorted(estado):
                        print(f"    {k}: {estado[k]:02X}")
                    try:
                        c = MSIRGB.estado_a_color(estado)
                        print(f"  color aprox: #{c.a_hex()}")
                    except Exception:
                        pass
        except SuperIOError as e:
            print(f"puerto {base:#04x}: {e}", file=sys.stderr)
            sys.exit(2)


def cmd_set(args):
    _aviso_placa(args.force)
    color = ColorRGB.desde_hex(args.color)
    inv = _parse_invert(args.invert)
    with _abrir(args)[0] as sio:
        ctl = MSIRGB(sio)
        ctl.set_estatico(color, pulse=args.pulse, blink=args.blink,
                         duracion=args.duracion, invertir=inv)
        modo = "pulso" if args.pulse else ("blink %d" % args.blink if args.blink else "estatico")
        print(f"OK: #{color.a_hex()} aplicado ({modo}, duracion {args.duracion})"
              + (f" [dry-run, puerto {sio.base:#04x}]" if sio.dry_run else f" [puerto {sio.base:#04x}]"))


def cmd_off(args):
    _aviso_placa(args.force)
    with _abrir(args)[0] as sio:
        MSIRGB(sio).apagar()
        print("OK: RGB apagado.")


def _hsv_a_color(h: float, s: float, v: float) -> ColorRGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return ColorRGB(int(r * 255), int(g * 255), int(b * 255))


def cmd_rainbow(args):
    _aviso_placa(args.force)
    brillo = max(1, min(100, args.brillo)) / 100.0
    pasos = max(1, args.pasos)
    espera = 1.0 / max(1.0, args.velocidad)
    print(f"Arcoiris software: Ctrl+C para parar (brillo {args.brillo}%, {args.velocidad} pasos/s).")
    with _abrir(args)[0] as sio:
        ctl = MSIRGB(sio)
        try:
            i = 0
            while True:
                h = (i % pasos) / pasos
                ctl.set_estatico(_hsv_a_color(h, 1.0, brillo), duracion=5)
                time.sleep(espera)
                i += 1
        except KeyboardInterrupt:
            print("\nParado. Dejando el ultimo color fijo.")
            if args.apagar_al_salir:
                ctl.apagar()
                print("RGB apagado.")


def cmd_breathing(args):
    _aviso_placa(args.force)
    base = ColorRGB.desde_hex(args.color)
    print(f"Respiracion #{base.a_hex()}: Ctrl+C para parar.")
    with _abrir(args)[0] as sio:
        ctl = MSIRGB(sio)
        try:
            t = 0.0
            paso = max(0.5, args.velocidad) / 50.0
            while True:
                import math
                f = (math.sin(t) + 1) / 2  # 0..1
                f = f * f  # curva mas suave
                c = ColorRGB(int(base.r * f), int(base.g * f), int(base.b * f))
                ctl.set_estatico(c, duracion=5)
                time.sleep(0.05)
                t += paso
        except KeyboardInterrupt:
            print("\nParado.")
            if args.apagar_al_salir:
                ctl.apagar()


def _add_comunes(parser):
    parser.add_argument("--port", default="auto", help="puerto base: auto, 2e o 4e (defecto: auto)")
    parser.add_argument("--dry-run", action="store_true", help="no toca hardware, simula un NCT6797")
    parser.add_argument("--force", action="store_true", help="continua aunque la placa no sea MS-7D95")


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="msi-mystic",
                                description="Control Mystic Light (MSI PRO B550M-P GEN3 / MS-7D95) en Linux via SuperIO.")
    _add_comunes(p)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="detecta SuperIO y muestra registros")
    d.add_argument("--verbose", "-v", action="store_true")
    _add_comunes(d)
    d.set_defaults(func=cmd_detect)

    s = sub.add_parser("set", help="fija un color estatico")
    s.add_argument("--color", "-c", required=True, help="hex RRGGBB, ej. FF0000")
    s.add_argument("--pulse", "-p", action="store_true", help="pulso suave hardware")
    s.add_argument("--blink", "-b", type=int, default=0, choices=range(0, 7), help="0=siempre on, 1..6 parpadeo")
    s.add_argument("--duracion", "-d", type=int, default=25, help="0..511, velocidad paso (def. 25)")
    s.add_argument("--invert", "-i", default="", help="canales a invertir, ej. 'r,g' o 'b' (def. ninguno)")
    _add_comunes(s)
    s.set_defaults(func=cmd_set)

    o = sub.add_parser("off", help="apaga el RGB")
    _add_comunes(o)
    o.set_defaults(func=cmd_off)

    r = sub.add_parser("rainbow", help="arcoiris por software (bucle hasta Ctrl+C)")
    r.add_argument("--brillo", type=int, default=100, help="1..100 (def. 100)")
    r.add_argument("--velocidad", type=float, default=30, help="pasos por segundo (def. 30)")
    r.add_argument("--pasos", type=int, default=360, help="pasos por vuelta (def. 360)")
    r.add_argument("--apagar-al-salir", action="store_true")
    _add_comunes(r)
    r.set_defaults(func=cmd_rainbow)

    br = sub.add_parser("breathing", help="respiracion por software en un color")
    br.add_argument("--color", "-c", required=True, help="hex RRGGBB base")
    br.add_argument("--velocidad", type=float, default=20, help="cuanto mayor, mas rapido (def. 20)")
    br.add_argument("--apagar-al-salir", action="store_true")
    _add_comunes(br)
    br.set_defaults(func=cmd_breathing)

    return p


def main(argv=None):
    parser = construir_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except SuperIOError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
