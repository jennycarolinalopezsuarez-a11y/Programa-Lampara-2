# TAG 6 — GPS automático V2 con corrección de retorno a beacons

## Problema observado

Al salir del rango, el GPS se activaba correctamente. Al volver al rango,
el sistema podía permanecer en GPS aunque los beacons reaparecieran.

## Causas probables corregidas

1. El umbral anterior para apagar el GPS era demasiado exigente:
   `RSSI >= -75 dBm`.

2. La zona de histéresis anterior mantenía el GPS activo entre `-84` y
   `-76 dBm`.

3. El filtro RSSI daba 70 % de peso al valor antiguo y solo 30 % al nuevo,
   retrasando la recuperación al volver al rango.

4. La pantalla podía conservar el texto GPS aunque el estado interno ya
   hubiese cambiado.

## Nueva configuración

```cpp
GPS_ON_BEACON_RSSI_DBM  = -94;
GPS_OFF_BEACON_RSSI_DBM = -85;

BEACON_SWITCH_RECENT_MS = 7000;
GPS_SWITCH_CONFIRM_MS   = 1500;
```

Filtro RSSI:

```cpp
RSSI_filtrado = RSSI_anterior * 0.35 + RSSI_nuevo * 0.65;
```

## Diagnóstico por monitor serie

Cada 2 segundos aparecerá:

```text
[SELECTOR] beacon=SI rssi=-72 gps=ON umbralOFF=-85 umbralON=-94
```

Interpretación:

- `beacon=NO`: no se están recibiendo anuncios.
- `beacon=SI`: el scanner está recibiendo beacons.
- `rssi >= -85`: debe apagar el GPS.
- `rssi <= -94`: debe encender el GPS.
- entre -93 y -86: mantiene el modo anterior.

Mensajes de cambio:

```text
[POSICION] Cambio pendiente GPS=OFF RSSI_FILTRADO=-78 motivo=beacon fuerte
[POSICION] GPS APAGADO | usando BEACON | motivo=beacon fuerte
```

## Compilar

```powershell
cd "C:\Users\Innovacion FMT\Documents\Tomas\pruebalilygo\PlatformIO_Minerguard_TEcho_4_GPS_AUTO_SEGUN_BEACON_V2_RSSI_FIX"

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t clean

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20
```

## Subir

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t upload
```

## Monitor

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -e minerguard_techo_6_gps_hr20 -b 115200
```
