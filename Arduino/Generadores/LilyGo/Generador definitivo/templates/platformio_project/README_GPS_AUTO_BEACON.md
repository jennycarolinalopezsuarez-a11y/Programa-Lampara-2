# TAG 6 — GPS automático según intensidad de beacon

## Regla de funcionamiento

El escaneo BLE de beacons permanece siempre activo.

### GPS encendido

El GPS se enciende cuando:

- no existe un beacon recibido durante los últimos 5 segundos; o
- el beacon más fuerte tiene RSSI menor o igual a -85 dBm.

La condición debe mantenerse durante 3 segundos antes de cambiar el modo.

### GPS apagado

El GPS entra en standby cuando:

- existe un beacon reciente; y
- el beacon más fuerte tiene RSSI mayor o igual a -75 dBm.

La condición debe mantenerse durante 3 segundos.

### Histéresis

Entre -84 y -76 dBm se conserva el modo anterior. Esto evita que el GPS
se encienda y apague continuamente cuando el RSSI fluctúa cerca del límite.

## Estados enviados

El formato sigue siendo de 46 bytes y no cambia HR7, HR8 ni HR20.

```text
flags 0x10 = coordenada GPS válida
flags 0x20 = módulo GPS encendido/buscando

HR7  = latitud cuando existe fix
HR8  = longitud cuando existe fix
HR20 = 1 solo con fix GPS válido
HR20 = 0 en modo beacon o mientras el GPS todavía busca satélites
```

Esto permite distinguir:

```text
gps_active=false, gps_valid=false → modo BEACON, GPS apagado
gps_active=true,  gps_valid=false → GPS encendido y buscando
gps_active=true,  gps_valid=true  → GPS con coordenada válida
```

## Parámetros configurables

En `src/main.cpp`:

```cpp
static const int8_t GPS_ON_BEACON_RSSI_DBM  = -85;
static const int8_t GPS_OFF_BEACON_RSSI_DBM = -75;
static const uint32_t BEACON_SWITCH_RECENT_MS = 5000;
static const uint32_t GPS_SWITCH_CONFIRM_MS = 3000;
```

## Compilar

```powershell
cd "C:\Users\Innovacion FMT\Documents\Tomas\pruebalilygo\PlatformIO_Minerguard_TEcho_4_GPS_AUTO_SEGUN_BEACON_V1"

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t clean

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20
```

## Subir

Doble clic rápido en RESET:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t upload
```

## Monitor serie

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -e minerguard_techo_6_gps_hr20 -b 115200
```

Mensajes esperados:

```text
[POSICION] GPS APAGADO | usando BEACON | motivo=beacon fuerte
[POSICION] GPS ENCENDIDO | motivo=sin beacon reciente
[POSICION] GPS ENCENDIDO | motivo=beacon debil
[GPS] mode=ON/BUSCANDO ...
[GPS] mode=OFF/BEACON ...
[PAYLOAD] GPS_ACTIVE=1 GPS_VALID=0 ...
[PAYLOAD] GPS_ACTIVE=1 GPS_VALID=1 ...
```
