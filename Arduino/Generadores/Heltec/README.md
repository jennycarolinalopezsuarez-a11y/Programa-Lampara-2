# MinerGuard Heltec T114 - Generador FinalPrueba Animación v2

Generador de escritorio en Python para crear sketches `.ino` de **MinerGuard** para placa **Heltec Mesh Node T114 / HT-n5262**, con LoRaWAN, BLE, pantalla TFT ST7789, beacons MinerGuard, banda cardiaca BLE y botón de pánico.

Este código genera automáticamente:

```text
Minerguard_<NODE_ID>/
├── Minerguard_<NODE_ID>.ino
├── display.cpp
└── display.h

nodes.csv
ug65_bulk_import_devices.csv
```

---

## 1. Funcionalidades principales

- Generación automática de sketch Arduino para **Heltec T114**.
- Generación de credenciales **OTAA**:
  - `DevEUI`
  - `AppEUI / JoinEUI`
  - `AppKey`
- Validación de credenciales únicas usando `nodes.csv`.
- Generación de CSV compatible con **Milesight UG65 Bulk Import**.
- Conexión BLE estricta por **MAC de banda cardiaca**.
- Lectura de:
  - Heart Rate Service `0x180D`
  - Heart Rate Measurement `0x2A37`
  - Battery Service `0x180F`
  - Battery Level `0x2A19`
- Detección de beacons tipo iBeacon MinerGuard:
  - `Major = nivel / piso / sector`
  - `Minor = PK`
- Selección de los 3 beacons más fuertes por RSSI.
- Envío LoRaWAN con payload extendido de **36 bytes**.
- Pantalla TFT ST7789 240x135.
- Animación fluida de corazón.
- Botón de pánico.
- Integración con gateway **Milesight UG65**.

---

## 2. Hardware objetivo

Placa principal:

```text
Heltec Mesh Node T114
Modelo en Arduino IDE: Mesh Node T114(HT-n5262)
MCU: nRF52840
Radio LoRa: SX1262
Bluetooth: BLE 5.0
Pantalla: TFT ST7789 240x135
```

Documentación oficial:

```text
https://wiki.heltec.org/docs/devices/open-source-hardware/nrf52840-series/mesh-node-t114/
```

Repositorio del core Heltec nRF52:

```text
https://github.com/HelTecAutomation/Heltec_nRF52
```

---

## 3. Requisitos de software

### Arduino IDE

Descargar Arduino IDE desde:

```text
https://www.arduino.cc/en/software
```

Se recomienda usar Arduino IDE 2.x.

### Python

El generador está hecho en Python con interfaz gráfica Tkinter.

Descargar Python desde:

```text
https://www.python.org/downloads/
```

En Windows normalmente Tkinter ya viene incluido con Python.

En Linux, si falta Tkinter:

```bash
sudo apt update
sudo apt install python3-tk
```

---

## 4. Instalación de boards Heltec nRF52

En Arduino IDE:

1. Ir a:

```text
File > Preferences
```

2. En **Additional Boards Manager URLs**, agregar:

```text
https://github.com/HelTecAutomation/Heltec_nRF52/releases/download/1.7.0/package_heltec_nrf_index.json
```

3. Luego ir a:

```text
Tools > Board > Boards Manager
```

4. Buscar e instalar:

```text
Heltec-nRF52
```

5. Seleccionar la placa:

```text
Tools > Board > Heltec nRF52 > Mesh Node T114(HT-n5262)
```

---

## 5. Configuración recomendada de board

En Arduino IDE, usar:

```text
Board: Mesh Node T114(HT-n5262)
SoftDevice: S140 6.1.1
LoRa Debug: Enable
LoRa Debug Port: Serial(USB CDC)
Upload Method: nrfutil / USB CDC
Puerto: el puerto COM/tty de la T114
```

Si no necesitas logs por monitor serial, `LoRa Debug` puede quedar en `Disable`, pero para pruebas iniciales conviene dejarlo activado.

---

## 6. Librerías necesarias en Arduino IDE

Instalar desde:

```text
Sketch > Include Library > Manage Libraries
```

| Librería | Uso | Link |
|---|---|---|
| **Heltec nRF52 Core** | Board package, LoRaWAN, pines, `heltec_nrf_lorawan.h`, soporte nRF52840. | `https://github.com/HelTecAutomation/Heltec_nRF52` |
| **Adafruit GFX Library** | Funciones gráficas base para la pantalla. | `https://github.com/adafruit/Adafruit-GFX-Library` |
| **Adafruit ST7735 and ST7789 Library** | Driver de pantalla ST7789 usado por `Adafruit_ST7789`. | `https://github.com/adafruit/Adafruit-ST7735-Library` |
| **Adafruit TinyUSB Library** | Soporte USB/Serial en placas compatibles. | `https://github.com/adafruit/Adafruit_TinyUSB_Arduino` |

### Librerías incluidas por el core / Arduino

Estas normalmente no se instalan manualmente:

```cpp
#include <Arduino.h>
#include <SPI.h>
#include <bluefruit.h>
#include "heltec_nrf_lorawan.h"
```

`bluefruit.h` y `heltec_nrf_lorawan.h` vienen asociados al entorno Heltec nRF52 / nRF52840.

---

## 7. Includes usados por el sketch generado

El firmware generado usa:

```cpp
#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_TinyUSB.h>
#include <bluefruit.h>
#include "heltec_nrf_lorawan.h"
#include "display.h"

#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
```

Además, el generador crea los archivos:

```text
display.cpp
display.h
```

Estos dos archivos son obligatorios y deben quedar en la misma carpeta del `.ino`.

---

## 8. Librerías Python necesarias

El generador usa principalmente librerías estándar de Python:

```python
csv
os
re
secrets
datetime
pathlib
tkinter
```

Opcionalmente, para usar el botón **Buscar bandas BLE**, se requiere:

```bash
pip install bleak
```

Si no instalas `bleak`, el generador igual funciona, pero tendrás que ingresar manualmente la MAC de la banda cardiaca.

---

## 9. Cómo ejecutar el generador

### Windows

Desde la carpeta donde está el archivo `.py`:

```powershell
python "MinerguardPRUEBA_generador_FinalPrueba_animacion_v2(7).py"
```

### Linux

```bash
python3 "MinerguardPRUEBA_generador_FinalPrueba_animacion_v2(7).py"
```

---

## 10. Campos importantes del generador

| Campo | Descripción |
|---|---|
| `Node ID` | ID numérico del trabajador/nodo. |
| `Nombre persona` | Nombre que aparecerá asociado al nodo. |
| `Nombre BLE T114` | Nombre BLE propio de la Heltec. |
| `Periodo envío (ms)` | Tiempo entre envíos LoRaWAN. Por defecto `15000`. |
| `Prefijo banda` | Filtro para búsqueda BLE desde el PC. |
| `Nombre banda` | Nombre visible de la banda detectada. |
| `MAC banda` | MAC exacta de la banda cardiaca. Es obligatoria. |
| `DevEUI` | Identificador único LoRaWAN. |
| `AppEUI / JoinEUI` | JoinEUI usado en OTAA. |
| `AppKey` | Clave OTAA. |
| `Application UG65` | Nombre de la aplicación en el gateway UG65. |
| `Device Profile UG65` | Perfil LoRaWAN usado por el UG65. |
| `FPort` | Puerto de aplicación usado por el decoder. |
| `Timeout` | Timeout definido para importación en UG65. |

---

## 11. Compilación del sketch generado

Después de generar el código:

1. Abrir el archivo:

```text
Minerguard_<NODE_ID>/Minerguard_<NODE_ID>.ino
```

2. Verificar que en la misma carpeta estén:

```text
display.cpp
display.h
```

3. Seleccionar board:

```text
Tools > Board > Heltec nRF52 > Mesh Node T114(HT-n5262)
```

4. Seleccionar el puerto correspondiente.

5. Compilar.

6. Subir a la placa.

---

## 12. Importante sobre la estructura de carpetas Arduino

Arduino IDE exige que el archivo `.ino` esté dentro de una carpeta con el mismo nombre.

Correcto:

```text
Minerguard_252/
├── Minerguard_252.ino
├── display.cpp
└── display.h
```

Incorrecto:

```text
Minerguard_252.ino
display.cpp
display.h
```

El generador ya crea la estructura correcta automáticamente.

---

## 13. Configuración LoRaWAN

El sketch generado usa:

```cpp
LoRaMacRegion_t loraWanRegion = LORAMAC_REGION_US915;
DeviceClass_t   loraWanClass  = CLASS_A;

bool overTheAirActivation = true;
bool loraWanAdr = true;
bool isTxConfirmed = false;
```

Máscara de canales configurada:

```cpp
uint16_t userChannelsMask[6] = {
  0xFF00,
  0x0000,
  0x0000,
  0x0000,
  0x0000,
  0x0000
};
```

Esto se usa normalmente para trabajar en **US915 Sub-Band 2**, compatible con configuraciones habituales en UG65.

---

## 14. Advertencia importante sobre FPort

En el sketch base aparece:

```cpp
uint8_t appPort = 2;
```

Pero en la interfaz del generador, el campo `FPort` del CSV UG65 puede venir por defecto en:

```text
1
```

Para evitar problemas en el decoder, el **FPort del sketch y el FPort del UG65 deben coincidir**.

Opciones:

### Opción A: usar FPort 2

Dejar el sketch así:

```cpp
uint8_t appPort = 2;
```

y configurar en el generador:

```text
FPort = 2
```

### Opción B: usar FPort 1

Cambiar en el sketch:

```cpp
uint8_t appPort = 2;
```

por:

```cpp
uint8_t appPort = 1;
```

y dejar en el generador:

```text
FPort = 1
```

---

## 15. CSV generado para UG65

El generador crea:

```text
ug65_bulk_import_devices.csv
```

Con columnas:

```text
name,description,deveui,deviceprofile,application,payloadcodec,fport,appkey,devaddr,nwkskey,appskey,timeout
```

Ejemplo conceptual:

```csv
name,description,deveui,deviceprofile,application,payloadcodec,fport,appkey,devaddr,nwkskey,appskey,timeout
252,Rodrigo Zuñiga,aabbccddeeff0011,ClassA-OTAA,Sense_T1000,,2,00112233445566778899aabbccddeeff,,,,1440
```

---

## 16. Payload extendido

El payload generado tiene tamaño fijo:

```text
36 bytes
```

Estructura general:

| Bytes | Contenido |
|---|---|
| `0` | Flags |
| `1` | Frecuencia cardiaca |
| `2` | Batería de banda |
| `3-4` | Node ID |
| `5` | Estado BLE conectado |
| `6-20` | Snapshot A de 3 beacons |
| `21-35` | Snapshot B de 3 beacons |

Cada beacon usa:

```text
Major_H, Major_L, Minor_H, Minor_L, RSSI_codificado
```

Convención:

```text
Major = nivel / piso / sector
Minor = PK
```

---

## 17. Banda cardiaca BLE

El firmware se conecta exclusivamente a la MAC indicada en el generador:

```cpp
static const char BAND_MAC_TARGET[] = "AA:BB:CC:DD:EE:FF";
```

No se conecta por nombre ni por prefijo, para evitar que la Heltec se conecte por error a otra banda cercana.

---

## 18. Pantalla y animación

El proyecto usa pantalla:

```text
ST7789 240x135
Rotación: 3
```

La lógica de pantalla está separada en:

```text
display.cpp
display.h
```

La pantalla muestra:

- BPM grande.
- Corazón animado.
- Estado de beacons.
- PK actual.
- Estado de pánico.
- Indicadores TX/ACK.

---

## 19. Error frecuente: setSPISpeed

Si al compilar aparece un error como:

```text
'class Adafruit_ST7789' has no member named 'setSPISpeed'
```

revisar primero que esté instalada la librería correcta:

```text
Adafruit ST7735 and ST7789 Library
```

y que Arduino IDE esté usando esa librería.

También puedes comentar temporalmente esta línea en `display.cpp`:

```cpp
tft.setSPISpeed(40000000);
```

dejándola así:

```cpp
// tft.setSPISpeed(40000000);
```

La pantalla puede funcionar igualmente, aunque con velocidad SPI por defecto.

---

## 20. Error frecuente: archivo fuera de carpeta del sketch

Si Arduino IDE muestra algo parecido a:

```text
The file needs to be inside a sketch folder named ...
```

significa que el `.ino` no está dentro de una carpeta con el mismo nombre.

Ejemplo correcto:

```text
Minerguard_252/Minerguard_252.ino
```

El generador ya debería crear esta estructura automáticamente.

---

## 21. Error frecuente: no encuentra heltec_nrf_lorawan.h

Si aparece:

```text
heltec_nrf_lorawan.h: No such file or directory
```

revisar:

1. Que esté instalado el board package **Heltec-nRF52**.
2. Que la placa seleccionada sea:

```text
Mesh Node T114(HT-n5262)
```

3. Que no estés compilando con una board Adafruit, ESP32 u otra placa.

Este código no usa MCCI LMIC directamente; usa la librería LoRaWAN incluida en el entorno Heltec nRF52.

---

## 22. Recomendaciones para GitHub

Si subes este proyecto a GitHub, se recomienda esta estructura:

```text
MinerGuard_Heltec_T114/
├── README.md
├── MinerguardPRUEBA_generador_FinalPrueba_animacion_v2.py
├── examples/
│   └── Minerguard_252/
│       ├── Minerguard_252.ino
│       ├── display.cpp
│       └── display.h
└── docs/
    └── payload_36_bytes.md
```

---

## 23. .gitignore recomendado

No conviene subir credenciales reales a GitHub.

Crear un archivo `.gitignore` con:

```gitignore
# Credenciales reales / CSV generados
nodes.csv
ug65_bulk_import_devices.csv

# Python
__pycache__/
*.pyc

# Arduino build
build/
*.tmp
*.bak

# Archivos locales
.DS_Store
Thumbs.db
```

Si el repositorio es privado y quieres llevar control de los nodos, puedes subir `nodes.csv`, pero para repositorios públicos es mejor no hacerlo.

---

## 24. Links necesarios

### Arduino IDE

```text
https://www.arduino.cc/en/software
```

### Heltec Mesh Node T114

```text
https://wiki.heltec.org/docs/devices/open-source-hardware/nrf52840-series/mesh-node-t114/
```

### Heltec nRF52 Core

```text
https://github.com/HelTecAutomation/Heltec_nRF52
```

### Board Manager URL Heltec nRF52

```text
https://github.com/HelTecAutomation/Heltec_nRF52/releases/download/1.7.0/package_heltec_nrf_index.json
```

### Adafruit GFX Library

```text
https://github.com/adafruit/Adafruit-GFX-Library
```

### Adafruit ST7735 and ST7789 Library

```text
https://github.com/adafruit/Adafruit-ST7735-Library
```

### Adafruit TinyUSB Arduino

```text
https://github.com/adafruit/Adafruit_TinyUSB_Arduino
```

### Bleak para escaneo BLE desde Python

```text
https://github.com/hbldh/bleak
```

### Milesight UG65

```text
https://www.milesight.com/iot/product/lorawan-gateway/ug65
```

---

## 25. Notas finales

Este generador está orientado a producción de nodos MinerGuard usando:

```text
Heltec Mesh Node T114
LoRaWAN OTAA
US915
Milesight UG65
BLE Heart Rate
iBeacon MinerGuard
Pantalla ST7789
Payload 36 bytes
```

Antes de cargar múltiples nodos, verificar siempre:

1. Que cada `DevEUI` sea único.
2. Que cada `AppKey` sea único.
3. Que el `FPort` del sketch coincida con el `FPort` configurado en UG65.
4. Que la MAC de la banda cardiaca corresponda al trabajador correcto.
5. Que el decoder de Node-RED esté esperando payload de 36 bytes.
