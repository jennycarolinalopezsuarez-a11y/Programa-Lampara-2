# MinerGuard T-Echo V5 LMIC FULL FIX ARRAYS

Firmware y generador para nodos **LilyGO T-Echo nRF52840 + SX1262**, orientado a integración con **Milesight UG65 / LoRaWAN**, lectura de beacons BLE, banda cardiaca BLE, botón de pánico, e-paper y payload extendido compatible con el flujo actual de Node-RED de MinerGuard.

> **Importante:** este repositorio contiene un generador en Python que crea el sketch `.ino`, `utilities.h`, `nodes.csv`, CSV de importación para UG65 y la configuración `lmic_project_config.h` para LMIC.

---

## 1. Funcionalidades principales

- Comunicación **LoRaWAN OTAA** mediante **MCCI LMIC**.
- Radio **SX1262** integrada en LilyGO T-Echo.
- Payload fijo de **36 bytes**.
- Envío por **FPort 1**.
- Integración con gateway **Milesight UG65**.
- Lectura de banda cardiaca BLE:
  - Heart Rate Service `0x180D`.
  - Heart Rate Measurement `0x2A37`.
  - Battery Service `0x180F`.
  - Battery Level `0x2A19`.
- Filtro por MAC de banda cardiaca.
- Detección de beacons MinerGuard tipo iBeacon:
  - `Major = nivel / sector`.
  - `Minor = PK`.
  - Top 3 beacons por RSSI.
- Pantalla e-paper 200x200.
- Botón de pánico.
- Doble click en botón USER para activar/desactivar iluminación de pantalla.
- Generación de CSV para importación masiva en UG65.

---

## 2. Archivos generados

Al ejecutar el generador Python, se crean archivos similares a los siguientes:

```text
Minerguard_TEcho_<ID>/
├── Minerguard_TEcho_<ID>.ino
├── utilities.h
├── nodes.csv
├── ug65_import_<ID>.csv
└── lmic_project_config.h
```

### Descripción de archivos

| Archivo | Descripción |
|---|---|
| `Minerguard_TEcho_<ID>.ino` | Firmware principal para LilyGO T-Echo. |
| `utilities.h` | Mapeo de pines específico para T-Echo. |
| `nodes.csv` | Registro local de nodos generados. |
| `ug65_import_<ID>.csv` | Archivo para importar el dispositivo en Milesight UG65. |
| `lmic_project_config.h` | Configuración regional y de radio para MCCI LMIC. |

---

## 3. Requisitos de software

### Arduino IDE

Instalar Arduino IDE desde:

```text
https://www.arduino.cc/en/software
```

Se recomienda usar Arduino IDE 2.x.

---

## 4. Boards necesarias

### Board package principal

Instalar el core de Adafruit nRF52:

```text
https://github.com/adafruit/Adafruit_nRF52_Arduino
```

En Arduino IDE:

1. Ir a **File / Archivo > Preferences / Preferencias**.
2. En **Additional Boards Manager URLs**, agregar:

```text
https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
```

3. Ir a **Tools > Board > Boards Manager**.
4. Buscar e instalar:

```text
Adafruit nRF52 by Adafruit
```

---

## 5. Selección de board para LilyGO T-Echo

La LilyGO T-Echo tiene una complicación específica al compilar/cargar desde Arduino IDE.

### Flujo recomendado usado para este proyecto

Primero seleccionar y compilar con:

```text
Adafruit Metro nRF52840 Express
```

Luego, para la compilación/carga definitiva de la LilyGO T-Echo, seleccionar:

```text
Nordic nRF52840 (PCA10056)
```

o, si aparece con ese nombre en tu instalación:

```text
Nordic nRF52840 DK
```

### Nota importante

Este paso es relevante porque la T-Echo usa un **nRF52840**, pero no siempre aparece como “LilyGO T-Echo” directamente en Arduino IDE. En la documentación de LilyGO se indica instalar el core **Adafruit nRF52 by Adafruit** y luego seleccionar una board tipo **Nordic nRF52840 / Nordic nRF52840 DK** para trabajar con la T-Echo.

En este proyecto, además, se ha observado que primero compilar con **Adafruit Metro nRF52840 Express** ayuda a evitar problemas de configuración del entorno antes de pasar a la board Nordic definitiva.

---

## 6. Librerías necesarias

Instalar desde **Arduino IDE > Sketch > Include Library > Manage Libraries**.

| Librería | Uso | Link |
|---|---|---|
| **Adafruit nRF52 Core** | Core de placas nRF52840 y soporte Bluefruit BLE. | `https://github.com/adafruit/Adafruit_nRF52_Arduino` |
| **MCCI LoRaWAN LMIC library** | Stack LoRaWAN para OTAA y comunicación con SX1262. | `https://github.com/mcci-catena/arduino-lmic` |
| **GxEPD** | Control de pantalla e-paper. | `https://github.com/ZinggJM/GxEPD` |
| **Adafruit GFX Library** | Gráficos y fuentes para pantalla. | `https://github.com/adafruit/Adafruit-GFX-Library` |
| **Adafruit TinyUSB Library** | Soporte USB/Serial en placas con TinyUSB. | `https://github.com/adafruit/Adafruit_TinyUSB_Arduino` |

### Librerías incluidas por el core Arduino

Estas normalmente no se instalan manualmente:

```cpp
#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
```

### Librerías usadas directamente por el firmware

El sketch generado utiliza includes como:

```cpp
#include "utilities.h"

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_TinyUSB.h>
#include <bluefruit.h>
#include <lmic.h>
#include <hal/hal.h>

#include <GxEPD.h>
#include <GxDEPG0150BN/GxDEPG0150BN.h>
#include <Fonts/FreeMonoBold9pt7b.h>
#include <Fonts/FreeMonoBold12pt7b.h>
#include <Fonts/FreeMonoBold18pt7b.h>
#include <GxIO/GxIO_SPI/GxIO_SPI.h>
#include <GxIO/GxIO.h>
```

---

## 7. Configuración de LMIC

El proyecto usa **US915** y radio **SX1262**.

El archivo `lmic_project_config.h` debe quedar en la carpeta de la librería MCCI LMIC:

### Windows

```text
C:\Users\<TU_USUARIO>\Documents\Arduino\libraries\MCCI_LoRaWAN_LMIC_library\project_config\lmic_project_config.h
```

### Linux

```text
/home/<TU_USUARIO>/Arduino/libraries/MCCI_LoRaWAN_LMIC_library/project_config/lmic_project_config.h
```

Contenido recomendado:

```cpp
// lmic_project_config.h para LilyGO T-Echo SX1262 + Milesight UG65 US915
#pragma once

#define CFG_us915 1
#define CFG_sx1262_radio 1
#define LMIC_LORAWAN_SPEC_VERSION LMIC_LORAWAN_SPEC_VERSION_1_0_3

#define DISABLE_PING
#define DISABLE_BEACONS

// Mantener comentadas otras regiones/radios:
// #define CFG_eu868 1
// #define CFG_au915 1
// #define CFG_as923 1
// #define CFG_kr920 1
// #define CFG_in866 1
// #define CFG_sx1276_radio 1
// #define CFG_sx1261_radio 1
```

El generador incluye un botón para copiar automáticamente esta configuración a la ruta esperada por la librería LMIC.

---

## 8. Configuración LoRaWAN / UG65

El firmware trabaja con **OTAA**.

Credenciales usadas:

| Campo | Descripción |
|---|---|
| `DevEUI` | Identificador único del nodo. |
| `AppEUI / JoinEUI` | JoinEUI de la aplicación. En este proyecto puede quedar `0000000000000000`. |
| `AppKey` | Clave OTAA del dispositivo. |
| `FPort` | Por defecto `1`. |
| `Payload` | 36 bytes. |
| `Device Profile` | Por defecto `ClassA-OTAA`. |
| `Application` | Por defecto `Sense_T1000`. |

El generador crea un CSV compatible con importación masiva en UG65.

---

## 9. Uso del generador Python

### Ejecutar en Windows

Abrir terminal en la carpeta del archivo y ejecutar:

```powershell
python Minerguard_TEcho_Generador_V5_LMIC_FULL_FIX_ARRAYS.py
```

### Ejecutar en Linux

```bash
python3 Minerguard_TEcho_Generador_V5_LMIC_FULL_FIX_ARRAYS.py
```

Si en Linux falta Tkinter:

```bash
sudo apt install python3-tk
```

---

## 10. Campos del generador

| Campo | Uso |
|---|---|
| `Node ID` | Identificador numérico del nodo. |
| `Nombre persona en pantalla` | Nombre mostrado en e-paper. |
| `Nombre BLE / NODE_LABEL` | Nombre BLE del dispositivo. Por defecto igual al Node ID. |
| `MAC banda cardiaca` | MAC fija de la banda BLE. |
| `Periodo payload/envío ms` | Tiempo entre envíos LoRaWAN. Por defecto `15000`. |
| `Filtro RSSI beacons` | Filtro mínimo RSSI para beacons. Por defecto `-95`. |
| `Rotación e-paper` | Rotación de pantalla. Por defecto `3`. |
| `DevEUI` | DevEUI OTAA. |
| `AppEUI / JoinEUI` | JoinEUI OTAA. |
| `AppKey` | AppKey OTAA. |

---

## 11. Compilación y carga en Arduino IDE

1. Ejecutar el generador Python.
2. Abrir el archivo `.ino` generado.
3. Verificar que `utilities.h` esté en la misma carpeta del `.ino`.
4. Instalar las boards y librerías indicadas.
5. Copiar o generar `lmic_project_config.h`.
6. Seleccionar primero:

```text
Tools > Board > Adafruit nRF52 > Adafruit Metro nRF52840 Express
```

7. Compilar una vez para validar entorno.
8. Cambiar a:

```text
Tools > Board > Adafruit nRF52 > Nordic nRF52840 (PCA10056)
```

o:

```text
Tools > Board > Adafruit nRF52 > Nordic nRF52840 DK
```

9. Poner la T-Echo en modo DFU si es necesario:
   - doble click al botón superior/boot/reset hasta que aparezca como unidad USB o puerto disponible.
10. Seleccionar el puerto correcto.
11. Presionar **Upload**.

---

## 12. Monitor serial esperado

Velocidad:

```text
115200 baud
```

Secuencia esperada:

```text
[BOOT] SKETCH GENERADO POR: V5_LMIC_FULL_FIX_ARRAYS
EV_JOINING
EV_JOINED
[PAYLOAD 36B]
EV_TXSTART
EV_TXCOMPLETE
```

Si aparece:

```text
[LMIC] Payload listo, esperando EV_JOINED para TX real.
```

significa que el firmware ya arma el payload, pero todavía no se ha completado el JOIN OTAA.

---

## 13. Consideraciones sobre e-paper

La T-Echo usa pantalla **e-paper**, por lo tanto:

- No se actualiza tan rápido como una pantalla TFT.
- El refresco puede bloquear momentáneamente el loop.
- El firmware evita refrescos excesivos.
- El latido visual en pantalla no es tan fluido como en Heltec T114.
- El LED rojo se usa para representar el latido en tiempo real.

---

## 14. Consideraciones importantes

### No subir credenciales privadas

Si el repositorio es público, evitar subir archivos con:

- `AppKey` real.
- CSV real de UG65.
- Credenciales de gateway.
- IPs públicas sensibles.
- Contraseñas.
- Tokens.

Se recomienda dejar archivos de ejemplo, por ejemplo:

```text
ug65_import_ejemplo.csv
```

y mantener los CSV reales fuera del repositorio.

### Archivos sugeridos para `.gitignore`

```gitignore
# Credenciales / CSV reales
ug65_import_*.csv
nodes.csv

# Archivos temporales
*.tmp
*.bak

# Python
__pycache__/
*.pyc

# Arduino
build/
```

---

## 15. Links útiles

### Arduino IDE

```text
https://www.arduino.cc/en/software
```

### Adafruit nRF52 Arduino Core

```text
https://github.com/adafruit/Adafruit_nRF52_Arduino
```

### Guía Adafruit nRF52 BSP

```text
https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/arduino-bsp-setup
```

### LilyGO T-Echo

```text
https://github.com/Xinyuan-LilyGO/T-Echo
```

### MCCI LoRaWAN LMIC

```text
https://github.com/mcci-catena/arduino-lmic
```

### GxEPD

```text
https://github.com/ZinggJM/GxEPD
```

### Adafruit GFX

```text
https://github.com/adafruit/Adafruit-GFX-Library
```

### Adafruit TinyUSB

```text
https://github.com/adafruit/Adafruit_TinyUSB_Arduino
```

---

## 16. Estado del proyecto

Versión del generador:

```text
V5 LMIC FULL FIX ARRAYS
```

Base validada:

```text
MCCI LMIC + SX1262 + UG65
OTAA JOIN probado
EV_JOINED / EV_TXSTART / EV_TXCOMPLETE
Payload 36 bytes compatible con Node-RED
```
