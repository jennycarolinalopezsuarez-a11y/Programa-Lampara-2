# Generador MinerGuard T-Echo GPS AUTO V6

Este programa parte del generador V5 y de la base funcional:

```text
GPS automático según RSSI de beacons
WAKEUP + RESET + PCAS al volver desde modo beacon
Payload de 46 bytes
HR7 = latitud
HR8 = longitud
HR20 = fix GPS válido
MCCI LMIC + SX1262 + UG65
PlatformIO
```

## Qué genera

Por cada TAG crea una carpeta PlatformIO con:

```text
platformio.ini
src/main.cpp
include/utilities.h
node_red/
README_GENERADO.md
TAG<id>_CONFIG.txt
01_LIMPIAR_Y_COMPILAR.bat
02_SUBIR_DFU.bat
03_MONITOR_SERIE.bat
```

También mantiene en la carpeta de salida:

```text
minerguard_nodes.csv
ug65_bulk_import_devices.csv
```

## Compilar y subir desde la interfaz

El botón **Generar + compilar + subir**:

1. Genera el proyecto.
2. Ejecuta PlatformIO.
3. Espera que la compilación termine correctamente.
4. Solicita hacer doble clic rápido en RESET.
5. Ejecuta la carga mediante `nrfutil`.

La entrada manual a DFU sigue siendo necesaria.

## Requisitos

- Windows con Python 3.
- Tkinter incluido con Python.
- PlatformIO instalado en:

```text
%USERPROFILE%\.platformio\penv\Scripts\platformio.exe
```

El programa también permite seleccionar manualmente otro `platformio.exe`.

## Ejecutar

Haz doble clic en:

```text
EJECUTAR_GENERADOR.bat
```

o desde PowerShell:

```powershell
python .\Minerguard_TEcho_Generador_V6_GPS_AUTO_PLATFORMIO.py
```

## Valores recomendados

```text
Filtro scanner: -100 dBm
GPS ON: RSSI <= -94 dBm
GPS OFF: RSSI >= -85 dBm
Beacon reciente: 7000 ms
Confirmación: 1500 ms
Timeout NMEA: 10000 ms
Cooldown recovery: 15000 ms
Intentos recovery: 3
```

## Node-RED

El decoder incluido reconoce:

```text
gps_active
gps_valid
latitud
longitud
gps_satelites
gps_hdop
```

No es necesario crear un decoder diferente por cada TAG.


## Escaneo Bluetooth desde el generador

La sección **Banda cardíaca y escaneo Bluetooth** permite:

```text
Definir un prefijo de nombre, por ejemplo H1_
Buscar dispositivos BLE durante 8 segundos
Ordenarlos por intensidad RSSI
Seleccionar la banda encontrada
Copiar automáticamente el nombre y la MAC
```

Para instalar la dependencia:

```text
INSTALAR_BLEAK.bat
```

o:

```powershell
py -3 -m pip install bleak
```

En algunos sistemas distintos de Windows, Bleak puede mostrar una dirección
interna o UUID en vez de la MAC pública. En ese caso el nombre se completa,
pero la MAC debe escribirse manualmente.

## Carpeta de destino

La parte superior del programa permite:

```text
Elegir la carpeta base
Definir el nombre de la carpeta del proyecto
Ver la ruta final antes de generar
Abrir la carpeta base desde el programa
```

Ejemplo:

```text
Carpeta base:
C:%USERPROFILE%\pruebalilygo

Proyecto:
PlatformIO_Minerguard_TEcho_8_GPS_AUTO_V3

Ruta final:
C:%USERPROFILE%\pruebalilygo\PlatformIO_Minerguard_TEcho_8_GPS_AUTO_V3
```


## Corrección V6.2: error SdFatConfig.h

La versión V6.1 incluía explícitamente:

```ini
adafruit/Adafruit TinyUSB Library@3.7.7
```

El firmware no utiliza funciones directas de esa librería. La dependencia
arrastraba Adafruit SPIFlash y SdFat, aunque no se utilizan en MinerGuard.

V6.2:

```text
Elimina el include Adafruit_TinyUSB.h
Elimina la dependencia externa Adafruit TinyUSB
Cambia lib_ldf_mode de deep+ a chain+
Limpia automáticamente .pio/libdeps y .pio/build antes de compilar
```

Para reparar un proyecto generado con V6.1 ejecuta:

```text
REPARAR_PROYECTO_EXISTENTE.bat
```

y pega la ruta completa de la carpeta del proyecto.


## Corrección V6.3: CSV UG65 exacto

Los dos archivos de referencia usan exactamente este encabezado y orden:

```text
name,description,deveui,deviceprofile,application,payloadcodec,fport,appkey,devaddr,nwkskey,appskey,timeout
```

La versión V6.3 escribe:

```text
Separador: coma
Codificación: UTF-8 sin BOM
Fin de línea: CRLF
DevEUI: minúsculas
AppKey: minúsculas
Campos ABP: vacíos
Orden de columnas: exacto
```

El usuario puede elegir un CSV existente, validarlo y actualizarlo. Si el
Node ID o DevEUI ya existe, se reemplaza la fila en vez de duplicarla.

Además se crean:

```text
CSV colectivo seleccionado por el usuario
UG65_TAG_<ID>_IMPORT.csv dentro del proyecto
registro_interno_minerguard.csv, que NO debe importarse en el UG65
```

Para T-Echo la aplicación predeterminada ahora es:

```text
LilyGo
```

También puede seleccionarse o escribirse:

```text
Sense_T1000
```

## Corrección V6.3: rueda del mouse

La ventana principal ahora reconoce:

```text
Rueda tradicional de Windows
Touchpad con delta menor a 120
Button-4 y Button-5 de Linux
Page Up y Page Down
```

El registro de texto conserva su propio desplazamiento.
