# MinerGuard T-Echo — GPS en HR7, HR8 y HR20

Esta versión corrige el diseño anterior.

## Error corregido

`HR20` no corresponde automáticamente a `payload[19]`.

El byte 19 ya pertenece al `minor` del beacon 3. Escribir el estado GPS allí
corrompía el beacon y no permitía que Node-RED obtuviera latitud ni longitud.

## Payload V2: 46 bytes

```text
Bytes 0..35  = payload MinerGuard original
Bytes 36..39 = latitud × 1.000.000, int32 big-endian
Bytes 40..43 = longitud × 1.000.000, int32 big-endian
Byte 44      = cantidad de satélites
Byte 45      = HDOP × 10; 255 significa inválido
```

El byte de flags mantiene:

```text
0x01 = pánico
0x02 = frecuencia cardíaca válida
0x04 = batería de banda válida
0x08 = BLE conectado
0x10 = GPS válido
```

Node-RED asigna:

```text
HR7  = latitud
HR8  = longitud
HR20 = gps_valid: 0 sin GPS, 1 con GPS
```

## Credenciales

Se mantienen el mismo DevEUI, JoinEUI/AppEUI y AppKey del proyecto anterior.

## Compilar

```powershell
cd "C:\Users\Innovacion FMT\Documents\Tomas\pruebalilygo\PlatformIO_Minerguard_TEcho_4_LMIC_GPS_HR7_HR8_HR20_V2"

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20
```

## Subir

Doble clic en RESET para entrar en DFU:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t upload
```

## Qué debe verse

En el UG65, el tamaño del uplink debe cambiar de 36 a **46 bytes**.

En `Debug Heltec decoded` de Node-RED:

```text
gps_valid: true
latitud: -34.xxxxxx
longitud: -70.xxxxxx
gps_satelites: 8
gps_hdop: 1.2
payload_bytes: 46
```

En `Debug mapa Modbus`:

```text
hr7: -34.xxxxxx
hr8: -70.xxxxxx
hr20: 1
```

Cuando no hay fix:

```text
gps_valid: false
latitud: null
longitud: null
hr20: 0
```

## Precisión

La codificación conserva seis decimales, pero la precisión real depende de la
geometría satelital. Usa `gps_satelites` y `gps_hdop` como referencia:

```text
HDOP <= 1.0  excelente
HDOP 1.0–2.5 buena
HDOP 2.5–5.0 moderada
HDOP > 5.0  baja
```
