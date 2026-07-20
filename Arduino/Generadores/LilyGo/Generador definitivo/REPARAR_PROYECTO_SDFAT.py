#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repara un proyecto generado por V6/V6.1 que falla por SdFat."""

from pathlib import Path
import re
import shutil
import sys

if len(sys.argv) > 1:
    project = Path(sys.argv[1]).expanduser().resolve()
else:
    project = Path.cwd()

ini = project / "platformio.ini"
main = project / "src" / "main.cpp"

if not ini.exists() or not main.exists():
    raise SystemExit(
        "No se encontró platformio.ini o src/main.cpp.\n"
        "Ejecuta este archivo dentro de la carpeta del proyecto o pasa la ruta."
    )

text = ini.read_text(encoding="utf-8")
text = re.sub(
    r"^\s*adafruit/Adafruit TinyUSB Library@[^\n]+\n",
    "",
    text,
    flags=re.M,
)
text = text.replace("lib_ldf_mode = deep+", "lib_ldf_mode = chain+")
ini.write_text(text, encoding="utf-8")

main_text = main.read_text(encoding="utf-8")
main_text = main_text.replace("#include <Adafruit_TinyUSB.h>\n", "")
main.write_text(main_text, encoding="utf-8")

pio = project / ".pio"
if pio.exists():
    shutil.rmtree(pio)

print("Proyecto reparado correctamente.")
print(f"Ruta: {project}")
print("Ahora vuelve a compilar con PlatformIO.")
