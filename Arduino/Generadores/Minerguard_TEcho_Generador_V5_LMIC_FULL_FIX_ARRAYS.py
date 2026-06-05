#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador MinerGuard LilyGO T-Echo V5 LMIC FULL.

Base estable:
- MCCI LMIC + SX1262 + UG65
- OTAA JOIN probado con EV_JOINED / EV_TXSTART / EV_TXCOMPLETE
- Payload 36 bytes compatible con Node-RED actual
- Beacons, banda cardiaca BLE, batería banda, pánico, doble click luz y e-paper
"""

from __future__ import annotations

import csv
import datetime
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

UG65_HEADERS = [
    "name",
    "description",
    "deveui",
    "deviceprofile",
    "application",
    "payloadcodec",
    "fport",
    "appkey",
    "devaddr",
    "nwkskey",
    "appskey",
    "timeout",
]

BASE_INO_TEMPLATE = '/********************************************************************\n * Minerguard para LILYGO T-Echo nRF52840\n * Adaptacion desde Minerguard_2.ino / Heltec T114\n *\n * Mantiene:\n *   - Banda cardiaca BLE estricta por MAC: E3:FD:1A:F2:F3:AF\n *   - Heart Rate Service 0x180D / Measurement 0x2A37\n *   - Battery Service 0x180F / Battery Level 0x2A19\n *   - Beacons MinerGuard tipo iBeacon:\n *       Major = nivel / sector\n *       Minor = PK\n *   - Top 3 beacons por RSSI con suavizado\n *   - Boton de panico por USER button\n *   - Doble click USER para encender/apagar iluminacion de pantalla\n *   - Payload extendido de 36 bytes igual a la logica Heltec\n *\n * Diferencia importante:\n *   La Heltec usa TFT ST7789 240x135 y permite animacion fluida.\n *   La T-Echo usa e-paper 200x200, por lo que la pantalla se actualiza\n *   lento. El LED rojo late en tiempo real; la pantalla muestra un frame\n *   grande/pequeno del corazon cada refresco.\n *\n * Archivos requeridos en la misma carpeta:\n *   - Minerguard_TEcho_Final.ino\n *   - utilities.h  (el definitivo de LILYGO T-Echo que subiste)\n ********************************************************************/\n\n#include "utilities.h"\n\n#include <Arduino.h>\n#include <SPI.h>\n#include <Wire.h>\n#include <Adafruit_TinyUSB.h>\n#include <bluefruit.h>\n#include <lmic.h>\n#include <hal/hal.h>\n\n#include <GxEPD.h>\n#include <GxDEPG0150BN/GxDEPG0150BN.h>\n#include <Fonts/FreeMonoBold9pt7b.h>\n#include <Fonts/FreeMonoBold12pt7b.h>\n#include <Fonts/FreeMonoBold18pt7b.h>\n#include <GxIO/GxIO_SPI/GxIO_SPI.h>\n#include <GxIO/GxIO.h>\n\n/* =========================================================\n   CONFIGURACION DEL TAG\n   ========================================================= */\n#define BUTTON_PIN UserButton_Pin\n\nstatic const uint16_t NODE_ID = 4;\nstatic const char PERSON_NAME[] = "Rodrigo Zuniga";\nstatic const char NODE_LABEL[]  = "4";\n\n// No cambiar la banda cardiaca.\nstatic const char BAND_MAC_TARGET[] = "E3:FD:1A:F2:F3:AF";\nstatic const uint8_t BAND_MAC_NORMAL[6]   = { 0xE3, 0xFD, 0x1A, 0xF2, 0xF3, 0xAF };\nstatic const uint8_t BAND_MAC_REVERSED[6] = { 0xAF, 0xF3, 0xF2, 0x1A, 0xFD, 0xE3 };\n\n\n/* =========================================================\n   LORAWAN MCCI LMIC + SX1262 + UG65\n   =========================================================\n   Diagnostico V4 ya comprobó EV_TXSTART / EV_TXCOMPLETE.\n   Esta versión integra ese bloque al firmware completo con:\n   pantalla, beacons, banda cardiaca, panico, doble click y payload 36B.\n   ========================================================= */\n\nstatic const uint8_t LORAWAN_APP_PORT = 1;\nstatic bool lmicJoined = false;\nstatic bool lmicTxPending = false;\nstatic uint32_t lastLmicKick = 0;\n\n// IMPORTANTE LMIC:\n// AppEUI / JoinEUI y DevEUI van en little-endian, es decir, invertidos.\n// AppKey va normal, igual que en UG65.\nstatic const u1_t PROGMEM APPEUI[8] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };\nstatic const u1_t PROGMEM DEVEUI[8] = { 0x13, 0x8C, 0xD6, 0x48, 0x0A, 0x7B, 0x20, 0x70 };\nstatic const u1_t PROGMEM APPKEY[16] = { 0x19, 0xB7, 0xC8, 0x63, 0x70, 0x89, 0xDB, 0x9A, 0xE7, 0xE5, 0xA5, 0x10, 0xC1, 0xE9, 0x78, 0xCB };\n\nvoid os_getArtEui(u1_t* buf) { memcpy_P(buf, APPEUI, 8); }\nvoid os_getDevEui(u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }\nvoid os_getDevKey(u1_t* buf) { memcpy_P(buf, APPKEY, 16); }\n\nclass T_EchoHalConfiguration_t : public Arduino_LMIC::HalConfiguration_t {\npublic:\n  virtual u1_t queryBusyPin(void) override { return LoRa_Busy; }\n  virtual bool queryUsingDcdc(void) override { return true; }\n  virtual bool queryUsingDIO2AsRfSwitch(void) override { return true; }\n  virtual bool queryUsingDIO3AsTCXOSwitch(void) override { return true; }\n};\n\nstatic T_EchoHalConfiguration_t myLmicConfig;\n\nconst lmic_pinmap lmic_pins = {\n  .nss = LoRa_Cs,\n  .rxtx = LMIC_UNUSED_PIN,\n  .rst = LoRa_Rst,\n  .dio = {LoRa_Dio1, LMIC_UNUSED_PIN, LMIC_UNUSED_PIN},\n  .rxtx_rx_active = 0,\n  .rssi_cal = 10,\n  .spi_freq = 8000000,\n  .pConfig = &myLmicConfig,\n};\n\nvoid setupLoRaWAN();\nvoid onEvent(ev_t ev);\nbool sendLoRaWANPayloadNow(const uint8_t *data, uint8_t len);\n\n// UUID MinerGuard usado en el codigo Heltec.\nstatic const uint8_t MINERGUARD_UUID[16] = {\n  0xE2, 0xC5, 0x6D, 0xB5, 0xDF, 0xFB, 0x48, 0xD2,\n  0xB0, 0x60, 0xD0, 0xF5, 0xA7, 0x10, 0x96, 0xE0\n};\n\n/* =========================================================\n   DISPLAY E-PAPER T-ECHO\n   ========================================================= */\nSPIClass    *dispPort = nullptr;\nGxIO_Class  *io       = nullptr;\nGxEPD_Class *display  = nullptr;\n\nstatic const uint16_t EPD_W = 200;\nstatic const uint16_t EPD_H = 200;\n\nstatic bool screenNeedsUpdate = true;\nstatic uint32_t lastScreenUpdate = 0;\nstatic const uint32_t SCREEN_MIN_INTERVAL_MS = 1800;\n\nchar scrLine1[32] = "Iniciando";\nchar scrLine2[32] = "Buscando Beacons";\nchar scrLine3[32] = "Rodrigo Zuniga";\n\nbool heartBigFrame = false;\n\n/* =========================================================\n   BLE HEART RATE / BATTERY\n   ========================================================= */\nBLEClientService        svcHR(UUID16_SVC_HEART_RATE);\nBLEClientCharacteristic chrHR(UUID16_CHR_HEART_RATE_MEASUREMENT);\nBLEClientService        svcBAT(UUID16_SVC_BATTERY);\nBLEClientCharacteristic chrBAT(UUID16_CHR_BATTERY_LEVEL);\n\nvolatile bool bleConnected = false;\nvolatile bool hrValid = false;\nvolatile uint8_t hrBpm = 0;\nvolatile bool bandBatValid = false;\nvolatile uint8_t bandBatPct = 0;\n\nuint32_t beatIntervalMs = 1000;\nuint32_t lastBeatMs = 0;\nuint32_t nextBeatMs = 0;\nuint32_t lastLedPulseMs = 0;\n\nuint32_t lastScanKick = 0;\n\n/* =========================================================\n   BEACONS\n   ========================================================= */\nstruct BeaconReading {\n  bool valid;\n  uint16_t major;\n  uint16_t minor;\n  int8_t rssi;\n  uint32_t seenAt;\n};\n\nBeaconReading topBeacons[3] = {\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0}\n};\n\nBeaconReading snapshotA[3] = {\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0}\n};\n\nBeaconReading snapshotB[3] = {\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0},\n  {false, 0, 0, -127, 0}\n};\n\nstatic const uint32_t BEACON_TIMEOUT_MS = 15000;\n\n/* =========================================================\n   PANICO / ENVIO\n   ========================================================= */\nvolatile bool panicActive = false;\nvolatile bool isPressingButton = false;\n\nbool buttonPrev = false;\nuint32_t buttonPressStart = 0;\nbool buttonHeld = false;\nuint32_t panicEndMs = 0;\n\n// Iluminacion de pantalla por doble click del USER.\n// Se detecta con interrupcion para no perder clicks mientras la e-paper\n// esta haciendo display->update(), que bloquea el loop por algunos segundos.\nstatic bool backlightOn = false;\nstatic const uint8_t BACKLIGHT_ON_LEVEL  = HIGH;\nstatic const uint8_t BACKLIGHT_OFF_LEVEL = LOW;\n\nstatic const uint32_t HOLD_TIME_MS = 1500;\nstatic const uint32_t PANIC_DURATION_MS = 60000;\nstatic const uint32_t DOUBLE_CLICK_MS = 650;\nstatic const uint32_t BUTTON_DEBOUNCE_MS = 35;\n\nvolatile bool backlightToggleRequest = false;\nvolatile uint32_t isrLastButtonChange = 0;\nvolatile uint32_t isrButtonPressStart = 0;\nvolatile uint32_t isrLastShortRelease = 0;\n\nvolatile bool requestImmediateTx = false;\nvolatile bool snapshotATaken = false;\nuint32_t lastPeriodicSend = 0;\nstatic const uint32_t TX_INTERVAL_MS = 15000;\n\nuint8_t appData[64];\nuint8_t appDataSize = 0;\n\n/* =========================================================\n   PROTOTIPOS\n   ========================================================= */\nvoid boardInit();\nvoid setupDisplay();\nvoid drawMainScreen();\nvoid drawSplash(const char *title, const char *sub);\nvoid drawHeart(int cx, int cy, int size, bool big);\nvoid drawTopBeaconsList(int x, int y);\nvoid requestScreenUpdate(const char *l1, const char *l2, const char *l3);\nvoid updateDisplayPosition();\nvoid handlePanicButton();\nvoid userButtonISR();\nvoid processBacklightToggle();\nvoid setScreenBacklight(bool on);\nvoid toggleScreenBacklight();\nvoid updateLedHeartbeat();\n\nbool matchBandByMac(const ble_gap_addr_t &addr);\nvoid macToString(const ble_gap_addr_t &addr, char *out, size_t len);\nvoid scan_cb(ble_gap_evt_adv_report_t *report);\nvoid connect_cb(uint16_t conn_handle);\nvoid disconnect_cb(uint16_t conn_handle, uint8_t reason);\nvoid hr_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len);\nvoid bat_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len);\n\nbool parseIBeacon(ble_gap_evt_adv_report_t *report, uint16_t &major, uint16_t &minor);\nvoid updateTopBeacon(uint16_t major, uint16_t minor, int8_t rssi);\nvoid cleanupOldBeacons();\nvoid sortTopBeacons();\n\nuint8_t encodeRSSI(int8_t rssi);\nvoid buildExtendedPayload(uint8_t *out, uint8_t &sz, bool panic);\nvoid printPayloadHex(const uint8_t *data, uint8_t len);\n\n/* =========================================================\n   SETUP\n   ========================================================= */\nvoid setup() {\n  boardInit();\n\n  SerialMon.println("======================================");\n  SerialMon.println("[BOOT] SKETCH GENERADO POR: V5_LMIC_FULL");\n  SerialMon.print("[BOOT] NODE_ID: ");\n  SerialMon.println(NODE_ID);\n  SerialMon.print("[BOOT] PERSON_NAME: ");\n  SerialMon.println(PERSON_NAME);\n  SerialMon.print("[BOOT] NODE_LABEL: ");\n  SerialMon.println(NODE_LABEL);\n  SerialMon.print("[BOOT] DevEUI UG65: ");\n  SerialMon.println("70207B0A48D68C13");\n  SerialMon.println("======================================");\n\n  drawSplash("MINERGUARD", "Iniciando T-Echo");\n  delay(1200);\n\n  pinMode(BUTTON_PIN, INPUT_PULLUP);\n  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), userButtonISR, CHANGE);\n\n  Bluefruit.begin(0, 1);\n  Bluefruit.setName(NODE_LABEL);\n  Bluefruit.setTxPower(4);\n\n  svcHR.begin();\n  chrHR.begin();\n\n  svcBAT.begin();\n  chrBAT.begin();\n\n  Bluefruit.Central.setConnectCallback(connect_cb);\n  Bluefruit.Central.setDisconnectCallback(disconnect_cb);\n\n  Bluefruit.Scanner.setRxCallback(scan_cb);\n  Bluefruit.Scanner.filterRssi(-95);\n  Bluefruit.Scanner.setInterval(160, 160);\n  Bluefruit.Scanner.useActiveScan(false);\n  Bluefruit.Scanner.restartOnDisconnect(true);\n  Bluefruit.Scanner.start(0);\n\n  setupLoRaWAN();\n\n  requestScreenUpdate("Minerguard", "Escaneando...", PERSON_NAME);\n\n  lastPeriodicSend = millis();\n  nextBeatMs = millis() + beatIntervalMs;\n}\n\n/* =========================================================\n   LOOP\n   ========================================================= */\nvoid loop() {\n  uint32_t now = millis();\n\n  // Mantiene viva la maquina LoRaWAN LMIC.\n  os_runloop_once();\n\n  // Procesa el doble click capturado por interrupcion. No refresca pantalla.\n  processBacklightToggle();\n\n  // Mantener scanner activo como en Heltec.\n  if (now - lastScanKick > 1500) {\n    lastScanKick = now;\n    if (!Bluefruit.Scanner.isRunning()) {\n      Bluefruit.Scanner.start(0);\n    }\n  }\n\n  handlePanicButton();\n  updateLedHeartbeat();\n\n  // Snapshot A a mitad de ventana, igual a la idea del codigo Heltec.\n  uint32_t elapsed = now - lastPeriodicSend;\n  if (elapsed >= 15000 && !snapshotATaken) {\n    cleanupOldBeacons();\n    sortTopBeacons();\n    memcpy(snapshotA, topBeacons, sizeof(topBeacons));\n    snapshotATaken = true;\n  }\n\n  // Preparar payload cada 15s o inmediatamente por panico.\n  if (elapsed >= TX_INTERVAL_MS || requestImmediateTx) {\n    requestImmediateTx = false;\n    buildExtendedPayload(appData, appDataSize, panicActive);\n\n    SerialMon.print("[PAYLOAD 36B] ");\n    printPayloadHex(appData, appDataSize);\n    SerialMon.println();\n\n    if (lmicJoined) {\n      sendLoRaWANPayloadNow(appData, appDataSize);\n    } else {\n      SerialMon.println("[LMIC] Payload listo, esperando EV_JOINED para TX real.");\n    }\n  }\n\n  // Actualizar posicion por timeout de beacons.\n  static uint32_t lastPositionRefresh = 0;\n  if (now - lastPositionRefresh > 2000) {\n    lastPositionRefresh = now;\n    cleanupOldBeacons();\n    sortTopBeacons();\n    updateDisplayPosition();\n  }\n\n  // Refresco de e-paper: lento, no como TFT.\n  if (screenNeedsUpdate && (now - lastScreenUpdate >= SCREEN_MIN_INTERVAL_MS)) {\n    if (!(LMIC.opmode & OP_TXRXPEND)) {\n      lastScreenUpdate = now;\n      screenNeedsUpdate = false;\n      drawMainScreen();\n    }\n  }\n\n  // Segunda pasada LMIC al final del loop para no atrasar eventos.\n  os_runloop_once();\n}\n\n/* =========================================================\n   HARDWARE / DISPLAY\n   ========================================================= */\nvoid boardInit() {\n  SerialMon.begin(MONITOR_SPEED);\n  delay(200);\n\n  pinMode(Power_Enable_Pin, OUTPUT);\n  digitalWrite(Power_Enable_Pin, HIGH);\n\n  pinMode(ePaper_Backlight, OUTPUT);\n  digitalWrite(ePaper_Backlight, BACKLIGHT_OFF_LEVEL);\n  backlightOn = false;\n\n  pinMode(GreenLed_Pin, OUTPUT);\n  pinMode(RedLed_Pin, OUTPUT);\n  pinMode(BlueLed_Pin, OUTPUT);\n\n  digitalWrite(GreenLed_Pin, HIGH);\n  digitalWrite(RedLed_Pin, HIGH);\n  digitalWrite(BlueLed_Pin, HIGH);\n\n  setupDisplay();\n}\n\nvoid setupDisplay() {\n  dispPort = new SPIClass(\n    NRF_SPIM2,\n    ePaper_Miso,\n    ePaper_Sclk,\n    ePaper_Mosi\n  );\n\n  io = new GxIO_Class(\n    *dispPort,\n    ePaper_Cs,\n    ePaper_Dc,\n    ePaper_Rst\n  );\n\n  display = new GxEPD_Class(\n    *io,\n    ePaper_Rst,\n    ePaper_Busy\n  );\n\n  dispPort->begin();\n  display->init();\n  display->setRotation(3);\n  SerialMon.println("[DISPLAY] Rotacion forzada: 3");\n  display->setTextColor(GxEPD_BLACK);\n\n  // Limpieza agresiva de e-paper para evitar nombres/frames fantasma.\n  display->fillScreen(GxEPD_WHITE);\n  display->update();\n  delay(200);\n  display->fillScreen(GxEPD_BLACK);\n  display->update();\n  delay(250);\n  display->fillScreen(GxEPD_WHITE);\n  display->update();\n  delay(250);\n}\n\nvoid drawSplash(const char *title, const char *sub) {\n  display->fillScreen(GxEPD_WHITE);\n  display->fillRect(0, 0, EPD_W, 34, GxEPD_BLACK);\n\n  display->setTextColor(GxEPD_WHITE);\n  display->setFont(&FreeMonoBold12pt7b);\n  display->setCursor(18, 24);\n  display->print(title);\n\n  display->setTextColor(GxEPD_BLACK);\n  display->setFont(&FreeMonoBold9pt7b);\n  display->setCursor(18, 82);\n  display->print(sub);\n\n  display->drawRoundRect(16, 112, 168, 46, 8, GxEPD_BLACK);\n  display->setCursor(34, 142);\n  display->print("BLE + BEACONS");\n\n  display->update();\n}\n\nvoid drawMainScreen() {\n  display->fillScreen(GxEPD_WHITE);\n\n  if (panicActive) {\n    display->fillRect(0, 0, EPD_W, 34, GxEPD_BLACK);\n    display->setTextColor(GxEPD_WHITE);\n    display->setFont(&FreeMonoBold12pt7b);\n    display->setCursor(38, 24);\n    display->print("PANICO");\n\n    display->setTextColor(GxEPD_BLACK);\n    display->setFont(&FreeMonoBold18pt7b);\n    display->setCursor(28, 108);\n    display->print("PANICO");\n\n    display->setFont(&FreeMonoBold9pt7b);\n    display->setCursor(16, 155);\n    display->print("Enviando alerta");\n    display->update();\n    return;\n  }\n\n  bool showHeart = bleConnected && hrValid;\n\n  // Panel superior, equivalente al layout Heltec:\n  // BPM grande a la izquierda + corazon a la derecha.\n  display->drawFastHLine(0, 68, EPD_W, GxEPD_BLACK);\n\n  if (showHeart) {\n    char bpmText[8];\n    snprintf(bpmText, sizeof(bpmText), "%u", hrBpm);\n\n    display->setFont(&FreeMonoBold18pt7b);\n    display->setCursor(14, 48);\n    if (hrBpm < 100) display->print(" ");\n    display->print(bpmText);\n\n    display->setFont(&FreeMonoBold9pt7b);\n    display->setCursor(91, 48);\n    display->print("BPM");\n\n    heartBigFrame = !heartBigFrame;\n    drawHeart(158, 35, heartBigFrame ? 18 : 14, heartBigFrame);\n  } else {\n    display->setFont(&FreeMonoBold12pt7b);\n    display->setCursor(10, 42);\n    display->print(scrLine1);\n  }\n\n  // Zona inferior de beacons/estado.\n  display->setFont(&FreeMonoBold12pt7b);\n  display->setCursor(10, 98);\n  display->print(scrLine2);\n\n  display->setFont(&FreeMonoBold9pt7b);\n  display->setCursor(10, 128);\n  display->print(scrLine3);\n\n  drawTopBeaconsList(10, 150);\n\n  if (isPressingButton && !panicActive) {\n    display->drawRoundRect(6, 174, 188, 22, 4, GxEPD_BLACK);\n    display->setFont(&FreeMonoBold9pt7b);\n    display->setCursor(14, 191);\n    display->print("Mantenga: panico");\n  }\n\n  display->update();\n}\n\nvoid drawHeart(int cx, int cy, int size, bool big) {\n  int r = size / 3;\n\n  if (big) {\n    display->drawCircle(cx, cy, size + 7, GxEPD_BLACK);\n    display->drawCircle(cx, cy, size + 2, GxEPD_BLACK);\n  }\n\n  display->fillCircle(cx - r, cy - r, r, GxEPD_BLACK);\n  display->fillCircle(cx + r, cy - r, r, GxEPD_BLACK);\n  display->fillTriangle(\n    cx - 2 * r, cy - r,\n    cx + 2 * r, cy - r,\n    cx, cy + 2 * r,\n    GxEPD_BLACK\n  );\n\n  if (big) {\n    display->fillCircle(cx - r - 2, cy - r - 3, 3, GxEPD_WHITE);\n  }\n}\n\nvoid drawTopBeaconsList(int x, int y) {\n  display->setFont(&FreeMonoBold9pt7b);\n\n  if (!topBeacons[0].valid) {\n    display->setCursor(x, y + 18);\n    display->print("Beacons: --");\n    return;\n  }\n\n  display->setCursor(x, y + 13);\n  display->print("TOP RSSI");\n\n  for (int i = 0; i < 3; i++) {\n    if (!topBeacons[i].valid) continue;\n\n    int yy = y + 31 + (i * 15);\n    display->setCursor(x, yy);\n    display->print(i + 1);\n    display->print(":PK");\n    display->print(topBeacons[i].minor);\n    display->print(" ");\n    display->print(topBeacons[i].rssi);\n  }\n}\n\n/* =========================================================\n   PANTALLA INTELIGENTE\n   ========================================================= */\nvoid requestScreenUpdate(const char *l1, const char *l2, const char *l3) {\n  bool changed =\n    strncmp(scrLine1, l1, sizeof(scrLine1) - 1) != 0 ||\n    strncmp(scrLine2, l2, sizeof(scrLine2) - 1) != 0 ||\n    strncmp(scrLine3, l3, sizeof(scrLine3) - 1) != 0;\n\n  if (!changed) return;\n\n  strncpy(scrLine1, l1, sizeof(scrLine1) - 1);\n  strncpy(scrLine2, l2, sizeof(scrLine2) - 1);\n  strncpy(scrLine3, l3, sizeof(scrLine3) - 1);\n\n  scrLine1[sizeof(scrLine1) - 1] = \'\\0\';\n  scrLine2[sizeof(scrLine2) - 1] = \'\\0\';\n  scrLine3[sizeof(scrLine3) - 1] = \'\\0\';\n\n  screenNeedsUpdate = true;\n}\n\nvoid updateDisplayPosition() {\n  if (panicActive) {\n    screenNeedsUpdate = true;\n    return;\n  }\n\n  char l1[32] = "Buscando...";\n  char l2[32] = "";\n  char l3[32] = "";\n  snprintf(l3, sizeof(l3), "%s", PERSON_NAME);\n\n  if (bleConnected && hrValid) {\n    snprintf(l1, sizeof(l1), "HR: %u bpm", hrBpm);\n\n    if (topBeacons[0].valid) {\n      snprintf(l2, sizeof(l2), "PK ACTUAL:%u", topBeacons[0].minor);\n    } else {\n      snprintf(l2, sizeof(l2), "PK: Fuera rango");\n    }\n  } else {\n    if (topBeacons[0].valid) {\n      snprintf(l1, sizeof(l1), "PK ACTUAL");\n      snprintf(l2, sizeof(l2), "%u", topBeacons[0].minor);\n    } else {\n      snprintf(l1, sizeof(l1), "Minerguard");\n      snprintf(l2, sizeof(l2), "Escaneando...");\n    }\n  }\n\n  requestScreenUpdate(l1, l2, l3);\n}\n\n/* =========================================================\n   BOTON DE PANICO / LED\n   ========================================================= */\nvoid handlePanicButton() {\n  bool reading = (digitalRead(BUTTON_PIN) == LOW);\n  uint32_t now = millis();\n\n  if (reading != isPressingButton) {\n    isPressingButton = reading;\n    screenNeedsUpdate = true;\n  }\n\n  if (reading) {\n    if (!buttonPrev) {\n      buttonPressStart = now;\n      buttonHeld = false;\n    }\n\n    if (!buttonHeld && (now - buttonPressStart) >= HOLD_TIME_MS) {\n      buttonHeld = true;\n\n      if (!panicActive) {\n        panicActive = true;\n        panicEndMs = now + PANIC_DURATION_MS;\n\n        requestImmediateTx = true;\n        screenNeedsUpdate = true;\n      }\n    }\n  }\n\n  buttonPrev = reading;\n\n  if (panicActive && ((int32_t)(now - panicEndMs) >= 0)) {\n    panicActive = false;\n    requestImmediateTx = true;\n    screenNeedsUpdate = true;\n  }\n}\n\nvoid userButtonISR() {\n  uint32_t now = millis();\n\n  // Debounce por software dentro de la ISR.\n  if ((now - isrLastButtonChange) < BUTTON_DEBOUNCE_MS) {\n    return;\n  }\n  isrLastButtonChange = now;\n\n  bool pressed = (digitalRead(BUTTON_PIN) == LOW);\n\n  if (pressed) {\n    isrButtonPressStart = now;\n    return;\n  }\n\n  uint32_t pressDuration = now - isrButtonPressStart;\n\n  // Solo los clicks cortos participan en el doble click.\n  // Una pulsacion larga queda reservada exclusivamente para panico.\n  if (pressDuration < HOLD_TIME_MS) {\n    if (isrLastShortRelease != 0 && (now - isrLastShortRelease) <= DOUBLE_CLICK_MS) {\n      backlightToggleRequest = true;\n      isrLastShortRelease = 0;\n    } else {\n      isrLastShortRelease = now;\n    }\n  } else {\n    isrLastShortRelease = 0;\n  }\n}\n\nvoid processBacklightToggle() {\n  bool shouldToggle = false;\n\n  noInterrupts();\n  if (backlightToggleRequest) {\n    backlightToggleRequest = false;\n    shouldToggle = true;\n  }\n  interrupts();\n\n  if (shouldToggle && !panicActive) {\n    toggleScreenBacklight();\n  }\n\n  // Si queda un click suelto y no llega el segundo, se descarta.\n  noInterrupts();\n  if (isrLastShortRelease != 0 && (millis() - isrLastShortRelease) > DOUBLE_CLICK_MS) {\n    isrLastShortRelease = 0;\n  }\n  interrupts();\n}\n\nvoid setScreenBacklight(bool on) {\n  backlightOn = on;\n  pinMode(ePaper_Backlight, OUTPUT);\n  digitalWrite(ePaper_Backlight, backlightOn ? BACKLIGHT_ON_LEVEL : BACKLIGHT_OFF_LEVEL);\n\n  SerialMon.print("[USER] Backlight ");\n  SerialMon.println(backlightOn ? "ON" : "OFF");\n}\n\nvoid toggleScreenBacklight() {\n  setScreenBacklight(!backlightOn);\n}\n\nvoid updateLedHeartbeat() {\n  uint32_t now = millis();\n\n  if (panicActive) {\n    if (now - lastLedPulseMs >= 250) {\n      lastLedPulseMs = now;\n      digitalWrite(RedLed_Pin, !digitalRead(RedLed_Pin));\n      digitalWrite(GreenLed_Pin, HIGH);\n      digitalWrite(BlueLed_Pin, HIGH);\n    }\n    return;\n  }\n\n  if (!bleConnected) {\n    if (now - lastLedPulseMs >= 500) {\n      lastLedPulseMs = now;\n      digitalWrite(BlueLed_Pin, !digitalRead(BlueLed_Pin));\n      digitalWrite(RedLed_Pin, HIGH);\n      digitalWrite(GreenLed_Pin, HIGH);\n    }\n    return;\n  }\n\n  if (bleConnected && !hrValid) {\n    if (now - lastLedPulseMs >= 300) {\n      lastLedPulseMs = now;\n      digitalWrite(GreenLed_Pin, !digitalRead(GreenLed_Pin));\n      digitalWrite(RedLed_Pin, HIGH);\n      digitalWrite(BlueLed_Pin, HIGH);\n    }\n    return;\n  }\n\n  if (hrValid && hrBpm > 0) {\n    if ((int32_t)(now - nextBeatMs) >= 0) {\n      lastBeatMs = now;\n      nextBeatMs = now + beatIntervalMs;\n      digitalWrite(RedLed_Pin, LOW);\n      digitalWrite(GreenLed_Pin, HIGH);\n      digitalWrite(BlueLed_Pin, HIGH);\n    }\n\n    if (now - lastBeatMs > 100) {\n      digitalWrite(RedLed_Pin, HIGH);\n    }\n  }\n}\n\n/* =========================================================\n   BLE\n   ========================================================= */\nbool matchBandByMac(const ble_gap_addr_t &addr) {\n  return memcmp(addr.addr, BAND_MAC_REVERSED, 6) == 0 ||\n         memcmp(addr.addr, BAND_MAC_NORMAL, 6) == 0;\n}\n\nvoid macToString(const ble_gap_addr_t &addr, char *out, size_t len) {\n  const uint8_t *a = addr.addr;\n  snprintf(out, len, "%02X:%02X:%02X:%02X:%02X:%02X",\n           a[5], a[4], a[3], a[2], a[1], a[0]);\n}\n\nvoid scan_cb(ble_gap_evt_adv_report_t *report) {\n  uint16_t major = 0;\n  uint16_t minor = 0;\n\n  if (parseIBeacon(report, major, minor)) {\n    updateTopBeacon(major, minor, report->rssi);\n  }\n\n  if (!bleConnected && matchBandByMac(report->peer_addr)) {\n    char macbuf[18];\n    macToString(report->peer_addr, macbuf, sizeof(macbuf));\n\n    SerialMon.print("[BLE] Banda encontrada: ");\n    SerialMon.println(macbuf);\n\n    Bluefruit.Central.connect(report);\n    return;\n  }\n\n  Bluefruit.Scanner.resume();\n}\n\nvoid connect_cb(uint16_t conn_handle) {\n  bleConnected = true;\n  requestScreenUpdate("Banda Conectada", "Sincronizando...", PERSON_NAME);\n\n  SerialMon.println("[BLE] Banda conectada");\n\n  if (svcHR.discover(conn_handle) && chrHR.discover()) {\n    chrHR.setNotifyCallback(hr_notify_cb);\n    chrHR.enableNotify();\n    SerialMon.println("[BLE] HR notify activo");\n  } else {\n    SerialMon.println("[BLE] HR no encontrado");\n  }\n\n  if (svcBAT.discover(conn_handle) && chrBAT.discover()) {\n    chrBAT.setNotifyCallback(bat_notify_cb);\n    chrBAT.enableNotify();\n\n    uint8_t v = 0;\n    if (chrBAT.read(&v, 1)) {\n      bandBatPct = v;\n      bandBatValid = true;\n    }\n  }\n\n  Bluefruit.Scanner.start(0);\n}\n\nvoid disconnect_cb(uint16_t, uint8_t) {\n  bleConnected = false;\n  hrValid = false;\n  bandBatValid = false;\n\n  requestScreenUpdate("Banda desconecta", "Reintentando...", PERSON_NAME);\n  SerialMon.println("[BLE] Banda desconectada");\n\n  Bluefruit.Scanner.start(0);\n}\n\nvoid hr_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len) {\n  (void)chr;\n\n  if (len < 2) return;\n\n  uint8_t flags = data[0];\n  uint8_t idx = 1;\n  uint16_t bpm = 0;\n\n  if (flags & 0x01) {\n    if (len < 3) return;\n    bpm = (uint16_t)data[idx] | ((uint16_t)data[idx + 1] << 8);\n    idx += 2;\n  } else {\n    bpm = data[idx++];\n  }\n\n  if (flags & 0x08) {\n    if (idx + 1 < len) idx += 2;\n  }\n\n  uint32_t rrIntervalMs = 0;\n\n  if (flags & 0x10) {\n    while (idx + 1 < len) {\n      uint16_t rr = (uint16_t)data[idx] | ((uint16_t)data[idx + 1] << 8);\n      idx += 2;\n\n      if (rr > 0) {\n        rrIntervalMs = ((uint32_t)rr * 1000UL) / 1024UL;\n      }\n    }\n  }\n\n  if (rrIntervalMs == 0 && bpm > 0) {\n    rrIntervalMs = 60000UL / bpm;\n  }\n\n  if (bpm >= 30 && bpm <= 240) {\n    hrBpm = (uint8_t)bpm;\n    hrValid = true;\n    beatIntervalMs = rrIntervalMs > 0 ? rrIntervalMs : beatIntervalMs;\n\n    SerialMon.print("[HR] BPM=");\n    SerialMon.println(hrBpm);\n\n    updateDisplayPosition();\n  }\n}\n\nvoid bat_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len) {\n  (void)chr;\n\n  if (len < 1) return;\n\n  bandBatPct = data[0];\n  bandBatValid = true;\n\n  SerialMon.print("[BAT] Banda=");\n  SerialMon.print(bandBatPct);\n  SerialMon.println("%");\n}\n\n/* =========================================================\n   BEACONS\n   ========================================================= */\nbool parseIBeacon(ble_gap_evt_adv_report_t *report, uint16_t &major, uint16_t &minor) {\n  const uint8_t *data = report->data.p_data;\n  uint8_t len = report->data.len;\n\n  for (uint8_t i = 0; i < len; ) {\n    uint8_t fieldLen = data[i];\n\n    if (fieldLen == 0) break;\n    if ((uint16_t)i + fieldLen >= len) break;\n\n    uint8_t type = data[i + 1];\n    const uint8_t *payload = &data[i + 2];\n    uint8_t payloadLen = fieldLen - 1;\n\n    if (type == BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC_DATA && payloadLen >= 25) {\n      bool appleIBeacon =\n        payload[0] == 0x4C &&\n        payload[1] == 0x00 &&\n        payload[2] == 0x02 &&\n        payload[3] == 0x15;\n\n      if (appleIBeacon && memcmp(&payload[4], MINERGUARD_UUID, 16) == 0) {\n        major = ((uint16_t)payload[20] << 8) | payload[21];\n        minor = ((uint16_t)payload[22] << 8) | payload[23];\n        return true;\n      }\n    }\n\n    i += fieldLen + 1;\n  }\n\n  return false;\n}\n\nvoid updateTopBeacon(uint16_t major, uint16_t minor, int8_t rssi) {\n  uint32_t now = millis();\n  bool updated = false;\n\n  for (int i = 0; i < 3; i++) {\n    if (topBeacons[i].valid &&\n        topBeacons[i].major == major &&\n        topBeacons[i].minor == minor) {\n\n      float smoothed = (topBeacons[i].rssi * 0.7f) + (rssi * 0.3f);\n      topBeacons[i].rssi = (int8_t)smoothed;\n      topBeacons[i].seenAt = now;\n      updated = true;\n      break;\n    }\n  }\n\n  if (!updated) {\n    for (int i = 0; i < 3; i++) {\n      if (!topBeacons[i].valid) {\n        topBeacons[i].valid = true;\n        topBeacons[i].major = major;\n        topBeacons[i].minor = minor;\n        topBeacons[i].rssi = rssi;\n        topBeacons[i].seenAt = now;\n        updated = true;\n        break;\n      }\n    }\n  }\n\n  if (!updated) {\n    int worst = 0;\n\n    for (int i = 1; i < 3; i++) {\n      if (topBeacons[i].rssi < topBeacons[worst].rssi) {\n        worst = i;\n      }\n    }\n\n    if (rssi > topBeacons[worst].rssi + 3) {\n      topBeacons[worst].valid = true;\n      topBeacons[worst].major = major;\n      topBeacons[worst].minor = minor;\n      topBeacons[worst].rssi = rssi;\n      topBeacons[worst].seenAt = now;\n    }\n  }\n\n  sortTopBeacons();\n  updateDisplayPosition();\n}\n\nvoid cleanupOldBeacons() {\n  uint32_t now = millis();\n\n  for (int i = 0; i < 3; i++) {\n    if (topBeacons[i].valid && (now - topBeacons[i].seenAt > BEACON_TIMEOUT_MS)) {\n      topBeacons[i].valid = false;\n      topBeacons[i].rssi = -127;\n    }\n  }\n}\n\nvoid sortTopBeacons() {\n  for (int i = 0; i < 2; i++) {\n    for (int j = i + 1; j < 3; j++) {\n      if (!topBeacons[i].valid && topBeacons[j].valid) {\n        BeaconReading tmp = topBeacons[i];\n        topBeacons[i] = topBeacons[j];\n        topBeacons[j] = tmp;\n      } else if (topBeacons[i].valid &&\n                 topBeacons[j].valid &&\n                 topBeacons[j].rssi > topBeacons[i].rssi) {\n        BeaconReading tmp = topBeacons[i];\n        topBeacons[i] = topBeacons[j];\n        topBeacons[j] = tmp;\n      }\n    }\n  }\n}\n\n\n/* =========================================================\n   LORAWAN LMIC\n   ========================================================= */\nvoid setupLoRaWAN() {\n  SerialMon.println("[LMIC] Inicializando MCCI LMIC SX1262...");\n\n  pinMode(LoRa_Cs, OUTPUT);\n  digitalWrite(LoRa_Cs, HIGH);\n  pinMode(LoRa_Rst, OUTPUT);\n  pinMode(LoRa_Busy, INPUT);\n  pinMode(LoRa_Dio1, INPUT);\n\n  SPI.setPins(LoRa_Miso, LoRa_Sclk, LoRa_Mosi);\n  SPI.begin();\n\n  os_init_ex(&lmic_pins);\n  LMIC_reset();\n\n#if defined(CFG_us915)\n  LMIC_selectSubBand(1);  // US915 SubBand 2: canales 8-15 + 65\n  SerialMon.println("[LMIC] US915 SubBand 2 seleccionada");\n#endif\n\n  LMIC_setClockError(MAX_CLOCK_ERROR * 5 / 100);\n  lmicJoined = false;\n  lmicTxPending = false;\n\n  SerialMon.println("[LMIC] Iniciando JOIN OTAA...");\n  LMIC_startJoining();\n}\n\nbool sendLoRaWANPayloadNow(const uint8_t *data, uint8_t len) {\n  if (!lmicJoined) {\n    SerialMon.println("[LMIC] TX cancelado: aun no hay EV_JOINED.");\n    return false;\n  }\n\n  if (LMIC.opmode & OP_TXRXPEND) {\n    SerialMon.println("[LMIC] TX pendiente, se omite este ciclo.");\n    return false;\n  }\n\n  LMIC_setTxData2(LORAWAN_APP_PORT, (xref2u1_t)data, len, 0);\n  lmicTxPending = true;\n\n  SerialMon.print("[LMIC] Uplink encolado FPort ");\n  SerialMon.print(LORAWAN_APP_PORT);\n  SerialMon.print(" bytes=");\n  SerialMon.println(len);\n  return true;\n}\n\nvoid onEvent(ev_t ev) {\n  SerialMon.print(os_getTime());\n  SerialMon.print(": ");\n\n  switch (ev) {\n    case EV_JOINING:\n      SerialMon.println("EV_JOINING");\n      requestScreenUpdate("LoRaWAN", "JOINING...", PERSON_NAME);\n      break;\n\n    case EV_JOINED:\n      SerialMon.println("EV_JOINED");\n      lmicJoined = true;\n      lmicTxPending = false;\n      LMIC_setLinkCheckMode(0);\n      requestScreenUpdate("LoRaWAN", "JOINED", PERSON_NAME);\n      break;\n\n    case EV_JOIN_FAILED:\n      SerialMon.println("EV_JOIN_FAILED");\n      lmicJoined = false;\n      lmicTxPending = false;\n      requestScreenUpdate("LoRaWAN", "JOIN FAILED", PERSON_NAME);\n      break;\n\n    case EV_REJOIN_FAILED:\n      SerialMon.println("EV_REJOIN_FAILED");\n      lmicJoined = false;\n      lmicTxPending = false;\n      break;\n\n    case EV_TXSTART:\n      SerialMon.println("EV_TXSTART");\n      break;\n\n    case EV_TXCOMPLETE:\n      SerialMon.println("EV_TXCOMPLETE");\n      lmicTxPending = false;\n\n      if (LMIC.txrxFlags & TXRX_ACK) {\n        SerialMon.println("[LMIC] ACK recibido");\n      }\n\n      if (LMIC.dataLen) {\n        SerialMon.print("[LMIC] Downlink bytes: ");\n        SerialMon.println(LMIC.dataLen);\n      }\n      break;\n\n    case EV_RESET:\n      SerialMon.println("EV_RESET");\n      break;\n\n    case EV_RXSTART:\n      SerialMon.println("EV_RXSTART");\n      break;\n\n    case EV_LINK_DEAD:\n      SerialMon.println("EV_LINK_DEAD");\n      break;\n\n    case EV_LINK_ALIVE:\n      SerialMon.println("EV_LINK_ALIVE");\n      break;\n\n    default:\n      SerialMon.print("EV_");\n      SerialMon.println((unsigned)ev);\n      break;\n  }\n}\n\n/* =========================================================\n   PAYLOAD 36 BYTES, MISMA ESTRUCTURA HELTEC\n   ========================================================= */\nuint8_t encodeRSSI(int8_t rssi) {\n  return (uint8_t)(rssi + 127);\n}\n\nvoid buildExtendedPayload(uint8_t *out, uint8_t &sz, bool panic) {\n  Bluefruit.Scanner.stop();\n\n  cleanupOldBeacons();\n  sortTopBeacons();\n\n  memcpy(snapshotB, topBeacons, sizeof(topBeacons));\n\n  uint8_t flags = 0;\n\n  if (panic) flags |= 0x01;\n  if (hrValid) flags |= 0x02;\n  if (bandBatValid) flags |= 0x04;\n  if (bleConnected) flags |= 0x08;\n\n  out[0] = flags;\n  out[1] = hrValid ? hrBpm : 0;\n  out[2] = bandBatValid ? bandBatPct : 0;\n  out[3] = (uint8_t)(NODE_ID & 0xFF);\n  out[4] = (uint8_t)((NODE_ID >> 8) & 0xFF);\n  out[5] = bleConnected ? 1 : 0;\n\n  for (int i = 0; i < 3; i++) {\n    int base = 6 + (i * 5);\n\n    if (snapshotA[i].valid) {\n      out[base + 0] = (uint8_t)((snapshotA[i].major >> 8) & 0xFF);\n      out[base + 1] = (uint8_t)(snapshotA[i].major & 0xFF);\n      out[base + 2] = (uint8_t)((snapshotA[i].minor >> 8) & 0xFF);\n      out[base + 3] = (uint8_t)(snapshotA[i].minor & 0xFF);\n      out[base + 4] = encodeRSSI(snapshotA[i].rssi);\n    } else {\n      memset(&out[base], 0, 5);\n    }\n  }\n\n  for (int i = 0; i < 3; i++) {\n    int base = 21 + (i * 5);\n\n    if (snapshotB[i].valid) {\n      out[base + 0] = (uint8_t)((snapshotB[i].major >> 8) & 0xFF);\n      out[base + 1] = (uint8_t)(snapshotB[i].major & 0xFF);\n      out[base + 2] = (uint8_t)((snapshotB[i].minor >> 8) & 0xFF);\n      out[base + 3] = (uint8_t)(snapshotB[i].minor & 0xFF);\n      out[base + 4] = encodeRSSI(snapshotB[i].rssi);\n    } else {\n      memset(&out[base], 0, 5);\n    }\n  }\n\n  sz = 36;\n  lastPeriodicSend = millis();\n  snapshotATaken = false;\n\n  Bluefruit.Scanner.start(0);\n}\n\nvoid printPayloadHex(const uint8_t *data, uint8_t len) {\n  for (uint8_t i = 0; i < len; i++) {\n    if (data[i] < 16) SerialMon.print("0");\n    SerialMon.print(data[i], HEX);\n    if (i < len - 1) SerialMon.print(" ");\n  }\n}\n'

UTILITIES_TEMPLATE = '#pragma once\n\n\n#include <Arduino.h>\n\n// #define VERSION_1\n// #define HIGH_VOLTAGE\n\n#ifndef _PINNUM\n#define _PINNUM(port, pin)    ((port)*32 + (pin))\n#endif\n\n#if defined(VERSION_1)\n#define ePaper_Miso         _PINNUM(1,3)\n#else\n#define ePaper_Miso         _PINNUM(1,6)\n#endif\n#define ePaper_Mosi         _PINNUM(0,29)\n#define ePaper_Sclk         _PINNUM(0,31)\n#define ePaper_Cs           _PINNUM(0,30)\n#define ePaper_Dc           _PINNUM(0,28)\n#define ePaper_Rst          _PINNUM(0,2)\n#define ePaper_Busy         _PINNUM(0,3)\n#define ePaper_Backlight    _PINNUM(1,11)\n\n#define LoRa_Miso           _PINNUM(0,23)\n#define LoRa_Mosi           _PINNUM(0,22)\n#define LoRa_Sclk           _PINNUM(0,19)\n#define LoRa_Cs             _PINNUM(0,24)\n#define LoRa_Rst            _PINNUM(0,25)\n#if defined(VERSION_1)\n#define LoRa_Dio0           _PINNUM(1,1)\n#else\n#define LoRa_Dio0           _PINNUM(0,22)\n#endif\n#define LoRa_Dio1           _PINNUM(0,20)\n#define LoRa_Dio2           //_PINNUM(0,3)\n#define LoRa_Dio3           _PINNUM(0,21)\n#define LoRa_Dio4           //_PINNUM(0,3)\n#define LoRa_Dio5           //_PINNUM(0,3)\n#define LoRa_Busy           _PINNUM(0,17)\n\n\n#define Flash_Cs            _PINNUM(1,15)\n#define Flash_Miso          _PINNUM(1,13)\n#define Flash_Mosi          _PINNUM(1,12)\n#define Flash_Sclk          _PINNUM(1,14)\n\n#define Touch_Pin           _PINNUM(0,11)\n#define Adc_Pin             _PINNUM(0,4)\n\n#define SDA_Pin             _PINNUM(0,26)\n#define SCL_Pin             _PINNUM(0,27)\n\n#define RTC_Int_Pin         _PINNUM(0,16)\n\n#define Gps_Rx_Pin          _PINNUM(1,9)\n#define Gps_Tx_Pin          _PINNUM(1,8)\n\n#if defined(VERSION_1)\n#define Gps_Wakeup_Pin      _PINNUM(1,2)\n#define Gps_pps_Pin         _PINNUM(1,4)\n#else\n#define Gps_Wakeup_Pin      _PINNUM(1,2)\n#define Gps_Reset_Pin       _PINNUM(1,5)\n#define Gps_pps_Pin         _PINNUM(1,4)\n#endif\n\n\n\n#define UserButton_Pin      _PINNUM(1,10)\n\n#if defined(VERSION_1)\n#define Power_Enable_Pin    _PINNUM(0,12)\n#else\n#define Power_Enable_Pin    _PINNUM(0,12)\n//#define Power_Enable1_Pin   _PINNUM(0,13)\n#endif\n\n\n#if defined(VERSION_1)\n#define GreenLed_Pin        _PINNUM(0,13)\n#define RedLed_Pin          _PINNUM(0,14)\n#define BlueLed_Pin         _PINNUM(0,15)\n#else\n#define GreenLed_Pin        _PINNUM(1,1)\n#define RedLed_Pin          _PINNUM(1,3)\n#define BlueLed_Pin         _PINNUM(0,14)\n#endif\n\n#define SerialMon           Serial\n#define SerialGPS           Serial2\n\n#define MONITOR_SPEED       115200\n\n\n\n\n\n'

LMIC_PROJECT_CONFIG = r"""// lmic_project_config.h para LilyGO T-Echo SX1262 + Milesight UG65 US915
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
"""


def sanitize_hex(value: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()


def validate_hex(value: str, bytes_len: int, field_name: str) -> str:
    cleaned = sanitize_hex(value)
    if len(cleaned) != bytes_len * 2:
        raise ValueError(f"{field_name} debe tener {bytes_len * 2} caracteres hexadecimales.")
    if not HEX_RE.fullmatch(cleaned):
        raise ValueError(f"{field_name} contiene caracteres no válidos.")
    return cleaned


def random_hex(bytes_len: int) -> str:
    return secrets.token_hex(bytes_len).upper()


def random_unique_hex(bytes_len: int, existing_values: set[str]) -> str:
    used = {sanitize_hex(v) for v in existing_values if v}
    for _ in range(10000):
        value = random_hex(bytes_len)
        if value not in used:
            return value
    raise RuntimeError("No se pudo generar una credencial única.")


def hex_to_c_array(hex_value: str, reverse: bool = False) -> str:
    value = sanitize_hex(hex_value)
    parts = [value[i:i+2] for i in range(0, len(value), 2)]
    if reverse:
        parts.reverse()
    return ", ".join(f"0x{p}" for p in parts)


def escape_c_string(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def safe_filename_part(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ_-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "SIN_NOMBRE"


def mac_to_c_arrays(mac: str) -> tuple[str, str]:
    parts = [int(x, 16) for x in mac.upper().split(":")]
    normal = ", ".join(f"0x{x:02X}" for x in parts)
    rev = ", ".join(f"0x{x:02X}" for x in reversed(parts))
    return normal, rev


def replace_regex(code: str, pattern: str, repl: str, label: str) -> str:
    new_code, n = re.subn(pattern, repl, code, count=1, flags=re.S)
    if n != 1:
        raise RuntimeError(f"No se pudo reemplazar: {label}")
    return new_code


def apply_template(
    *,
    sketch_filename: str,
    node_id: str,
    person_name: str,
    ble_name: str,
    band_mac: str,
    dev_eui: str,
    app_eui: str,
    app_key: str,
    app_port: str,
    period_ms: str,
    rssi_filter: str,
    display_rotation: str,
) -> str:
    code = BASE_INO_TEMPLATE
    normal_mac, reversed_mac = mac_to_c_arrays(band_mac)

    code = replace_regex(code, r"static const uint16_t NODE_ID = \d+;", f"static const uint16_t NODE_ID = {node_id};", "NODE_ID")
    code = replace_regex(code, r'static const char PERSON_NAME\[\] = ".*?";', f'static const char PERSON_NAME[] = "{escape_c_string(person_name)}";', "PERSON_NAME")
    code = replace_regex(code, r'static const char NODE_LABEL\[\]\s*=\s*".*?";', f'static const char NODE_LABEL[]  = "{escape_c_string(ble_name)}";', "NODE_LABEL")

    code = replace_regex(code, r'static const char BAND_MAC_TARGET\[\] = ".*?";', f'static const char BAND_MAC_TARGET[] = "{band_mac.upper()}";', "BAND_MAC_TARGET")
    code = replace_regex(code, r"static const uint8_t BAND_MAC_NORMAL\[6\]\s*=\s*\{.*?\};", "static const uint8_t BAND_MAC_NORMAL[6]   = { " + normal_mac + " };", "BAND_MAC_NORMAL")
    code = replace_regex(code, r"static const uint8_t BAND_MAC_REVERSED\[6\]\s*=\s*\{.*?\};", "static const uint8_t BAND_MAC_REVERSED[6] = { " + reversed_mac + " };", "BAND_MAC_REVERSED")

    code = replace_regex(code, r"static const uint8_t LORAWAN_APP_PORT = \d+;", f"static const uint8_t LORAWAN_APP_PORT = {app_port};", "LORAWAN_APP_PORT")
    code = replace_regex(code, r"static const u1_t PROGMEM APPEUI\[8\]\s*=\s*\{.*?\};", "static const u1_t PROGMEM APPEUI[8] = { " + hex_to_c_array(app_eui, reverse=True) + " };", "APPEUI")
    code = replace_regex(code, r"static const u1_t PROGMEM DEVEUI\[8\]\s*=\s*\{.*?\};", "static const u1_t PROGMEM DEVEUI[8] = { " + hex_to_c_array(dev_eui, reverse=True) + " };", "DEVEUI")
    code = replace_regex(code, r"static const u1_t PROGMEM APPKEY\[16\]\s*=\s*\{.*?\};", "static const u1_t PROGMEM APPKEY[16] = { " + hex_to_c_array(app_key, reverse=False) + " };", "APPKEY")

    code = replace_regex(code, r'char scrLine3\[32\] = ".*?";', f'char scrLine3[32] = "{escape_c_string(person_name)}";', "scrLine3")
    code = replace_regex(code, r"static const uint32_t TX_INTERVAL_MS = \d+;", f"static const uint32_t TX_INTERVAL_MS = {period_ms};", "TX_INTERVAL_MS")
    code = replace_regex(code, r"Bluefruit\.Scanner\.filterRssi\(-?\d+\);", f"Bluefruit.Scanner.filterRssi({rssi_filter});", "filterRssi")
    code = replace_regex(code, r"display->setRotation\(\d+\);", f"display->setRotation({display_rotation});", "display rotation")
    code = replace_regex(code, r'SerialMon\.println\("\[DISPLAY\] Rotacion forzada: \d+"\);', f'SerialMon.println("[DISPLAY] Rotacion forzada: {display_rotation}");', "display rotation log")

    # Boot identificable para no confundir con versiones viejas.
    code = code.replace('[BOOT] SKETCH GENERADO POR: V5_LMIC_FULL', '[BOOT] SKETCH GENERADO POR: V5_LMIC_FULL_FIX_ARRAYS')
    code = replace_regex(code, r'SerialMon\.println\("[0-9A-Fa-f]{16}"\);', f'SerialMon.println("{dev_eui}");', "DevEUI boot print")

    # Ajustar comentario de archivo si aparece.
    code = code.replace("Minerguard_TEcho_4_LMIC_FULL.ino", sketch_filename)

    return code


class MinerguardGenerator:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Minerguard T-Echo - Generador V5 LMIC FULL FIX ARRAYS")
        self.root.geometry("940x780")
        self.root.minsize(820, 660)

        self.output_dir = tk.StringVar(value=str(Path.cwd()))
        self.output_filename = tk.StringVar(value="")
        self.final_output_path = tk.StringVar(value="")

        self.node_id = tk.StringVar(value="4")
        self.person_name = tk.StringVar(value="Rodrigo Zuniga")
        self.ble_name = tk.StringVar(value="4")
        self._last_auto_ble_name = "4"
        self.band_mac = tk.StringVar(value="E3:FD:1A:F2:F3:AF")

        self.period_ms = tk.StringVar(value="15000")
        self.rssi_filter = tk.StringVar(value="-95")
        self.display_rotation = tk.StringVar(value="3")

        self.ug65_application = tk.StringVar(value="Sense_T1000")
        self.ug65_deviceprofile = tk.StringVar(value="ClassA-OTAA")
        self.ug65_fport = tk.StringVar(value="1")
        self.ug65_timeout = tk.StringVar(value="1440")

        self.dev_eui = tk.StringVar(value=random_hex(8))
        self.app_eui = tk.StringVar(value="0000000000000000")
        self.app_key = tk.StringVar(value=random_hex(16))
        self.auto_otaa = tk.BooleanVar(value=True)
        self.force_unique_otaa = tk.BooleanVar(value=True)

        self._build_ui()
        self.node_id.trace_add("write", self.on_node_changed)
        self.output_dir.trace_add("write", lambda *_: self.update_output_preview())
        self.output_filename.trace_add("write", lambda *_: self.update_output_preview())
        self.update_output_preview()

    def _build_ui(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frm = ttk.Frame(canvas, padding=12)
        win = canvas.create_window((0, 0), window=frm, anchor="nw")
        frm.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        self.root.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        ttk.Label(frm, text="Generador MinerGuard V5 LMIC FULL FIX ARRAYS - LilyGO T-Echo", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            frm,
            text="Formato fijo: FPort 1, payload 36 bytes, HR flags 0x01/0x02/0x04/0x08, CSV UG65 con name numérico.",
            foreground="#444"
        ).pack(anchor="w", pady=(0, 10))

        box1 = ttk.LabelFrame(frm, text="Datos del nodo / pantalla / BLE", padding=10)
        box1.pack(fill="x", pady=6)
        self._entry(box1, "Node ID", self.node_id, 0, width=16)
        self._entry(box1, "Nombre persona en pantalla", self.person_name, 1, width=42)
        self._entry(box1, "Nombre BLE / NODE_LABEL (por defecto = Node ID)", self.ble_name, 2, width=24)
        self._entry(box1, "MAC banda cardiaca", self.band_mac, 3, width=24)
        self._entry(box1, "Periodo payload/envío ms", self.period_ms, 4, width=16)
        self._entry(box1, "Filtro RSSI beacons", self.rssi_filter, 5, width=16)
        self._entry(box1, "Rotación e-paper", self.display_rotation, 6, width=16)

        box2 = ttk.LabelFrame(frm, text="Credenciales OTAA", padding=10)
        box2.pack(fill="x", pady=6)
        self._entry(box2, "DevEUI", self.dev_eui, 0, width=42)
        self._entry(box2, "AppEUI / JoinEUI", self.app_eui, 1, width=42)
        self._entry(box2, "AppKey", self.app_key, 2, width=42)
        ttk.Checkbutton(box2, text="Generar DevEUI y AppKey automáticamente", variable=self.auto_otaa).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 2))
        ttk.Checkbutton(box2, text="Forzar únicos contra nodes.csv", variable=self.force_unique_otaa).grid(row=4, column=0, columnspan=2, sticky="w")
        btns = ttk.Frame(box2)
        btns.grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="Generar DevEUI", command=self.regen_deveui).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Generar AppKey", command=self.regen_appkey).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="AppEUI = 000...", command=lambda: self.app_eui.set("0000000000000000")).pack(side="left")

        box3 = ttk.LabelFrame(frm, text="UG65 Bulk Import", padding=10)
        box3.pack(fill="x", pady=6)
        self._entry(box3, "Application", self.ug65_application, 0, width=34)
        self._entry(box3, "Device Profile", self.ug65_deviceprofile, 1, width=34)
        self._entry(box3, "FPort", self.ug65_fport, 2, width=12)
        self._entry(box3, "Timeout", self.ug65_timeout, 3, width=12)

        box4 = ttk.LabelFrame(frm, text="Salida", padding=10)
        box4.pack(fill="x", pady=6)
        self._entry(box4, "Carpeta base", self.output_dir, 0, width=70)
        ttk.Button(box4, text="Elegir carpeta", command=self.choose_folder).grid(row=0, column=2, padx=6, pady=4)
        self._entry(box4, "Archivo .ino", self.output_filename, 1, width=48)
        ttk.Button(box4, text="Auto nombre", command=self.reset_filename).grid(row=1, column=2, padx=6, pady=4)
        ttk.Label(box4, text="Ruta final").grid(row=2, column=0, sticky="nw", padx=(0, 8), pady=4)
        ttk.Label(box4, textvariable=self.final_output_path, wraplength=640).grid(row=2, column=1, columnspan=2, sticky="w", pady=4)

        actions = ttk.Frame(frm)
        actions.pack(fill="x", pady=(10, 6))
        ttk.Button(actions, text="Generar sketch + CSV", command=self.generate, width=24).pack(side="left")
        ttk.Button(actions, text="Copiar config LMIC", command=self.copy_lmic_config, width=22).pack(side="left", padx=8)
        ttk.Button(actions, text="Abrir carpeta", command=self.open_output, width=18).pack(side="left")
        ttk.Button(actions, text="Salir", command=self.root.destroy, width=12).pack(side="right")

        log_box = ttk.LabelFrame(frm, text="Resumen / log", padding=10)
        log_box.pack(fill="both", expand=True, pady=6)
        self.text = tk.Text(log_box, height=16, wrap="word", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)

        self.write_log("Listo. Este generador usa la base V5 que ya hizo EV_JOINED, EV_TXSTART y EV_TXCOMPLETE.")
        self.write_log("Recordatorio Node-RED: payload 36 bytes, flags 0x01 panic, 0x02 HR, 0x04 batería banda, 0x08 BLE conectado.")

    def _entry(self, parent, label, var, row, width=34):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=1, sticky="w", pady=4)

    def write_log(self, msg: str):
        self.text.insert("end", msg + "\n")
        self.text.see("end")

    def auto_name(self, node_id: str) -> str:
        return str(node_id or "SIN_ID").strip()

    def on_node_changed(self, *_):
        node_id = self.node_id.get().strip() or "SIN_ID"
        auto = self.auto_name(node_id)
        current = self.ble_name.get().strip()
        if current == "" or current == self._last_auto_ble_name or current.startswith("T-Echo-"):
            self.ble_name.set(auto)
            self._last_auto_ble_name = auto
        self.update_output_preview()

    def update_output_preview(self):
        node_id = self.node_id.get().strip() or "SIN_ID"
        filename = self.output_filename.get().strip() or f"Minerguard_TEcho_{safe_filename_part(node_id)}_LMIC_FULL.ino"
        if not filename.lower().endswith(".ino"):
            filename += ".ino"
        base = Path(self.output_dir.get().strip() or Path.cwd())
        self.final_output_path.set(str(base / Path(filename).stem / filename))

    def reset_filename(self):
        self.output_filename.set("")
        self.update_output_preview()

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.cwd()))
        if folder:
            self.output_dir.set(folder)
            self.update_output_preview()

    def get_nodes_csv_path(self) -> Path:
        return Path(self.output_dir.get().strip() or Path.cwd()) / "nodes.csv"

    def read_existing_credentials(self) -> tuple[set[str], set[str]]:
        devs, keys = set(), set()
        path = self.get_nodes_csv_path()
        if not path.exists():
            return devs, keys
        try:
            with path.open("r", newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    d = sanitize_hex(row.get("devEUI", ""))
                    k = sanitize_hex(row.get("appKey", ""))
                    if len(d) == 16:
                        devs.add(d)
                    if len(k) == 32:
                        keys.add(k)
        except Exception as e:
            self.write_log(f"Advertencia al leer nodes.csv: {e}")
        return devs, keys

    def regen_deveui(self):
        devs, _ = self.read_existing_credentials()
        self.dev_eui.set(random_unique_hex(8, devs))
        self.write_log(f"Nuevo DevEUI: {self.dev_eui.get()}")

    def regen_appkey(self):
        _, keys = self.read_existing_credentials()
        self.app_key.set(random_unique_hex(16, keys))
        self.write_log("Nueva AppKey generada.")

    def validate(self):
        node_id = self.node_id.get().strip()
        if not node_id.isdigit():
            raise ValueError("Node ID debe ser numérico.")

        if not MAC_RE.fullmatch(self.band_mac.get().strip()):
            raise ValueError("MAC banda debe tener formato AA:BB:CC:DD:EE:FF.")

        for field, name in [
            (self.period_ms.get(), "Periodo"),
            (self.ug65_fport.get(), "FPort"),
            (self.ug65_timeout.get(), "Timeout"),
        ]:
            if not field.strip().isdigit():
                raise ValueError(f"{name} debe ser numérico.")

        if int(self.ug65_fport.get()) < 1 or int(self.ug65_fport.get()) > 223:
            raise ValueError("FPort debe estar entre 1 y 223.")

        display_rotation = self.display_rotation.get().strip()
        if display_rotation not in ["0", "1", "2", "3"]:
            raise ValueError("Rotación e-paper debe ser 0, 1, 2 o 3.")

        rssi_filter = self.rssi_filter.get().strip()
        if not re.fullmatch(r"-?\d+", rssi_filter):
            raise ValueError("Filtro RSSI debe ser entero, por ejemplo -95.")

        if self.auto_otaa.get():
            if self.force_unique_otaa.get():
                devs, keys = self.read_existing_credentials()
                self.dev_eui.set(random_unique_hex(8, devs))
                self.app_key.set(random_unique_hex(16, keys))
            else:
                if len(sanitize_hex(self.dev_eui.get())) != 16:
                    self.dev_eui.set(random_hex(8))
                if len(sanitize_hex(self.app_key.get())) != 32:
                    self.app_key.set(random_hex(16))
            if not self.app_eui.get().strip():
                self.app_eui.set("0000000000000000")

        dev_eui = validate_hex(self.dev_eui.get(), 8, "DevEUI")
        app_eui = validate_hex(self.app_eui.get(), 8, "AppEUI/JoinEUI")
        app_key = validate_hex(self.app_key.get(), 16, "AppKey")
        return node_id, dev_eui, app_eui, app_key

    def write_nodes_csv(self, row: dict):
        path = self.get_nodes_csv_path()
        headers = [
            "created_at", "node_id", "person_name", "ble_name", "ug65_name",
            "band_mac", "devEUI", "appEUI", "appKey", "app_port",
            "period_ms", "rssi_filter", "display_rotation", "sketch_path"
        ]
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            if not exists:
                writer.writeheader()
            writer.writerow({h: row.get(h, "") for h in headers})

    def write_ug65_csv(self, row: dict):
        path = Path(self.output_dir.get().strip() or Path.cwd()) / "ug65_bulk_import_devices.csv"

        if path.exists():
            try:
                with path.open("r", newline="", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    old_headers = next(reader, [])
                if old_headers != UG65_HEADERS:
                    backup = path.with_suffix(".bak.csv")
                    shutil.move(str(path), str(backup))
                    self.write_log(f"CSV UG65 anterior tenía encabezado distinto. Respaldo: {backup.name}")
            except Exception:
                pass

        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=UG65_HEADERS)
            if not exists:
                writer.writeheader()
            writer.writerow({h: row.get(h, "") for h in UG65_HEADERS})

        return path

    def generate(self):
        try:
            node_id, dev_eui, app_eui, app_key = self.validate()

            base = Path(self.output_dir.get().strip() or Path.cwd())
            filename = self.output_filename.get().strip() or f"Minerguard_TEcho_{safe_filename_part(node_id)}_LMIC_FULL.ino"
            if not filename.lower().endswith(".ino"):
                filename += ".ino"

            outdir = base / Path(filename).stem
            outdir.mkdir(parents=True, exist_ok=True)

            # Evitar que Arduino compile pestañas viejas.
            for old in outdir.glob("*.ino"):
                try:
                    old.unlink()
                except Exception:
                    pass

            ino_path = outdir / filename
            utilities_path = outdir / "utilities.h"

            person = self.person_name.get().strip() or f"Minero {node_id}"
            ble_name = self.ble_name.get().strip() or node_id

            code = apply_template(
                sketch_filename=filename,
                node_id=node_id,
                person_name=person,
                ble_name=ble_name,
                band_mac=self.band_mac.get().strip().upper(),
                dev_eui=dev_eui,
                app_eui=app_eui,
                app_key=app_key,
                app_port=self.ug65_fport.get().strip(),
                period_ms=self.period_ms.get().strip(),
                rssi_filter=self.rssi_filter.get().strip(),
                display_rotation=self.display_rotation.get().strip(),
            )

            ino_path.write_text(code, encoding="utf-8")
            utilities_path.write_text(UTILITIES_TEMPLATE, encoding="utf-8")

            # También se deja config LMIC dentro de la carpeta base.
            config_path = base / "lmic_project_config_T_ECHO_US915_SX1262.h"
            config_path.write_text(LMIC_PROJECT_CONFIG, encoding="utf-8")

            self.write_nodes_csv({
                "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "node_id": node_id,
                "person_name": person,
                "ble_name": ble_name,
                "ug65_name": node_id,
                "band_mac": self.band_mac.get().strip().upper(),
                "devEUI": dev_eui,
                "appEUI": app_eui,
                "appKey": app_key,
                "app_port": self.ug65_fport.get().strip(),
                "period_ms": self.period_ms.get().strip(),
                "rssi_filter": self.rssi_filter.get().strip(),
                "display_rotation": self.display_rotation.get().strip(),
                "sketch_path": str(ino_path),
            })

            ug65_csv = self.write_ug65_csv({
                "name": node_id,
                "description": person,
                "deveui": dev_eui.lower(),
                "deviceprofile": self.ug65_deviceprofile.get().strip(),
                "application": self.ug65_application.get().strip(),
                "payloadcodec": "",
                "fport": self.ug65_fport.get().strip(),
                "appkey": app_key.lower(),
                "devaddr": "",
                "nwkskey": "",
                "appskey": "",
                "timeout": self.ug65_timeout.get().strip(),
            })

            self.write_log("=" * 70)
            self.write_log("GENERADO CORRECTAMENTE")
            self.write_log(f"Sketch: {ino_path}")
            self.write_log(f"utilities.h: {utilities_path}")
            self.write_log(f"nodes.csv: {self.get_nodes_csv_path()}")
            self.write_log(f"UG65 CSV: {ug65_csv}")
            self.write_log(f"Config LMIC: {config_path}")
            self.write_log("")
            self.write_log("Serial esperado:")
            self.write_log("[BOOT] SKETCH GENERADO POR: V5_LMIC_FULL_FIX_ARRAYS")
            self.write_log("EV_JOINING -> EV_JOINED -> [PAYLOAD 36B] -> EV_TXSTART -> EV_TXCOMPLETE")
            self.write_log("")
            self.write_log(f"UG65 name numérico: {node_id}")
            self.write_log(f"DevEUI: {dev_eui}")
            self.write_log("=" * 70)

            messagebox.showinfo("Generado", "Sketch + CSV UG65 generados correctamente.")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.write_log(f"ERROR: {e}")

    def copy_lmic_config(self):
        target = Path.home() / "Documents" / "Arduino" / "libraries" / "MCCI_LoRaWAN_LMIC_library" / "project_config" / "lmic_project_config.h"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(LMIC_PROJECT_CONFIG, encoding="utf-8")
            self.write_log(f"Config LMIC copiada a: {target}")
            messagebox.showinfo("LMIC", f"Configuración LMIC copiada a:\n{target}")
        except Exception as e:
            self.write_log(f"ERROR copiando config LMIC: {e}")
            messagebox.showerror("LMIC", str(e))

    def open_output(self):
        path = Path(self.output_dir.get().strip() or Path.cwd())
        try:
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.write_log(f"No se pudo abrir carpeta: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MinerguardGenerator(root)
    root.mainloop()
