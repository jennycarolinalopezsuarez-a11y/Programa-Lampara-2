# MinerGuard - Visor CSV y Carga de Trabajadores a MariaDB

Aplicación de escritorio en Python para leer archivos `nodes.csv` generados por los **generadores MinerGuard**, visualizar el inventario de trabajadores, editar datos personales, asociar fotografías y cargar o actualizar la información en una base de datos **MariaDB**.

Este programa está pensado como una herramienta complementaria a los generadores de códigos de MinerGuard. Los generadores crean los nodos/dispositivos, sus credenciales LoRaWAN y archivos CSV de respaldo; este visor toma esos CSV y los transforma en registros útiles para la tabla `trabajador` dentro de MariaDB.

---

## 1. Introducción

En el flujo de trabajo de MinerGuard existen dos etapas principales:

### 1. Generadores de códigos

Los generadores crean archivos para programar dispositivos como:

```text
Heltec T114
LilyGO T-Echo
otros nodos MinerGuard
```

Normalmente estos generadores producen:

```text
archivo .ino
archivos auxiliares .h / .cpp
nodes.csv
CSV para importación en UG65
credenciales OTAA
```

El archivo más importante para este programa es:

```text
nodes.csv
```

Ese archivo contiene información del dispositivo, trabajador o nodo, como:

```text
node_id
person / person_name
devEUI
appKey
band_mac
period_ms
creation_date / created_at
```

### 2. Visor CSV + MariaDB

Este programa abre el `nodes.csv`, normaliza la información y permite completar datos que no siempre vienen desde el generador, por ejemplo:

```text
nombres
apellidos
empresa
proyecto
fecha de ingreso
fecha de nacimiento
fotografía del trabajador
```

Luego permite guardar esa información en uno o más servidores MariaDB.

---

## 2. ¿Para qué sirve este programa?

Sirve para administrar el inventario de trabajadores y dispositivos MinerGuard desde una interfaz gráfica simple.

Permite:

- Abrir un archivo `nodes.csv`.
- Ver los trabajadores en una tabla.
- Editar nombres y apellidos.
- Seleccionar empresa.
- Seleccionar proyecto.
- Agregar fecha de ingreso.
- Agregar fecha de nacimiento.
- Adjuntar fotografía del trabajador.
- Copiar la fila seleccionada al portapapeles.
- Guardar la información en MariaDB.
- Probar conexión con distintos servidores MariaDB.
- Guardar en servidor actual.
- Guardar en servidor nuevo seleccionado.
- Guardar en ambos servidores nuevos.
- Guardar en todos los servidores configurados.
- Recuperar datos ya guardados desde MariaDB.
- Guardar respaldo local para no perder cambios al reabrir el CSV.

---

## 3. Archivo principal

El archivo principal del proyecto es:

```text
Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
```

Este archivo contiene toda la aplicación:

```text
interfaz Tkinter
lectura de CSV
normalización de datos
edición de trabajadores
selección de fotografías
conexión a MariaDB
creación/actualización de tabla trabajador
guardado en múltiples IP
respaldo local en JSON
```

---

## 4. Archivos que utiliza o genera

### Archivo de entrada principal

```text
nodes.csv
```

Es el archivo generado por los generadores MinerGuard. Contiene los nodos, trabajadores y credenciales asociadas.

### Archivo de respaldo local

Cuando se edita información desde la interfaz, el programa crea un archivo auxiliar junto al CSV:

```text
nodes_trabajadores_guardado.json
```

Este archivo permite recuperar datos editados aunque se vuelva a abrir el mismo `nodes.csv`.

Guarda información como:

```text
empresa
proyecto
fecha_ingreso
fecha_nacimiento
fotografía en base64
ruta de fotografía
```

### Tabla MariaDB utilizada

El programa crea o actualiza la tabla:

```text
trabajador
```

Esta tabla almacena:

```text
id_dispositivo
nombres
apellidos
empresa
proyecto
fecha_ingreso
fecha_nacimiento
fotografia
fecha_actualizacion
```

---

## 5. Requisitos

### Sistema operativo

Funciona en:

```text
Windows
Linux
Ubuntu
Debian
Raspberry Pi OS
```

### Python

Se recomienda usar Python 3.10 o superior.

Descarga oficial:

```text
https://www.python.org/downloads/
```

### MariaDB

Servidor de base de datos recomendado:

```text
MariaDB Server
```

Página oficial:

```text
https://mariadb.org/
```

---

## 6. Librerías necesarias

El programa usa principalmente librerías estándar de Python:

```python
csv
json
base64
datetime
pathlib
tkinter
```

La única librería externa necesaria es:

```text
pymysql
```

Instalación:

```bash
pip install pymysql
```

En Linux, si falta Tkinter:

```bash
sudo apt update
sudo apt install python3-tk
```

---

## 7. Instalación rápida en Windows

1. Instalar Python desde:

```text
https://www.python.org/downloads/
```

2. Abrir PowerShell o CMD.

3. Instalar PyMySQL:

```powershell
pip install pymysql
```

4. Ir a la carpeta donde está el archivo:

```powershell
cd "C:\ruta\del\proyecto"
```

5. Ejecutar:

```powershell
python Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
```

---

## 8. Instalación rápida en Linux / Ubuntu

Actualizar sistema:

```bash
sudo apt update
sudo apt upgrade -y
```

Instalar Python, Tkinter y pip:

```bash
sudo apt install -y python3 python3-pip python3-tk
```

Instalar PyMySQL:

```bash
pip3 install pymysql
```

Ejecutar el programa:

```bash
python3 Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
```

---

## 9. Configuración de MariaDB en el script

En la parte superior del archivo se encuentra la configuración de MariaDB.

El programa maneja un servidor actual y dos IP para un nuevo servidor.

Ejemplo de estructura interna:

```python
DB_CONFIG = {
    "host": "IP_SERVIDOR_ACTUAL",
    "port": 3306,
    "user": "USUARIO",
    "password": "PASSWORD",
    "database": "minerguard",
    "charset": "utf8mb4",
    "autocommit": False,
    "connect_timeout": 5,
}
```

También existen configuraciones para:

```text
nuevo servidor por red 100
nuevo servidor por red 60
nuevo servidor seleccionado desde la interfaz
```

---

## 10. Advertencia importante sobre credenciales

No se recomienda subir contraseñas reales a GitHub.

Antes de subir el proyecto a un repositorio público, reemplazar datos sensibles como:

```text
usuario real
password real
IP internas privadas si no quieres exponerlas
```

Por valores de ejemplo:

```python
"user": "TU_USUARIO",
"password": "TU_PASSWORD",
"host": "IP_DEL_SERVIDOR",
```

También puedes crear un archivo `.env` en versiones futuras para separar las credenciales del código.

---

## 11. Base de datos esperada

El programa usa la base de datos:

```text
minerguard
```

Si no existe, crearla en MariaDB:

```sql
CREATE DATABASE minerguard CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Crear usuario de ejemplo:

```sql
CREATE USER 'minerguard_user'@'%' IDENTIFIED BY 'CAMBIAR_PASSWORD';
GRANT ALL PRIVILEGES ON minerguard.* TO 'minerguard_user'@'%';
FLUSH PRIVILEGES;
```

---

## 12. Tabla `trabajador`

El programa puede crear automáticamente la tabla `trabajador` si no existe.

Estructura base:

```sql
CREATE TABLE IF NOT EXISTS trabajador (
    id_dispositivo INT NOT NULL,
    nombres VARCHAR(120) NULL,
    apellidos VARCHAR(120) NULL,
    empresa VARCHAR(120) NULL,
    proyecto VARCHAR(120) NULL,
    fecha_ingreso DATE NULL,
    fecha_nacimiento DATE NULL,
    fotografia LONGBLOB NULL,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id_dispositivo)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

La fotografía se guarda como:

```text
LONGBLOB
```

---

## 13. Permitir conexión remota a MariaDB

Si Node-RED o este programa se conectan desde otro equipo, revisar la configuración de MariaDB.

Editar:

```bash
sudo nano /etc/mysql/mariadb.conf.d/50-server.cnf
```

Buscar:

```ini
bind-address = 127.0.0.1
```

Cambiar por:

```ini
bind-address = 0.0.0.0
```

Reiniciar MariaDB:

```bash
sudo systemctl restart mariadb
```

Verificar puerto:

```bash
sudo ss -ltnp | grep 3306
```

Probar conexión desde Windows:

```powershell
Test-NetConnection IP_DEL_SERVIDOR -Port 3306
```

---

## 14. Uso paso a paso

### Paso 1: Ejecutar el programa

Windows:

```powershell
python Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
```

Linux:

```bash
python3 Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
```

---

### Paso 2: Abrir `nodes.csv`

Presionar el botón:

```text
📂 Abrir archivo nodes.csv
```

Seleccionar el archivo generado por el generador MinerGuard.

El programa cargará las filas válidas y omitirá las que no tengan ID de dispositivo.

---

### Paso 3: Revisar tabla de trabajadores

La tabla muestra columnas como:

```text
ID Dispositivo
Trabajador CSV
Nombres
Apellidos
Empresa
Proyecto
Fecha ingreso
Fecha nacimiento
Foto
DevEUI
AppKey
MAC Pulsera
Periodo
Fecha creación CSV
```

---

### Paso 4: Editar trabajador

Seleccionar una fila y presionar:

```text
✏️ Editar trabajador / agregar foto
```

También se puede abrir el editor con doble clic sobre una fila.

Desde esa ventana puedes modificar:

```text
nombres
apellidos
empresa
proyecto
fecha de ingreso
fecha de nacimiento
fotografía
```

---

### Paso 5: Agregar fotografía

Dentro del editor, presionar:

```text
📷 Seleccionar foto
```

Formatos aceptados:

```text
jpg
jpeg
png
bmp
gif
webp
```

La imagen se guardará en MariaDB como `LONGBLOB`.

---

### Paso 6: Quitar fotografía

Dentro del editor, presionar:

```text
🗑️ Quitar foto
```

Esto marca la fila para eliminar la fotografía existente en MariaDB al guardar.

---

### Paso 7: Guardar cambios locales

Al presionar:

```text
Guardar cambios
```

El programa actualiza la tabla visual y guarda respaldo local junto al CSV.

Eso evita perder:

```text
cumpleaños
empresa
proyecto
fotos
fechas
```

cuando se vuelve a abrir el mismo `nodes.csv`.

---

## 15. Valores por defecto

El programa permite definir empresa y proyecto por defecto para filas vacías.

Panel:

```text
Valores por defecto para filas sin empresa/proyecto
```

Opciones internas de empresa:

```text
FMT
Drilltech
GeoMining
Minera Sur
EmpresaX
```

Opciones internas de proyecto:

```text
Diamante
Esmeralda
Andesita
Andes Norte
Diablo Regimiento
```

Botón:

```text
Aplicar a filas vacías
```

Este botón solo completa filas donde empresa o proyecto estén vacíos.

---

## 16. Botones de conexión MariaDB

El panel superior incluye:

```text
🔌 Probar actual
🔌 Probar nuevo seleccionado
🔌 Probar ambos nuevos
```

### Probar actual

Prueba conexión con el servidor definido como actual.

### Probar nuevo seleccionado

Prueba conexión con la IP seleccionada en el combo de nuevo servidor.

### Probar ambos nuevos

Prueba conexión con las dos IP configuradas para el nuevo servidor.

---

## 17. Botones de guardado MariaDB

El programa permite guardar en distintos destinos:

```text
💾 Guardar actual
💾 Guardar nuevo seleccionado
💾 Guardar ambos nuevos
💾 Guardar todos
```

### Guardar actual

Guarda solo en el servidor actual.

### Guardar nuevo seleccionado

Guarda en la IP seleccionada desde la interfaz.

### Guardar ambos nuevos

Guarda en las dos IP del nuevo servidor.

### Guardar todos

Guarda en:

```text
servidor actual
nuevo servidor IP red 100
nuevo servidor IP red 60
```

---

## 18. Cómo el programa recupera datos

Al volver a abrir un `nodes.csv`, el programa intenta recuperar datos desde tres lugares:

### 1. MariaDB servidor actual

Busca trabajadores existentes por `id_dispositivo`.

### 2. MariaDB nuevos servidores

Busca información en las dos IP configuradas para el nuevo servidor.

### 3. Respaldo local JSON

Carga el archivo local:

```text
nodes_trabajadores_guardado.json
```

Esto permite que la tabla vuelva a mostrar datos ya editados.

---

## 19. Formatos de fecha aceptados

El programa acepta:

```text
YYYY-MM-DD
DD/MM/YYYY
DD-MM-YYYY
YYYY/MM/DD
```

Ejemplos válidos:

```text
2026-05-18
18/05/2026
18-05-2026
2026/05/18
```

Internamente se guarda como:

```text
YYYY-MM-DD
```

---

## 20. Compatibilidad con distintos CSV de generadores

El programa intenta ser compatible con CSV antiguos y nuevos.

Puede leer campos como:

```text
node_id
id_dispositivo
ug65_name
name
```

Para nombres puede leer:

```text
person
person_name
trabajador
description
nombre
```

Para fechas puede leer:

```text
creation_date
created_at
fecha_creacion
fecha_ingreso
fecha_nacimiento
```

Para credenciales puede leer:

```text
devEUI
deveui
appKey
appkey
```

Para banda puede leer:

```text
band_mac
mac_pulsera
mac_banda
```

---

## 21. Lógica de nombres y apellidos

Si el CSV no trae columnas separadas de `nombres` y `apellidos`, el programa intenta separarlos desde el nombre completo.

Regla usada:

| Cantidad de palabras | Resultado |
|---|---|
| 1 palabra | `nombres = palabra`, `apellidos = vacío` |
| 2 palabras | primera como nombre, segunda como apellido |
| 3 palabras | primera como nombre, últimas dos como apellidos |
| 4 o más palabras | todas menos las últimas dos como nombres, últimas dos como apellidos |

También soporta formato:

```text
Apellidos, Nombres
```

---

## 22. Copiar fila seleccionada

Botón:

```text
📋 Copiar fila seleccionada
```

Copia al portapapeles:

```text
ID dispositivo
Trabajador CSV
Nombres
Apellidos
Empresa
Proyecto
Fecha ingreso
Fecha nacimiento
Fotografía
DevEUI
AppKey
MAC Pulsera
Generado el
```

---

## 23. Flujo recomendado de trabajo

```text
1. Generar códigos MinerGuard con el generador correspondiente.
2. Obtener el archivo nodes.csv.
3. Abrir este programa.
4. Cargar nodes.csv.
5. Revisar cada trabajador.
6. Editar empresa, proyecto, fechas y fotografía.
7. Probar conexión MariaDB.
8. Guardar en servidor actual o nuevo.
9. Verificar en MariaDB que la tabla trabajador quedó actualizada.
```

---

## 24. Consultas útiles en MariaDB

Entrar a MariaDB:

```bash
mariadb -u minerguard_user -p minerguard
```

Ver trabajadores:

```sql
SELECT id_dispositivo, nombres, apellidos, empresa, proyecto, fecha_ingreso, fecha_nacimiento
FROM trabajador
ORDER BY id_dispositivo;
```

Ver si hay fotografías cargadas:

```sql
SELECT id_dispositivo, nombres, apellidos,
       CASE WHEN fotografia IS NULL THEN 'SIN FOTO' ELSE 'CON FOTO' END AS estado_foto
FROM trabajador
ORDER BY id_dispositivo;
```

Contar trabajadores:

```sql
SELECT COUNT(*) AS total_trabajadores
FROM trabajador;
```

---

## 25. Problemas frecuentes

### Error: falta PyMySQL

Mensaje probable:

```text
Falta instalar pymysql
```

Solución:

```bash
pip install pymysql
```

---

### Error: no se puede conectar a MariaDB

Revisar:

```text
IP del servidor
puerto 3306
usuario
password
base de datos
firewall
bind-address de MariaDB
```

Comando útil en servidor:

```bash
sudo ss -ltnp | grep 3306
```

---

### Error: archivo CSV no carga

Revisar:

```text
que sea .csv
que tenga encabezados
que tenga node_id, id_dispositivo, ug65_name o name
que esté guardado en UTF-8
```

---

### La foto no aparece al reabrir el CSV

El programa intenta recuperarla desde:

```text
MariaDB
respaldo local JSON
```

Revisar que se haya presionado un botón de guardado en MariaDB o que exista el archivo:

```text
nodes_trabajadores_guardado.json
```

---

### La fecha aparece vacía

Puede ocurrir si la fecha está en un formato no reconocido.

Usar uno de estos formatos:

```text
YYYY-MM-DD
DD/MM/YYYY
DD-MM-YYYY
YYYY/MM/DD
```

---

## 26. Seguridad y GitHub

No subir a GitHub:

```text
passwords reales
usuarios reales de base de datos
IP internas si no quieres exponerlas
fotografías reales de trabajadores
nodes.csv con credenciales reales
archivos JSON con fotos en base64
```

Se recomienda subir solo ejemplos:

```text
nodes_ejemplo.csv
README.md
schema.sql
```

---

## 27. .gitignore recomendado

```gitignore
# Credenciales y datos reales
nodes.csv
*_trabajadores_guardado.json
*.db
*.sqlite

# Fotografías reales
fotos/
*.jpg
*.jpeg
*.png
*.webp

# Python
__pycache__/
*.pyc
.venv/
venv/

# Sistema
.DS_Store
Thumbs.db

# Backups
*.bak
*.tmp
```

---

## 28. Estructura recomendada del repositorio

```text
MinerGuard_CSV_MariaDB/
├── README.md
├── Lectura_csv_mariadb_trabajador_foto_TRIPLE_IP_V5.py
├── sql/
│   └── schema_trabajador.sql
├── examples/
│   └── nodes_ejemplo.csv
└── docs/
    └── flujo_generadores_mariadb.md
```

---

## 29. Links útiles

### Python

```text
https://www.python.org/downloads/
```

### PyMySQL

```text
https://pymysql.readthedocs.io/
```

### MariaDB

```text
https://mariadb.org/
```

### Tkinter

```text
https://docs.python.org/3/library/tkinter.html
```

### GitHub Docs

```text
https://docs.github.com/
```

---

## 30. Resumen final

Este programa conecta la etapa de generación de códigos MinerGuard con la base de datos MariaDB.

Los generadores crean los dispositivos y el archivo `nodes.csv`.

Este visor permite completar la información humana y administrativa del trabajador, agregar fotografía y guardar todo en la tabla `trabajador`.

Flujo resumido:

```text
Generador MinerGuard
        ↓
nodes.csv
        ↓
Visor CSV MariaDB
        ↓
tabla trabajador
        ↓
Ignition / Node-RED / sistema MinerGuard
```
