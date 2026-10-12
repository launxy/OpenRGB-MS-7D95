<div align="center">

<img src="mysticlight.svg" width="128" alt=logo" />

# OpenRGB-MS-7D95
# MSI Mystic Light on Linux — PRO B550M-P GEN3 (MS-7D95)

App to control the Mystic Light colors of the **MSI PRO B550M-P GEN3 (MS-7D95)**
motherboard on Linux (developed and tested on CachyOS), talking directly to
the **Nuvoton NCT6795/NCT6797** SuperIO chip. It was born because OpenRGB does
not detect this board (the why, with evidence, further below).

## Features

- **Static color** on onboard LEDs + strip connected to **JRGB1 (12V)**.
  The hardware gives 4 bits per channel (16 levels per color, 4096 colors).
- **Hardware smooth pulsing and blinking** (`--pulse`, `--blink 1-6`,
  `--duracion 0-511`) and per-channel inversion (`--invert r,g,b`).
- **6 custom colors**: slots stored in `~/.config/msi-mystic/colores.json`
  that persist across sessions. Click an empty slot = save the current color;
  click a filled one = load it; right-click = delete it.
- **Software effects** (the hardware can't do more): `rainbow` and
  `breathing`, rewriting the color ~30 times/s until Ctrl+C.
- **Full CLI**: `detect | set | off | rainbow | breathing`, with a `--dry-run`
  mode that simulates a NCT6797 without touching hardware or needing root.
- **Pure-black Qt6 GUI with green accent**: large preview, HEX field,
  RGB sliders, presets, threaded rainbow, collapsible advanced panel
  (pulse/blink/duration/port/inverts) and collapsible log.
  Without root it warns and relaunches via pkexec while keeping the
  Wayland display.
- **Desktop launcher** (own RGB bulb icon, validated) and a **`--user`
  systemd service** to restore your color at boot.

## Requirements

- MSI MS-7D95 board (the protocol usually works on other MSI boards with
  NCT6795/6797 — use `--force` at your own risk).
- Linux with `/dev/port`, Python 3 and PySide6. Root is only needed to write
  to the SuperIO (`--dry-run` doesn't need it).

## Install & quick start

```bash
./install.sh
./msi-mystic detect --dry-run --verbose   # safe test, no hardware
sudo ./msi-mystic detect --verbose        # should show NCT6795/6797 on 0x4E
sudo ./msi-mystic set --color 00E676
./msi-mystic --gui                        # elevates itself, don't prepend sudo
```

Restore color at boot (edit the color in the `.service` first):

```bash
systemctl --user enable --now msi-mystic.service
```

## Comparison with OpenRGB

| | This app | OpenRGB |
|---|---|---|
| Detects the MS-7D95 | Yes (direct SuperIO) | No (tested by the author, never shows up) |
| Method | SuperIO `0x2E/0x4E`, bank `0x12` | USB HID and SuperIO depending on board |
| Effects | Static + HW pulse/blink + SW rainbow/breathing | Large catalog (on supported boards) |
| Dependencies | Just Python + PySide6 | Full Qt daemon, udev, SMBus |
| Risk | Only touches RGB bank `0x12` | History of bricked RGB on MSI boards |

This is not an OpenRGB replacement: it's a minimal tool for a board OpenRGB
doesn't cover. If OpenRGB ever adds PID `7D95`, use it.

## Why OpenRGB didn't work on this board (drivers)

Checked against the OpenRGB source (master branch) and this very machine:

1. **The USB detector doesn't include the MS-7D95.** `MSIMotherboardControllerDetect.cpp`
   registers specific PIDs (`1462:7B12`, `7C02`, `7D96`…) and the common `0DB0:0076`,
   but there is **no `1462:7D95` entry**. And even if there were, `lsusb` on this
   machine shows no `1462:xxxx` or `0DB0:0076` device at all: this budget board
   **exposes no USB RGB controller**. The USB path is impossible here.
2. **The SuperIO driver does cover the board** (`MSIRGBControllerDetect.cpp`
   includes `{"7D95", false}` for NCT6795/NCT6797), but it demands: running as
   root (access to `SIO`/`/dev/port`), the chip being exactly NCT6795/6797,
   and no other driver holding the SuperIO. Any of those three failing explains
   why the board still doesn't show up when trying it.
3. **Conclusion**: on the MS-7D95 only the SuperIO path remains, which is exactly
   what this app implements with the same protocol (`nagisa/msi-rgb` +
   `MSIRGBController`: advanced mode `0x87/0x87`, bank `0x12`, registers
   `E0/E4/F0-FB/FD/FE/FF`) — but asking for root explicitly and with a
   `--dry-run` mode for diagnosis.

## Layout

```
msi-mystic                 CLI + --gui launcher (self-elevates with display)
msi-mystic-gui-root        root helper for pkexec
msi_mystic/superio.py      /dev/port, advanced mode, NCT detection
msi_mystic/controller.py   bank 0x12, static + 8 frames
msi_mystic/cli.py          detect|set|off|rainbow|breathing
msi_mystic/gui.py          Qt6, pure black + green accent, 6 custom colors
icons/msi-mystic.svg       RGB bulb icon
requirements.txt           PySide6
msi-mystic.desktop         launcher (@@APP_DIR@@ template)
msi-mystic.service         --user systemd example (@@APP_DIR@@ template)
install.sh                 installer (pacman/apt/dnf, venv, icon, launcher)
```

## Safety

Only bank `0x12` and bit `0x10` of `0x09/0x2C` are ever written, same as
OpenRGB/msi-rgb. Still: confirm `detect --verbose` first, don't run two RGB
programs at once, and if anything looks odd, power off and unplug for 30 s.


