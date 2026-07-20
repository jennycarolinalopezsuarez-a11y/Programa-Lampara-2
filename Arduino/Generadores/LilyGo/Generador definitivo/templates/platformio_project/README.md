# MinerGuard T-Echo 6 LMIC + GPS real en HR20

Proyecto PlatformIO basado en `Minerguard_TEcho_6_LMIC_FULL(1).ino`.

## Cambio realizado

Se integró la lectura GPS del logger CSV que sí funcionó:

```cpp
GPS RX = P1.9
GPS TX = P1.8
GPS Wakeup = P1.2
GPS Reset = P1.5
UART = 9600 baud
```

El payload continúa siendo de **36 bytes** y conserva las mismas credenciales OTAA del sketch original.

El flujo actual interpreta:

```txt
HR1  = payload[0]
...
HR20 = payload[19]
```

Por eso el firmware fuerza:

```txt
payload[19] = 0  cuando no hay fix GPS
payload[19] = 1  cuando hay fix GPS válido y reciente
```

## Advertencia sobre el payload existente

En el payload original, el byte `19` formaba parte del tercer beacon del snapshot A. Al dedicarlo a HR20/GPS, ese byte deja de representar la parte baja del `minor` de ese beacon. Esto se hizo para respetar exactamente el HR20 solicitado sin modificar Node-RED ni aumentar los 36 bytes.

## Credenciales conservadas

```txt
DevEUI mostrado por el sketch: CBE76AE7ABCCF0E6
JoinEUI: 0000000000000000
AppKey: 38A852308D24355D1428A4EC853EDF83
US915 SubBand 2
FPort 1
```

## Compilar

```powershell
cd "C:\Users\Innovacion FMT\Documents\Tomas\pruebalilygo\PlatformIO_Minerguard_TEcho_6_LMIC_GPS_HR20"

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20
```

## Subir

Pon la T-Echo en DFU con doble clic en RESET y ejecuta:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t upload
```

Luego reinicia con un solo clic.

## Monitor serie

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -e minerguard_techo_6_gps_hr20 -b 115200
```

Cada 5 segundos aparecerá algo como:

```txt
[GPS] chars=1200 sentences=30 GGA=10 RMC=10 GSV=20 fixQ=0 rmc=V sats=0 valid=NO HR20=0
```

o, con fix:

```txt
[GPS] ... fixQ=1 rmc=A sats=8 valid=YES HR20=1 lat=-34.xxxxxx lon=-70.xxxxxx
```

Al construir el payload también imprime:

```txt
[PAYLOAD] HR20 GPS=0
```

o:

```txt
[PAYLOAD] HR20 GPS=1
```


## Versión sin Git

Esta variante instala MCCI LMIC directamente desde el registro de PlatformIO:

```ini
mcci-catena/MCCI LoRaWAN LMIC library@5.0.1
```

Por lo tanto, no requiere instalar Git en Windows.


## Corrección de compilación incluida

La versión anterior declaraba las variables globales del GPS después de las
funciones que las utilizaban. PlatformIO compila `main.cpp` como C++ estándar,
por lo que nombres como `gps`, `gpsChars`, `gpsGgaCount`,
`gpsGgaFixQuality`, `gpsRmcStatus` y `lastGpsDiagnostic` todavía no existían
para el compilador cuando procesaba esas funciones.

Esta versión mueve todas las declaraciones globales GPS antes de
`processGpsNmeaLine()`, `readGPS()`, `hasFreshGpsFix()` y
`printGpsDiagnostic()`.

Los avisos de `SdFat - Adafruit Fork` son warnings de una dependencia de
Adafruit TinyUSB y no son la causa del fallo.


## Identidad de este proyecto

```text
NODE_ID: 6
PERSON_NAME: Hector Quiroz
NODE_LABEL / BLE name: 6
DevEUI UG65: CBE76AE7ABCCF0E6
JoinEUI/AppEUI: 0000000000000000
AppKey: 38A852308D24355D1428A4EC853EDF83
Banda cardíaca: E5:FD:8A:F2:F3:AF
```
