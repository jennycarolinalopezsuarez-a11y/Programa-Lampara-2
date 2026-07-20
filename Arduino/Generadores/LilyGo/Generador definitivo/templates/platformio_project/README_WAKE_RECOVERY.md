# TAG 6 — GPS automático V3 con recuperación de despertar

La versión anterior levantaba WAKEUP a HIGH al volver desde modo beacon, pero
no repetía RESET ni la configuración PCAS. Esta versión realiza una
reinicialización completa del L76K cada vez que el selector vuelve a GPS.

## Secuencia al activar GPS

```text
WAKEUP HIGH
RESET HIGH → LOW → HIGH
espera 500 ms
PCAS04: GPS + GLONASS
PCAS03: sentencias NMEA
PCAS11: modo vehículo
```

Si en 10 segundos no aparece ningún carácter NMEA, reintenta automáticamente.
Se permiten hasta tres intentos, separados por 15 segundos.

## Diagnóstico

```text
[GPS] mode=ON/RECOVERY newChars=0
```

El GPS se está reinicializando.

```text
[GPS] mode=ON/BUSCANDO newChars=1200 fixQ=0 rmc=V
```

El GPS está entregando NMEA, pero todavía no tiene fix.

```text
[GPS] mode=ON/BUSCANDO newChars=0
[GPS-RECOVERY] Inicio | motivo=sin caracteres NMEA
```

No despertó la UART del GPS y el firmware está reintentando.

```text
[GPS] ... fixQ=1 rmc=A valid=YES HR20=1 lat=... lon=...
```

Fix válido.

## Prueba

Al salir del rango de beacons, espera hasta 120 segundos a cielo abierto,
especialmente porque el RESET puede producir un arranque GNSS en frío.

## Comandos

```powershell
cd "C:USERPROFILE\pruebalilygo\PlatformIO_Minerguard_TEcho_6_GPS_AUTO_SEGUN_BEACON_V3_WAKE_RECOVERY"

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t clean

& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20
```

Doble clic en RESET y subir:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" run -e minerguard_techo_6_gps_hr20 -t upload
```

Monitor:

```powershell
& "$env:USERPROFILE\.platformio\penv\Scripts\platformio.exe" device monitor -e minerguard_techo_6_gps_hr20 -b 115200
```
