#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador MinerGuard T-Echo GPS AUTO V6.

Genera un proyecto PlatformIO completo basado en:
- MCCI LMIC + SX1262 + UG65 US915 SubBand 2.
- Payload de 46 bytes.
- HR7 latitud, HR8 longitud y HR20 estado de fix GPS.
- GPS automático según RSSI de beacons.
- Recuperación WAKEUP + RESET + PCAS al volver desde modo beacon.
- Compilación y carga desde la misma interfaz usando PlatformIO.

La carga sigue requiriendo colocar manualmente la T-Echo en DFU con
doble clic rápido en RESET.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "MinerGuard T-Echo - Generador GPS AUTO V6.3 CSV + Mouse FIX"
UG65_HEADERS = [
    "name",
    "description",
    "deveui",
    "deviceprofile",
    "application",
    "payloadcodec",
    "fport",
    "appkey",
    "devaddr",
    "nwkskey",
    "appskey",
    "timeout",
]

HEX_RE = re.compile(r"^[0-9A-F]+$")
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def app_root() -> Path:
    """Carpeta del ejecutable/script, compatible con PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def template_root() -> Path:
    root = app_root() / "templates" / "platformio_project"
    if not root.exists():
        raise FileNotFoundError(
            "No se encontró templates/platformio_project. "
            "Mantén el generador dentro de su carpeta completa."
        )
    return root


def sanitize_hex(value: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()


def validate_hex(value: str, bytes_len: int, label: str) -> str:
    cleaned = sanitize_hex(value)
    expected = bytes_len * 2
    if len(cleaned) != expected or not HEX_RE.fullmatch(cleaned):
        raise ValueError(f"{label} debe tener exactamente {expected} caracteres hexadecimales.")
    return cleaned


def random_hex(bytes_len: int) -> str:
    return secrets.token_hex(bytes_len).upper()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "tag"


def c_escape(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def hex_to_c_array(value: str, reverse: bool = False) -> str:
    value = sanitize_hex(value)
    parts = [value[i:i + 2] for i in range(0, len(value), 2)]
    if reverse:
        parts.reverse()
    return ", ".join(f"0x{x}" for x in parts)


def mac_arrays(mac: str) -> tuple[str, str]:
    parts = [int(x, 16) for x in mac.upper().split(":")]
    normal = ", ".join(f"0x{x:02X}" for x in parts)
    reverse = ", ".join(f"0x{x:02X}" for x in reversed(parts))
    return normal, reverse


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"No se pudo modificar la plantilla: {label}")
    return updated


def detect_platformio() -> Path | None:
    candidates: list[Path] = []

    if os.name == "nt":
        candidates.append(Path.home() / ".platformio" / "penv" / "Scripts" / "platformio.exe")
    else:
        candidates.append(Path.home() / ".platformio" / "penv" / "bin" / "platformio")

    for name in ("platformio", "pio"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return None


@dataclass
class GeneratorConfig:
    node_id: int
    person_name: str
    ble_name: str
    band_prefix: str
    band_name: str
    band_mac: str

    dev_eui: str
    app_eui: str
    app_key: str
    app_port: int

    tx_interval_ms: int
    scanner_rssi_filter: int
    display_rotation: int

    gps_on_rssi: int
    gps_off_rssi: int
    beacon_recent_ms: int
    switch_confirm_ms: int

    gps_nmea_timeout_ms: int
    gps_recovery_cooldown_ms: int
    gps_recovery_attempts: int

    ug65_application: str
    ug65_deviceprofile: str
    ug65_timeout: int

    project_name: str

    @property
    def env_name(self) -> str:
        return f"minerguard_techo_{self.node_id}_gps_auto"


def validate_config(raw: dict[str, str]) -> GeneratorConfig:
    try:
        node_id = int(raw["node_id"])
    except ValueError as exc:
        raise ValueError("Node ID debe ser un número entero.") from exc

    if not 1 <= node_id <= 65535:
        raise ValueError("Node ID debe estar entre 1 y 65535.")

    person = raw["person_name"].strip()
    if not person:
        raise ValueError("Ingresa el nombre de la persona.")

    ble_name = raw["ble_name"].strip() or str(node_id)

    band_mac = raw["band_mac"].strip().upper()
    if not MAC_RE.fullmatch(band_mac):
        raise ValueError("La MAC de la banda debe usar el formato AA:BB:CC:DD:EE:FF.")

    dev_eui = validate_hex(raw["dev_eui"], 8, "DevEUI")
    app_eui = validate_hex(raw["app_eui"], 8, "AppEUI/JoinEUI")
    app_key = validate_hex(raw["app_key"], 16, "AppKey")

    def number(name: str, label: str) -> int:
        try:
            return int(raw[name])
        except ValueError as exc:
            raise ValueError(f"{label} debe ser un número entero.") from exc

    app_port = number("app_port", "FPort")
    if not 1 <= app_port <= 223:
        raise ValueError("FPort debe estar entre 1 y 223.")

    tx_interval = number("tx_interval_ms", "Intervalo TX")
    if tx_interval < 5000:
        raise ValueError("El intervalo TX debe ser de al menos 5000 ms.")

    scanner_filter = number("scanner_rssi_filter", "Filtro RSSI scanner")
    if not -120 <= scanner_filter <= -20:
        raise ValueError("El filtro RSSI del scanner debe estar entre -120 y -20 dBm.")

    rotation = number("display_rotation", "Rotación")
    if rotation not in (0, 1, 2, 3):
        raise ValueError("La rotación de pantalla debe ser 0, 1, 2 o 3.")

    gps_on = number("gps_on_rssi", "Umbral GPS ON")
    gps_off = number("gps_off_rssi", "Umbral GPS OFF")
    if gps_on >= gps_off:
        raise ValueError(
            "GPS ON debe ser más negativo que GPS OFF. "
            "Ejemplo recomendado: ON=-94 y OFF=-85."
        )

    recent_ms = number("beacon_recent_ms", "Tiempo beacon reciente")
    confirm_ms = number("switch_confirm_ms", "Confirmación de cambio")
    nmea_timeout = number("gps_nmea_timeout_ms", "Timeout NMEA")
    recovery_cooldown = number("gps_recovery_cooldown_ms", "Cooldown recovery")
    recovery_attempts = number("gps_recovery_attempts", "Intentos recovery")

    if recent_ms < 1000:
        raise ValueError("Beacon reciente debe ser de al menos 1000 ms.")
    if confirm_ms < 200:
        raise ValueError("La confirmación de cambio debe ser de al menos 200 ms.")
    if nmea_timeout < 3000:
        raise ValueError("Timeout NMEA debe ser de al menos 3000 ms.")
    if recovery_cooldown < 3000:
        raise ValueError("Cooldown recovery debe ser de al menos 3000 ms.")
    if not 1 <= recovery_attempts <= 10:
        raise ValueError("Intentos recovery debe estar entre 1 y 10.")

    if not raw["ug65_application"].strip():
        raise ValueError("La aplicación UG65 no puede estar vacía.")
    if not raw["ug65_deviceprofile"].strip():
        raise ValueError("El Device Profile UG65 no puede estar vacío.")

    project_name = raw["project_name"].strip()
    if not project_name:
        project_name = f"PlatformIO_Minerguard_TEcho_{node_id}_GPS_AUTO_V3"
    project_name = safe_name(project_name)

    return GeneratorConfig(
        node_id=node_id,
        person_name=person,
        ble_name=ble_name,
        band_prefix=raw["band_prefix"].strip(),
        band_name=raw["band_name"].strip(),
        band_mac=band_mac,
        dev_eui=dev_eui,
        app_eui=app_eui,
        app_key=app_key,
        app_port=app_port,
        tx_interval_ms=tx_interval,
        scanner_rssi_filter=scanner_filter,
        display_rotation=rotation,
        gps_on_rssi=gps_on,
        gps_off_rssi=gps_off,
        beacon_recent_ms=recent_ms,
        switch_confirm_ms=confirm_ms,
        gps_nmea_timeout_ms=nmea_timeout,
        gps_recovery_cooldown_ms=recovery_cooldown,
        gps_recovery_attempts=recovery_attempts,
        ug65_application=raw["ug65_application"].strip(),
        ug65_deviceprofile=raw["ug65_deviceprofile"].strip(),
        ug65_timeout=number("ug65_timeout", "Timeout UG65"),
        project_name=project_name,
    )


def patch_main_cpp(code: str, cfg: GeneratorConfig) -> str:
    normal_mac, reverse_mac = mac_arrays(cfg.band_mac)

    code = replace_once(
        code,
        r"static const uint16_t NODE_ID = \d+;",
        f"static const uint16_t NODE_ID = {cfg.node_id};",
        "NODE_ID",
    )
    code = replace_once(
        code,
        r'static const char PERSON_NAME\[\] = ".*?";',
        f'static const char PERSON_NAME[] = "{c_escape(cfg.person_name)}";',
        "PERSON_NAME",
    )
    code = replace_once(
        code,
        r'static const char NODE_LABEL\[\]\s*=\s*".*?";',
        f'static const char NODE_LABEL[]  = "{c_escape(cfg.ble_name)}";',
        "NODE_LABEL",
    )

    code = replace_once(
        code,
        r'static const char BAND_MAC_TARGET\[\] = ".*?";',
        f'static const char BAND_MAC_TARGET[] = "{cfg.band_mac}";',
        "BAND_MAC_TARGET",
    )
    code = replace_once(
        code,
        r"static const uint8_t BAND_MAC_NORMAL\[6\]\s*=\s*\{.*?\};",
        f"static const uint8_t BAND_MAC_NORMAL[6]   = {{ {normal_mac} }};",
        "BAND_MAC_NORMAL",
    )
    code = replace_once(
        code,
        r"static const uint8_t BAND_MAC_REVERSED\[6\]\s*=\s*\{.*?\};",
        f"static const uint8_t BAND_MAC_REVERSED[6] = {{ {reverse_mac} }};",
        "BAND_MAC_REVERSED",
    )

    code = replace_once(
        code,
        r"static const uint8_t LORAWAN_APP_PORT = \d+;",
        f"static const uint8_t LORAWAN_APP_PORT = {cfg.app_port};",
        "FPort",
    )
    code = replace_once(
        code,
        r"static const u1_t PROGMEM APPEUI\[8\]\s*=\s*\{.*?\};",
        "static const u1_t PROGMEM APPEUI[8] = { "
        + hex_to_c_array(cfg.app_eui, reverse=True)
        + " };",
        "APPEUI",
    )
    code = replace_once(
        code,
        r"static const u1_t PROGMEM DEVEUI\[8\]\s*=\s*\{.*?\};",
        "static const u1_t PROGMEM DEVEUI[8] = { "
        + hex_to_c_array(cfg.dev_eui, reverse=True)
        + " };",
        "DEVEUI",
    )
    code = replace_once(
        code,
        r"static const u1_t PROGMEM APPKEY\[16\]\s*=\s*\{.*?\};",
        "static const u1_t PROGMEM APPKEY[16] = { "
        + hex_to_c_array(cfg.app_key)
        + " };",
        "APPKEY",
    )

    code = replace_once(
        code,
        r'char scrLine3\[32\] = ".*?";',
        f'char scrLine3[32] = "{c_escape(cfg.person_name)}";',
        "nombre inicial pantalla",
    )
    code = replace_once(
        code,
        r'SerialMon\.println\("[0-9A-Fa-f]{16}"\);',
        f'SerialMon.println("{cfg.dev_eui}");',
        "DevEUI visible en boot",
    )

    code = replace_once(
        code,
        r"static const uint32_t TX_INTERVAL_MS = \d+;",
        f"static const uint32_t TX_INTERVAL_MS = {cfg.tx_interval_ms};",
        "TX_INTERVAL_MS",
    )
    code = replace_once(
        code,
        r"Bluefruit\.Scanner\.filterRssi\(-?\d+\);",
        f"Bluefruit.Scanner.filterRssi({cfg.scanner_rssi_filter});",
        "filtro scanner RSSI",
    )
    code = replace_once(
        code,
        r"display->setRotation\(\d+\);",
        f"display->setRotation({cfg.display_rotation});",
        "rotación de pantalla",
    )
    code = replace_once(
        code,
        r'SerialMon\.println\("\[DISPLAY\] Rotacion forzada: \d+"\);',
        f'SerialMon.println("[DISPLAY] Rotacion forzada: {cfg.display_rotation}");',
        "log de rotación",
    )

    code = replace_once(
        code,
        r"static const int8_t GPS_ON_BEACON_RSSI_DBM\s*=\s*-?\d+;",
        f"static const int8_t GPS_ON_BEACON_RSSI_DBM   = {cfg.gps_on_rssi};",
        "umbral GPS ON",
    )
    code = replace_once(
        code,
        r"static const int8_t GPS_OFF_BEACON_RSSI_DBM\s*=\s*-?\d+;",
        f"static const int8_t GPS_OFF_BEACON_RSSI_DBM  = {cfg.gps_off_rssi};",
        "umbral GPS OFF",
    )
    code = replace_once(
        code,
        r"static const uint32_t BEACON_SWITCH_RECENT_MS\s*=\s*\d+;",
        f"static const uint32_t BEACON_SWITCH_RECENT_MS = {cfg.beacon_recent_ms};",
        "beacon reciente",
    )
    code = replace_once(
        code,
        r"static const uint32_t GPS_SWITCH_CONFIRM_MS\s*=\s*\d+;",
        f"static const uint32_t GPS_SWITCH_CONFIRM_MS   = {cfg.switch_confirm_ms};",
        "confirmación de cambio",
    )
    code = replace_once(
        code,
        r"static const uint32_t GPS_NMEA_START_TIMEOUT_MS\s*=\s*\d+;",
        f"static const uint32_t GPS_NMEA_START_TIMEOUT_MS = {cfg.gps_nmea_timeout_ms};",
        "timeout NMEA",
    )
    code = replace_once(
        code,
        r"static const uint32_t GPS_RECOVERY_COOLDOWN_MS\s*=\s*\d+;",
        f"static const uint32_t GPS_RECOVERY_COOLDOWN_MS = {cfg.gps_recovery_cooldown_ms};",
        "cooldown recovery",
    )
    code = replace_once(
        code,
        r"static const uint8_t GPS_MAX_RECOVERY_ATTEMPTS\s*=\s*\d+;",
        f"static const uint8_t GPS_MAX_RECOVERY_ATTEMPTS = {cfg.gps_recovery_attempts};",
        "intentos recovery",
    )

    code = code.replace(
        "[BOOT] SKETCH: V9 GPS AUTO + WAKE RECOVERY",
        "[BOOT] SKETCH GENERADO POR: V6_GPS_AUTO_PLATFORMIO",
    )

    return code


def patch_platformio_ini(text: str, cfg: GeneratorConfig) -> str:
    # El firmware no usa directamente Adafruit TinyUSB.
    # La dependencia externa arrastraba Adafruit SPIFlash y SdFat,
    # provocando fallos de compilación innecesarios.
    text = re.sub(
        r"^\s*adafruit/Adafruit TinyUSB Library@[^\n]+\n",
        "",
        text,
        flags=re.M,
    )
    text = text.replace("lib_ldf_mode = deep+", "lib_ldf_mode = chain+")

    text = re.sub(
        r"^default_envs\s*=\s*.*$",
        f"default_envs = {cfg.env_name}",
        text,
        count=1,
        flags=re.M,
    )
    text = re.sub(
        r"^\[env:[^\]]+\]$",
        f"[env:{cfg.env_name}]",
        text,
        count=1,
        flags=re.M,
    )
    text = re.sub(
        r"^; PlatformIO - .*$",
        f"; PlatformIO - MinerGuard T-Echo {cfg.node_id} GPS AUTO V3",
        text,
        count=1,
        flags=re.M,
    )
    return text


def write_registry_csv(output_root: Path, cfg: GeneratorConfig, project_dir: Path) -> Path:
    path = output_root / "registro_interno_minerguard.csv"
    headers = [
        "created_at",
        "node_id",
        "person_name",
        "ble_name",
        "band_prefix",
        "band_name",
        "band_mac",
        "devEUI",
        "appEUI",
        "appKey",
        "fport",
        "tx_interval_ms",
        "scanner_rssi_filter",
        "gps_on_rssi",
        "gps_off_rssi",
        "beacon_recent_ms",
        "switch_confirm_ms",
        "gps_nmea_timeout_ms",
        "gps_recovery_cooldown_ms",
        "gps_recovery_attempts",
        "project_path",
    ]

    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        if not exists:
            writer.writeheader()
        row = asdict(cfg)
        row["created_at"] = dt.datetime.now().isoformat(timespec="seconds")
        row["devEUI"] = row.pop("dev_eui")
        row["appEUI"] = row.pop("app_eui")
        row["appKey"] = row.pop("app_key")
        row["fport"] = row.pop("app_port")
        row["project_path"] = str(project_dir)
        writer.writerow({key: row.get(key, "") for key in headers})

    return path



def make_ug65_row(cfg: GeneratorConfig) -> dict[str, str]:
    """Fila exacta compatible con los CSV exportados/importados por UG65."""
    return {
        "name": str(cfg.node_id),
        "description": cfg.person_name,
        "deveui": cfg.dev_eui.lower(),
        "deviceprofile": cfg.ug65_deviceprofile,
        "application": cfg.ug65_application,
        "payloadcodec": "",
        "fport": str(cfg.app_port),
        "appkey": cfg.app_key.lower(),
        "devaddr": "",
        "nwkskey": "",
        "appskey": "",
        "timeout": str(cfg.ug65_timeout),
    }


def read_ug65_rows(path: Path) -> list[dict[str, str]]:
    """Lee UTF-8 con o sin BOM y exige el orden exacto de columnas UG65."""
    if not path.exists() or path.stat().st_size == 0:
        return []

    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        actual = reader.fieldnames or []

        if actual != UG65_HEADERS:
            raise ValueError(
                "El CSV seleccionado no tiene el formato UG65 esperado.\n\n"
                f"Encabezado encontrado:\n{','.join(actual)}\n\n"
                f"Encabezado requerido:\n{','.join(UG65_HEADERS)}"
            )

        rows: list[dict[str, str]] = []
        for raw in reader:
            rows.append({key: (raw.get(key) or "") for key in UG65_HEADERS})
        return rows


def write_ug65_rows_exact(path: Path, rows: list[dict[str, str]]) -> Path:
    """Escribe coma, UTF-8 sin BOM, CRLF y orden exacto de columnas."""
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=UG65_HEADERS,
            extrasaction="ignore",
            lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in UG65_HEADERS})

    temp_path.replace(path)
    return path


def write_ug65_csv(path: Path, cfg: GeneratorConfig) -> tuple[Path, str]:
    """
    Actualiza o agrega el TAG sin duplicar.

    Coincidencias:
    - mismo name / Node ID, o
    - mismo DevEUI.
    """
    path = path.expanduser().resolve()
    rows = read_ug65_rows(path)
    new_row = make_ug65_row(cfg)

    replaced = False
    for index, row in enumerate(rows):
        same_name = row.get("name", "").strip() == new_row["name"]
        same_deveui = (
            sanitize_hex(row.get("deveui", ""))
            == sanitize_hex(new_row["deveui"])
        )

        if same_name or same_deveui:
            rows[index] = new_row
            replaced = True
            break

    if not replaced:
        rows.append(new_row)

    write_ug65_rows_exact(path, rows)
    return path, ("actualizado" if replaced else "agregado")


def write_single_ug65_csv(project_dir: Path, cfg: GeneratorConfig) -> Path:
    """CSV con una sola fila, listo para importar únicamente este TAG."""
    path = project_dir / f"UG65_TAG_{cfg.node_id}_IMPORT.csv"
    return write_ug65_rows_exact(path, [make_ug65_row(cfg)])


def validate_ug65_csv_file(path: Path) -> tuple[int, list[dict[str, str]]]:
    rows = read_ug65_rows(path)
    return len(rows), rows


def create_batch_files(project_dir: Path, cfg: GeneratorConfig, pio_path: Path | None) -> None:
    pio = str(pio_path) if pio_path else r"%USERPROFILE%\.platformio\penv\Scripts\platformio.exe"
    env = cfg.env_name

    files = {
        "01_LIMPIAR_Y_COMPILAR.bat": f"""@echo off
cd /d "%~dp0"
"{pio}" run -e {env} -t clean
if errorlevel 1 pause & exit /b 1
"{pio}" run -e {env}
pause
""",
        "02_SUBIR_DFU.bat": f"""@echo off
cd /d "%~dp0"
echo Haz DOBLE CLIC rapido en RESET para poner la T-Echo en DFU.
pause
"{pio}" run -e {env} -t upload
pause
""",
        "03_MONITOR_SERIE.bat": f"""@echo off
cd /d "%~dp0"
"{pio}" device monitor -e {env} -b 115200
pause
""",
    }

    for name, content in files.items():
        (project_dir / name).write_text(content, encoding="utf-8")


def generate_project(
    cfg: GeneratorConfig,
    output_root: Path,
    ug65_csv_path: Path | None = None,
) -> Path:
    source = template_root()
    output_root.mkdir(parents=True, exist_ok=True)
    project_dir = output_root / cfg.project_name

    if project_dir.exists():
        shutil.rmtree(project_dir)
    shutil.copytree(source, project_dir)

    main_path = project_dir / "src" / "main.cpp"
    main_code = patch_main_cpp(main_path.read_text(encoding="utf-8"), cfg)
    main_code = main_code.replace("#include <Adafruit_TinyUSB.h>\n", "")
    main_path.write_text(main_code, encoding="utf-8")

    ini_path = project_dir / "platformio.ini"
    ini_path.write_text(
        patch_platformio_ini(ini_path.read_text(encoding="utf-8"), cfg),
        encoding="utf-8",
    )

    for old in project_dir.glob("TAG*_CONFIG.txt"):
        old.unlink()

    config_text = f"""MINERGUARD T-ECHO GPS AUTO V6

IDENTIDAD
NODE_ID={cfg.node_id}
PERSON_NAME={cfg.person_name}
NODE_LABEL={cfg.ble_name}
BAND_NAME_PREFIX={cfg.band_prefix}
BAND_NAME={cfg.band_name}
BAND_MAC_TARGET={cfg.band_mac}

LORAWAN
DevEUI visible UG65={cfg.dev_eui}
DEVEUI LMIC little-endian={hex_to_c_array(cfg.dev_eui, reverse=True)}
JoinEUI/AppEUI={cfg.app_eui}
AppKey={cfg.app_key}
FPort={cfg.app_port}
US915 SubBand 2

SELECTOR BEACON/GPS
GPS ON: sin beacon reciente o RSSI <= {cfg.gps_on_rssi} dBm
GPS OFF: beacon reciente y RSSI >= {cfg.gps_off_rssi} dBm
Beacon reciente={cfg.beacon_recent_ms} ms
Confirmación={cfg.switch_confirm_ms} ms
Filtro scanner={cfg.scanner_rssi_filter} dBm

RECOVERY GPS
Timeout NMEA={cfg.gps_nmea_timeout_ms} ms
Cooldown={cfg.gps_recovery_cooldown_ms} ms
Intentos={cfg.gps_recovery_attempts}

PAYLOAD
46 bytes
HR7=latitud
HR8=longitud
HR20=fix GPS válido
flags 0x10=GPS válido
flags 0x20=GPS encendido/buscando

PLATFORMIO
Environment={cfg.env_name}
"""
    (project_dir / f"TAG{cfg.node_id}_CONFIG.txt").write_text(config_text, encoding="utf-8")

    readme = f"""# MinerGuard T-Echo TAG {cfg.node_id}

Proyecto generado automáticamente con el generador GPS AUTO V6.

## Identidad

```text
NODE_ID: {cfg.node_id}
Nombre: {cfg.person_name}
BLE: {cfg.ble_name}
Prefijo banda: {cfg.band_prefix}
Nombre banda: {cfg.band_name}
MAC banda: {cfg.band_mac}
DevEUI: {cfg.dev_eui}
AppEUI: {cfg.app_eui}
AppKey: {cfg.app_key}
```

## Compilar

```powershell
& "$env:USERPROFILE\\.platformio\\penv\\Scripts\\platformio.exe" run -e {cfg.env_name}
```

## Subir

Haz doble clic rápido en RESET para entrar en DFU:

```powershell
& "$env:USERPROFILE\\.platformio\\penv\\Scripts\\platformio.exe" run -e {cfg.env_name} -t upload
```

## Monitor

```powershell
& "$env:USERPROFILE\\.platformio\\penv\\Scripts\\platformio.exe" device monitor -e {cfg.env_name} -b 115200
```
"""
    (project_dir / "README_GENERADO.md").write_text(readme, encoding="utf-8")

    pio = detect_platformio()
    create_batch_files(project_dir, cfg, pio)

    # Registro técnico interno. NO se importa en el UG65.
    write_registry_csv(output_root, cfg, project_dir)

    # CSV colectivo seleccionado por el usuario y CSV individual por TAG.
    selected_csv = (
        ug65_csv_path.expanduser()
        if ug65_csv_path is not None
        else output_root / "ug65_bulk_import_devices.csv"
    )
    write_ug65_csv(selected_csv, cfg)
    write_single_ug65_csv(project_dir, cfg)

    return project_dir


class GeneratorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1060x890")
        self.root.minsize(900, 700)

        self.last_project: Path | None = None
        self.last_config: GeneratorConfig | None = None
        self.process_running = False
        self.output_queue: queue.Queue[str] = queue.Queue()

        default_output = Path.home() / "Documents" / "Tomas" / "pruebalilygo"
        if not default_output.parent.exists():
            default_output = Path.cwd()

        self.vars: dict[str, tk.StringVar] = {
            "output_dir": tk.StringVar(value=str(default_output)),
            "project_name": tk.StringVar(value="PlatformIO_Minerguard_TEcho_6_GPS_AUTO_V3"),
            "node_id": tk.StringVar(value="6"),
            "person_name": tk.StringVar(value="Hector Quiroz"),
            "ble_name": tk.StringVar(value="6"),
            "band_prefix": tk.StringVar(value="H1_"),
            "band_name": tk.StringVar(value=""),
            "band_mac": tk.StringVar(value="E5:FD:8A:F2:F3:AF"),
            "final_output_path": tk.StringVar(value=""),
            "dev_eui": tk.StringVar(value=random_hex(8)),
            "app_eui": tk.StringVar(value="0000000000000000"),
            "app_key": tk.StringVar(value=random_hex(16)),
            "app_port": tk.StringVar(value="1"),
            "tx_interval_ms": tk.StringVar(value="15000"),
            "scanner_rssi_filter": tk.StringVar(value="-100"),
            "display_rotation": tk.StringVar(value="3"),
            "gps_on_rssi": tk.StringVar(value="-94"),
            "gps_off_rssi": tk.StringVar(value="-85"),
            "beacon_recent_ms": tk.StringVar(value="7000"),
            "switch_confirm_ms": tk.StringVar(value="1500"),
            "gps_nmea_timeout_ms": tk.StringVar(value="10000"),
            "gps_recovery_cooldown_ms": tk.StringVar(value="15000"),
            "gps_recovery_attempts": tk.StringVar(value="3"),
            "ug65_application": tk.StringVar(value="LilyGo"),
            "ug65_deviceprofile": tk.StringVar(value="ClassA-OTAA"),
            "ug65_timeout": tk.StringVar(value="1440"),
            "ug65_csv_path": tk.StringVar(
                value=str(default_output / "ug65_bulk_import_devices.csv")
            ),
            "platformio_path": tk.StringVar(
                value=str(detect_platformio() or "NO ENCONTRADO")
            ),
        }

        self.ble_scan_enabled = tk.BooleanVar(value=True)
        self._last_auto_ug65_csv = str(
            default_output / "ug65_bulk_import_devices.csv"
        )

        self._build_ui()
        self.vars["node_id"].trace_add("write", self._node_changed)
        self.vars["output_dir"].trace_add("write", lambda *_: self._on_output_dir_changed())
        self.vars["project_name"].trace_add("write", lambda *_: self._update_output_preview())
        self._update_output_preview()
        self.root.after(100, self._drain_output_queue)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        self.scroll_canvas = canvas
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = ttk.Frame(canvas, padding=12)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window, width=event.width),
        )

        # Rueda del mouse compatible con Windows, touchpad y Linux.
        self.root.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_mousewheel_linux_up, add="+")
        self.root.bind_all("<Button-5>", self._on_mousewheel_linux_down, add="+")
        canvas.bind("<Button-1>", lambda _event: canvas.focus_set())
        canvas.bind("<Prior>", lambda _event: canvas.yview_scroll(-8, "units"))
        canvas.bind("<Next>", lambda _event: canvas.yview_scroll(8, "units"))

        ttk.Label(
            frame,
            text="Generador MinerGuard T-Echo GPS AUTO V6.3",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text=(
                "Genera proyecto PlatformIO, CSV UG65 y permite compilar/subir. "
                "La carga requiere doble clic en RESET para DFU."
            ),
        ).pack(anchor="w", pady=(2, 10))

        output_box = ttk.LabelFrame(frame, text="Carpeta de destino", padding=10)
        output_box.pack(fill="x", pady=5)
        self._entry(output_box, "Carpeta base", "output_dir", 0, width=76)
        ttk.Button(
            output_box,
            text="Elegir carpeta",
            command=self._choose_output,
        ).grid(row=0, column=2, padx=5)
        self._entry(output_box, "Nombre del proyecto", "project_name", 1, width=60)
        ttk.Label(output_box, text="Ruta final").grid(row=2, column=0, sticky="nw", padx=4, pady=3)
        ttk.Label(
            output_box,
            textvariable=self.vars["final_output_path"],
            wraplength=720,
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=4, pady=3)
        ttk.Button(
            output_box,
            text="Abrir carpeta base",
            command=self.open_output_base,
        ).grid(row=3, column=1, sticky="w", padx=4, pady=5)

        identity = ttk.LabelFrame(frame, text="Identidad del TAG", padding=10)
        identity.pack(fill="x", pady=5)
        self._entry(identity, "Node ID", "node_id", 0)
        self._entry(identity, "Nombre persona", "person_name", 1, width=38)
        self._entry(identity, "Nombre BLE del TAG", "ble_name", 2)

        ble_box = ttk.LabelFrame(frame, text="Banda cardíaca y escaneo Bluetooth", padding=10)
        ble_box.pack(fill="x", pady=5)
        self._entry(ble_box, "Prefijo de nombre BLE", "band_prefix", 0, width=24)
        self._entry(ble_box, "Nombre detectado", "band_name", 1, width=38)
        self._entry(ble_box, "MAC banda cardíaca", "band_mac", 2, width=24)
        ttk.Checkbutton(
            ble_box,
            text="Habilitar búsqueda de bandas por Bluetooth del computador",
            variable=self.ble_scan_enabled,
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=4, pady=(6, 3))
        ttk.Button(
            ble_box,
            text="Buscar bandas BLE",
            command=self.scan_ble_devices,
        ).grid(row=4, column=0, sticky="w", padx=4, pady=4)
        ttk.Label(
            ble_box,
            text="Requiere Bluetooth en el PC y el paquete Python bleak.",
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=4)

        otaa = ttk.LabelFrame(frame, text="LoRaWAN OTAA / UG65", padding=10)
        otaa.pack(fill="x", pady=5)
        self._entry(otaa, "DevEUI", "dev_eui", 0, width=30)
        ttk.Button(otaa, text="Generar", command=self._new_deveui).grid(row=0, column=2, padx=5)
        self._entry(otaa, "AppEUI / JoinEUI", "app_eui", 1, width=30)
        self._entry(otaa, "AppKey", "app_key", 2, width=42)
        ttk.Button(otaa, text="Generar", command=self._new_appkey).grid(row=2, column=2, padx=5)
        self._entry(otaa, "FPort", "app_port", 3)

        ttk.Label(otaa, text="Aplicación UG65").grid(
            row=4, column=0, sticky="w", padx=4, pady=3
        )
        application_combo = ttk.Combobox(
            otaa,
            textvariable=self.vars["ug65_application"],
            values=("LilyGo", "Sense_T1000"),
            width=25,
            state="normal",
        )
        application_combo.grid(row=4, column=1, sticky="w", padx=4, pady=3)

        self._entry(otaa, "Device Profile UG65", "ug65_deviceprofile", 5, width=28)
        self._entry(otaa, "Timeout UG65", "ug65_timeout", 6)

        self._entry(otaa, "Archivo CSV importable UG65", "ug65_csv_path", 7, width=68)
        ttk.Button(
            otaa,
            text="Elegir / cargar CSV",
            command=self._choose_ug65_csv,
        ).grid(row=7, column=2, padx=5)

        csv_buttons = ttk.Frame(otaa)
        csv_buttons.grid(row=8, column=0, columnspan=3, sticky="w", padx=4, pady=5)
        ttk.Button(
            csv_buttons,
            text="Usar CSV nuevo en destino",
            command=self._reset_ug65_csv_path,
        ).pack(side="left")
        ttk.Button(
            csv_buttons,
            text="Validar formato CSV",
            command=self._validate_selected_ug65_csv,
        ).pack(side="left", padx=6)
        ttk.Button(
            csv_buttons,
            text="Abrir ubicación CSV",
            command=self._open_ug65_csv_location,
        ).pack(side="left")

        ttk.Label(
            otaa,
            text=(
                "Formato exacto: name,description,deveui,deviceprofile,"
                "application,payloadcodec,fport,appkey,devaddr,nwkskey,"
                "appskey,timeout"
            ),
            wraplength=760,
        ).grid(row=9, column=0, columnspan=3, sticky="w", padx=4, pady=(2, 4))

        firmware = ttk.LabelFrame(frame, text="Firmware general", padding=10)
        firmware.pack(fill="x", pady=5)
        self._entry(firmware, "Intervalo TX (ms)", "tx_interval_ms", 0)
        self._entry(firmware, "Filtro scanner RSSI", "scanner_rssi_filter", 1)
        self._entry(firmware, "Rotación pantalla", "display_rotation", 2)

        selector = ttk.LabelFrame(frame, text="Selector automático Beacon / GPS", padding=10)
        selector.pack(fill="x", pady=5)
        self._entry(selector, "GPS ON si RSSI <=", "gps_on_rssi", 0)
        self._entry(selector, "GPS OFF si RSSI >=", "gps_off_rssi", 1)
        self._entry(selector, "Beacon reciente (ms)", "beacon_recent_ms", 2)
        self._entry(selector, "Confirmación cambio (ms)", "switch_confirm_ms", 3)

        recovery = ttk.LabelFrame(frame, text="Recuperación del GPS", padding=10)
        recovery.pack(fill="x", pady=5)
        self._entry(recovery, "Timeout inicio NMEA (ms)", "gps_nmea_timeout_ms", 0)
        self._entry(recovery, "Cooldown recovery (ms)", "gps_recovery_cooldown_ms", 1)
        self._entry(recovery, "Intentos máximos", "gps_recovery_attempts", 2)

        pio_box = ttk.LabelFrame(frame, text="PlatformIO", padding=10)
        pio_box.pack(fill="x", pady=5)
        self._entry(pio_box, "Ejecutable detectado", "platformio_path", 0, width=76)
        ttk.Button(pio_box, text="Buscar ejecutable", command=self._choose_platformio).grid(
            row=0, column=2, padx=5
        )

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)

        actions = [
            ("Generar proyecto", self.generate_only),
            ("Generar + compilar", self.generate_and_compile),
            ("Generar + compilar + subir", self.generate_compile_upload),
            ("Limpiar", self.clean_last),
            ("Compilar", self.compile_last),
            ("Subir", self.upload_last),
            ("Monitor serie", self.monitor_last),
            ("Abrir carpeta", self.open_last),
            ("Exportar CSV UG65", self.export_ug65_only),
        ]

        for index, (label, command) in enumerate(actions):
            ttk.Button(buttons, text=label, command=command).grid(
                row=index // 3,
                column=index % 3,
                padx=4,
                pady=4,
                sticky="ew",
            )

        for col in range(3):
            buttons.columnconfigure(col, weight=1)

        log_box = ttk.LabelFrame(frame, text="Registro", padding=8)
        log_box.pack(fill="both", expand=True, pady=5)
        self.log_widget = tk.Text(log_box, height=16, wrap="word", font=("Consolas", 9))
        self.log_widget.pack(fill="both", expand=True)
        self.log("Generador listo.")
        self.log(f"PlatformIO: {self.vars['platformio_path'].get()}")

    def _entry(
        self,
        parent: ttk.Widget,
        label: str,
        key: str,
        row: int,
        width: int = 20,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=3)
        entry = ttk.Entry(parent, textvariable=self.vars[key], width=width)
        entry.grid(row=row, column=1, sticky="w", padx=4, pady=3)
        return entry

    def log(self, text: str) -> None:
        self.log_widget.insert("end", text.rstrip() + "\n")
        self.log_widget.see("end")

    def _drain_output_queue(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self.log(line)
        self.root.after(100, self._drain_output_queue)

    def _should_main_canvas_scroll(self, event) -> bool:
        try:
            if event.widget.winfo_toplevel() is not self.root:
                return False
        except Exception:
            return False

        # Los campos multilinea y listas mantienen su propio scroll.
        if isinstance(event.widget, (tk.Text, tk.Listbox, ttk.Treeview)):
            return False
        return True

    def _on_mousewheel(self, event):
        if not self._should_main_canvas_scroll(event):
            return None

        delta = getattr(event, "delta", 0)
        if delta == 0:
            return None

        # Funciona también cuando el touchpad entrega valores menores que 120.
        steps = max(1, abs(int(delta)) // 120)
        direction = -1 if delta > 0 else 1
        self.scroll_canvas.yview_scroll(direction * steps, "units")
        return "break"

    def _on_mousewheel_linux_up(self, event):
        if self._should_main_canvas_scroll(event):
            self.scroll_canvas.yview_scroll(-1, "units")
            return "break"
        return None

    def _on_mousewheel_linux_down(self, event):
        if self._should_main_canvas_scroll(event):
            self.scroll_canvas.yview_scroll(1, "units")
            return "break"
        return None

    def _on_output_dir_changed(self) -> None:
        self._update_output_preview()

        current = self.vars["ug65_csv_path"].get().strip()
        new_auto = str(
            Path(self.vars["output_dir"].get().strip() or Path.cwd())
            / "ug65_bulk_import_devices.csv"
        )

        # Solo cambiar automáticamente si el usuario no escogió otro archivo.
        if not current or current == self._last_auto_ug65_csv:
            self.vars["ug65_csv_path"].set(new_auto)

        self._last_auto_ug65_csv = new_auto

    def _selected_ug65_csv_path(self) -> Path:
        raw = self.vars["ug65_csv_path"].get().strip()
        if not raw:
            raw = str(self._output_root() / "ug65_bulk_import_devices.csv")
            self.vars["ug65_csv_path"].set(raw)
        path = Path(raw).expanduser()
        if path.suffix.lower() != ".csv":
            path = path.with_suffix(".csv")
            self.vars["ug65_csv_path"].set(str(path))
        return path

    def _choose_ug65_csv(self) -> None:
        current = self._selected_ug65_csv_path()
        selected = filedialog.asksaveasfilename(
            title="Seleccionar CSV UG65 existente o crear uno nuevo",
            initialdir=str(current.parent),
            initialfile=current.name,
            defaultextension=".csv",
            filetypes=[("CSV UG65", "*.csv"), ("Todos", "*.*")],
        )
        if not selected:
            return

        path = Path(selected)
        if path.exists():
            try:
                count, _rows = validate_ug65_csv_file(path)
                self.log(
                    f"[CSV UG65] Archivo cargado y validado: {path} "
                    f"({count} dispositivos)"
                )
            except Exception as exc:
                messagebox.showerror("CSV UG65 inválido", str(exc))
                self.log(f"[CSV UG65] ERROR: {exc}")
                return
        else:
            self.log(f"[CSV UG65] Se creará un archivo nuevo: {path}")

        self.vars["ug65_csv_path"].set(str(path))

    def _reset_ug65_csv_path(self) -> None:
        path = self._output_root() / "ug65_bulk_import_devices.csv"
        self.vars["ug65_csv_path"].set(str(path))
        self._last_auto_ug65_csv = str(path)
        self.log(f"[CSV UG65] Nuevo archivo en carpeta destino: {path}")

    def _validate_selected_ug65_csv(self) -> None:
        try:
            path = self._selected_ug65_csv_path()
            if not path.exists():
                messagebox.showinfo(
                    "CSV UG65",
                    "El archivo todavía no existe. Se creará con el formato "
                    "correcto al generar o exportar.",
                )
                return

            count, _rows = validate_ug65_csv_file(path)
            messagebox.showinfo(
                "CSV UG65 correcto",
                f"Formato válido.\nDispositivos registrados: {count}\n\n{path}",
            )
            self.log(f"[CSV UG65] Formato válido: {path} | filas={count}")
        except Exception as exc:
            messagebox.showerror("CSV UG65 inválido", str(exc))
            self.log(f"[CSV UG65] ERROR: {exc}")

    def _open_ug65_csv_location(self) -> None:
        try:
            path = self._selected_ug65_csv_path()
            folder = path.parent
            folder.mkdir(parents=True, exist_ok=True)

            if os.name == "nt":
                if path.exists():
                    subprocess.Popen(["explorer", "/select,", str(path)])
                else:
                    os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("CSV UG65", str(exc))

    def _node_changed(self, *_args) -> None:
        node = self.vars["node_id"].get().strip()
        if node.isdigit():
            self.vars["ble_name"].set(node)
            self.vars["project_name"].set(
                f"PlatformIO_Minerguard_TEcho_{node}_GPS_AUTO_V3"
            )
        self._update_output_preview()

    def _choose_output(self) -> None:
        chosen = filedialog.askdirectory(
            title="Seleccionar carpeta base de destino",
            initialdir=self.vars["output_dir"].get() or str(Path.cwd()),
        )
        if chosen:
            self.vars["output_dir"].set(chosen)
            self._update_output_preview()
            self.log(f"[SALIDA] Carpeta base seleccionada: {chosen}")

    def _choose_platformio(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Seleccionar platformio.exe",
            filetypes=[("PlatformIO", "platformio.exe"), ("Ejecutables", "*.exe"), ("Todos", "*.*")],
        )
        if chosen:
            self.vars["platformio_path"].set(chosen)

    def _update_output_preview(self) -> None:
        base = Path(self.vars["output_dir"].get().strip() or Path.cwd()).expanduser()
        project = self.vars["project_name"].get().strip() or "PlatformIO_Minerguard_TEcho"
        self.vars["final_output_path"].set(str(base / safe_name(project)))

    def open_output_base(self) -> None:
        try:
            folder = Path(self.vars["output_dir"].get().strip() or Path.cwd()).expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            messagebox.showerror("Carpeta", str(exc))

    def scan_ble_devices(self) -> None:
        if not self.ble_scan_enabled.get():
            messagebox.showinfo("Bluetooth", "La búsqueda Bluetooth está deshabilitada.")
            return

        try:
            import asyncio
            from bleak import BleakScanner
        except Exception:
            messagebox.showerror(
                "Bluetooth",
                "No se encontró el paquete 'bleak'.\n\n"
                "Ejecuta INSTALAR_BLEAK.bat o instala con:\n"
                "py -3 -m pip install bleak",
            )
            self.log("BLE no disponible: falta instalar bleak.")
            return

        prefix = self.vars["band_prefix"].get().strip()
        self.log(f"[BLE] Escaneo iniciado durante 8 segundos. Prefijo: {prefix or '<todos>'}")

        progress = tk.Toplevel(self.root)
        progress.title("Escaneo Bluetooth")
        progress.geometry("390x135")
        progress.transient(self.root)
        progress.grab_set()

        ttk.Label(
            progress,
            text="Buscando dispositivos Bluetooth LE...",
            font=("Segoe UI", 11, "bold"),
        ).pack(pady=(16, 8))
        ttk.Label(progress, text="Mantén la banda encendida y cerca del computador.").pack()
        bar = ttk.Progressbar(progress, mode="indeterminate", length=300)
        bar.pack(pady=12)
        bar.start(10)

        def worker() -> None:
            async def discover():
                found = await BleakScanner.discover(timeout=8.0, return_adv=True)
                items = []

                # Bleak moderno: dict[address] = (device, advertisement_data)
                if isinstance(found, dict):
                    iterable = found.values()
                else:
                    iterable = [(device, None) for device in found]

                for item in iterable:
                    if isinstance(item, tuple):
                        device, adv = item
                    else:
                        device, adv = item, None

                    name = (
                        getattr(adv, "local_name", None)
                        or getattr(device, "name", None)
                        or ""
                    ).strip()
                    mac = (getattr(device, "address", "") or "").strip().upper()
                    rssi = getattr(adv, "rssi", None)
                    if rssi is None:
                        rssi = getattr(device, "rssi", None)

                    if not mac:
                        continue
                    if prefix and not name.startswith(prefix):
                        continue

                    items.append((name, mac, rssi))

                items.sort(
                    key=lambda row: row[2] if isinstance(row[2], int) else -999,
                    reverse=True,
                )
                return items

            try:
                devices = asyncio.run(discover())
                self.root.after(
                    0,
                    lambda: self._finish_ble_scan(progress, devices, None),
                )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda: self._finish_ble_scan(progress, None, exc),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _finish_ble_scan(self, progress_window, devices, error) -> None:
        try:
            progress_window.grab_release()
            progress_window.destroy()
        except Exception:
            pass

        if error is not None:
            self.log(f"[BLE] ERROR: {error}")
            messagebox.showerror("Bluetooth", f"Falló el escaneo BLE:\n{error}")
            return

        if not devices:
            self.log("[BLE] No se encontraron dispositivos con el filtro indicado.")
            messagebox.showinfo(
                "Bluetooth",
                "No se encontraron dispositivos BLE con ese prefijo.\n"
                "Prueba dejando el prefijo vacío para mostrar todos.",
            )
            return

        picker = tk.Toplevel(self.root)
        picker.title("Seleccionar banda Bluetooth")
        picker.geometry("670x390")
        picker.transient(self.root)

        ttk.Label(
            picker,
            text="Selecciona la banda detectada:",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=10, pady=10)

        columns = ("name", "mac", "rssi")
        tree = ttk.Treeview(picker, columns=columns, show="headings", height=12)
        tree.heading("name", text="Nombre")
        tree.heading("mac", text="MAC / dirección")
        tree.heading("rssi", text="RSSI")
        tree.column("name", width=220)
        tree.column("mac", width=270)
        tree.column("rssi", width=80, anchor="center")
        tree.pack(fill="both", expand=True, padx=10, pady=6)

        for name, mac, rssi in devices:
            tree.insert(
                "",
                "end",
                values=(
                    name or "<sin nombre>",
                    mac,
                    "" if rssi is None else rssi,
                ),
            )

        def use_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("Bluetooth", "Selecciona un dispositivo.")
                return

            values = tree.item(selected[0], "values")
            name = "" if values[0] == "<sin nombre>" else str(values[0])
            mac = str(values[1]).upper()

            # En Windows normalmente Bleak entrega una MAC clásica.
            # En otros sistemas puede entregar un UUID; se advierte al usuario.
            if MAC_RE.fullmatch(mac):
                self.vars["band_mac"].set(mac)
            else:
                self.log(
                    "[BLE] La dirección detectada no tiene formato MAC. "
                    "Ingresa manualmente la MAC real de la banda."
                )
                messagebox.showwarning(
                    "Bluetooth",
                    "El sistema entregó una dirección que no tiene formato MAC.\n"
                    "Se copiará el nombre, pero deberás ingresar manualmente la MAC.",
                )

            self.vars["band_name"].set(name)
            self.log(
                f"[BLE] Banda seleccionada: {name or '<sin nombre>'} / {mac}"
            )
            picker.destroy()

        button_row = ttk.Frame(picker)
        button_row.pack(fill="x", padx=10, pady=10)
        ttk.Button(
            button_row,
            text="Usar selección",
            command=use_selected,
        ).pack(side="left")
        ttk.Button(
            button_row,
            text="Cancelar",
            command=picker.destroy,
        ).pack(side="left", padx=8)

    def _new_deveui(self) -> None:
        self.vars["dev_eui"].set(random_hex(8))

    def _new_appkey(self) -> None:
        self.vars["app_key"].set(random_hex(16))

    def _raw_config(self) -> dict[str, str]:
        return {key: value.get() for key, value in self.vars.items()}

    def _current_config(self) -> GeneratorConfig:
        return validate_config(self._raw_config())

    def _output_root(self) -> Path:
        return Path(self.vars["output_dir"].get().strip() or Path.cwd()).expanduser()

    def _generate(self) -> tuple[GeneratorConfig, Path]:
        cfg = self._current_config()
        ug65_csv = self._selected_ug65_csv_path()
        project = generate_project(cfg, self._output_root(), ug65_csv)
        self.last_config = cfg
        self.last_project = project

        self.log("=" * 70)
        self.log("PROYECTO GENERADO")
        self.log(f"Ruta: {project}")
        self.log(f"Environment: {cfg.env_name}")
        self.log(f"DevEUI: {cfg.dev_eui}")
        self.log(f"AppKey: {cfg.app_key}")
        self.log("Payload: 46 bytes | HR7 lat | HR8 lon | HR20 fix GPS")
        self.log(f"CSV UG65 IMPORTABLE: {ug65_csv}")
        self.log(
            f"CSV UG65 INDIVIDUAL: "
            f"{project / f'UG65_TAG_{cfg.node_id}_IMPORT.csv'}"
        )
        self.log(
            f"Registro interno (NO importar al UG65): "
            f"{self._output_root() / 'registro_interno_minerguard.csv'}"
        )
        self.log("=" * 70)
        return cfg, project

    def export_ug65_only(self) -> None:
        try:
            cfg = self._current_config()
            path = self._selected_ug65_csv_path()
            final_path, action = write_ug65_csv(path, cfg)

            self.log(
                f"[CSV UG65] TAG {cfg.node_id} {action}: {final_path}"
            )
            messagebox.showinfo(
                "CSV UG65 exportado",
                f"TAG {cfg.node_id} {action} correctamente.\n\n"
                f"Archivo importable:\n{final_path}\n\n"
                f"Aplicación: {cfg.ug65_application}",
            )
        except Exception as exc:
            self.log(f"[CSV UG65] ERROR: {exc}")
            messagebox.showerror("CSV UG65", str(exc))

    def generate_only(self) -> None:
        try:
            _cfg, project = self._generate()
            messagebox.showinfo("Generado", f"Proyecto creado:\n{project}")
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Error", str(exc))

    def _platformio_path(self) -> Path:
        raw = self.vars["platformio_path"].get().strip()
        candidate = Path(raw).expanduser()
        if candidate.exists():
            return candidate

        detected = detect_platformio()
        if detected:
            self.vars["platformio_path"].set(str(detected))
            return detected

        raise FileNotFoundError(
            "No se encontró PlatformIO. Instálalo o selecciona platformio.exe."
        )

    def _ensure_last(self) -> tuple[GeneratorConfig, Path]:
        if self.last_config and self.last_project and self.last_project.exists():
            return self.last_config, self.last_project

        cfg = self._current_config()
        project = self._output_root() / cfg.project_name
        if not project.exists():
            raise FileNotFoundError("Primero genera el proyecto.")
        self.last_config = cfg
        self.last_project = project
        return cfg, project

    def _clean_legacy_dependency_residue(self, project: Path) -> None:
        """Elimina dependencias descargadas por versiones anteriores del generador."""
        candidates = [
            project / ".pio" / "libdeps",
            project / ".pio" / "build",
        ]

        for candidate in candidates:
            if candidate.exists():
                try:
                    shutil.rmtree(candidate)
                    self.log(f"[DEPENDENCIAS] Limpieza automática: {candidate}")
                except Exception as exc:
                    self.log(f"[DEPENDENCIAS] No se pudo limpiar {candidate}: {exc}")

    def _start_command(
        self,
        args: list[str],
        cwd: Path,
        title: str,
        callback=None,
    ) -> None:
        if self.process_running:
            messagebox.showwarning("En ejecución", "Ya existe un proceso PlatformIO activo.")
            return

        pio = self._platformio_path()

        if title in ("COMPILAR", "LIMPIAR"):
            self._clean_legacy_dependency_residue(cwd)

        command = [str(pio), *args]
        self.process_running = True
        self.log("")
        self.log(f"[{title}] {' '.join(command)}")

        def worker() -> None:
            try:
                creationflags = 0
                if os.name == "nt":
                    creationflags = subprocess.CREATE_NO_WINDOW

                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=creationflags,
                )

                assert proc.stdout is not None
                for line in proc.stdout:
                    self.output_queue.put(line.rstrip())

                return_code = proc.wait()
            except Exception as exc:
                self.output_queue.put(f"ERROR ejecutando PlatformIO: {exc}")
                return_code = -1

            def finish() -> None:
                self.process_running = False
                status = "SUCCESS" if return_code == 0 else f"FAILED ({return_code})"
                self.log(f"[{title}] {status}")
                if callback:
                    callback(return_code)

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def generate_and_compile(self) -> None:
        try:
            cfg, project = self._generate()
            self._start_command(
                ["run", "-e", cfg.env_name],
                project,
                "COMPILAR",
                lambda rc: messagebox.showinfo("Compilación", "Compilación terminada correctamente.")
                if rc == 0
                else messagebox.showerror("Compilación", "La compilación falló. Revisa el registro."),
            )
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Error", str(exc))

    def generate_compile_upload(self) -> None:
        try:
            cfg, project = self._generate()

            def after_compile(return_code: int) -> None:
                if return_code != 0:
                    messagebox.showerror("Compilación", "La compilación falló. No se realizará la carga.")
                    return

                ready = messagebox.askokcancel(
                    "Preparar DFU",
                    "Compilación correcta.\n\n"
                    "Ahora haz DOBLE CLIC rápido en RESET de la T-Echo.\n"
                    "Espera a que aparezca el puerto de bootloader y pulsa Aceptar.",
                )
                if ready:
                    self._start_command(
                        ["run", "-e", cfg.env_name, "-t", "upload"],
                        project,
                        "SUBIR",
                    )

            self._start_command(
                ["run", "-e", cfg.env_name],
                project,
                "COMPILAR",
                after_compile,
            )
        except Exception as exc:
            self.log(f"ERROR: {exc}")
            messagebox.showerror("Error", str(exc))

    def clean_last(self) -> None:
        try:
            cfg, project = self._ensure_last()
            self._start_command(
                ["run", "-e", cfg.env_name, "-t", "clean"],
                project,
                "LIMPIAR",
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def compile_last(self) -> None:
        try:
            cfg, project = self._ensure_last()
            self._start_command(["run", "-e", cfg.env_name], project, "COMPILAR")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def upload_last(self) -> None:
        try:
            cfg, project = self._ensure_last()
            ready = messagebox.askokcancel(
                "Preparar DFU",
                "Haz DOBLE CLIC rápido en RESET de la T-Echo.\n"
                "Luego pulsa Aceptar para iniciar la carga.",
            )
            if ready:
                self._start_command(
                    ["run", "-e", cfg.env_name, "-t", "upload"],
                    project,
                    "SUBIR",
                )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def monitor_last(self) -> None:
        try:
            cfg, project = self._ensure_last()
            pio = self._platformio_path()
            command = [
                str(pio),
                "device",
                "monitor",
                "-e",
                cfg.env_name,
                "-b",
                "115200",
            ]

            if os.name == "nt":
                subprocess.Popen(
                    command,
                    cwd=str(project),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                subprocess.Popen(command, cwd=str(project))

            self.log("[MONITOR] Abierto en una consola independiente.")
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def open_last(self) -> None:
        try:
            _cfg, project = self._ensure_last()
            if os.name == "nt":
                os.startfile(project)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(project)])
            else:
                subprocess.Popen(["xdg-open", str(project)])
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


def main() -> None:
    root = tk.Tk()
    GeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
