# Minerguard

## Introducción

Este repositorio contiene una versión inicial del programa asociado al control de una lámpara o sistema de señalización visual utilizado dentro del proyecto MinerGuard.

El objetivo principal es permitir el encendido, apagado o cambio de estado de una salida luminosa mediante comandos simples, facilitando pruebas de integración con microcontroladores, Node-RED, Ignition u otros sistemas de control.

## Descripción general

El programa está pensado para recibir comandos y activar una respuesta visual, por ejemplo:

- Encender una luz.
- Cambiar el color o estado de la lámpara.
- Apagar la salida.
- Representar estados de alarma o prueba.

Este apartado funciona como base para futuras versiones más completas del sistema.

## Requisitos generales

- Placa microcontroladora compatible.
- Arduino IDE o PlatformIO.
- Cable USB para programación.
- Sistema de iluminación, LED o módulo de salida.
- Librerías según la placa y versión utilizada.

## Uso básico

1. Abrir el proyecto en Arduino IDE o PlatformIO.
2. Seleccionar la placa correspondiente.
3. Configurar el puerto USB.
4. Compilar el código.
5. Subir el programa al microcontrolador.
6. Enviar comandos de prueba para verificar el funcionamiento.

## Integración

Este programa puede integrarse posteriormente con:

- Node-RED.
- Ignition.
- Comunicación serial USB.
- Sistemas de alarma o señalización de MinerGuard.

## Próximas incorporaciones

Más adelante se agregarán generadores y versiones preparadas para PlatformIO, con su respectiva configuración, archivos auxiliares y documentación específica.

## Estado del proyecto

Versión inicial orientada a pruebas y documentación general.
