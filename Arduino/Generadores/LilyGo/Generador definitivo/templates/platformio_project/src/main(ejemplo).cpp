/********************************************************************
 * Minerguard para LILYGO T-Echo nRF52840
 * Adaptacion desde Minerguard_2.ino / Heltec T114
 *
 * Mantiene:
 *   - Banda cardiaca BLE estricta por MAC: E5:FD:8A:F2:F3:AF
 *   - Heart Rate Service 0x180D / Measurement 0x2A37
 *   - Battery Service 0x180F / Battery Level 0x2A19
 *   - Beacons MinerGuard tipo iBeacon:
 *       Major = nivel / sector
 *       Minor = PK
 *   - Top 3 beacons por RSSI con suavizado
 *   - Boton de panico por USER button
 *   - Doble click USER para encender/apagar iluminacion de pantalla
 *   - Payload extendido de 46 bytes: base Heltec 36B + GPS 10B
 *
 * Diferencia importante:
 *   La Heltec usa TFT ST7789 240x135 y permite animacion fluida.
 *   La T-Echo usa e-paper 200x200, por lo que la pantalla se actualiza
 *   lento. El LED rojo late en tiempo real; la pantalla muestra un frame
 *   grande/pequeno del corazon cada refresco.
 *
 * Archivos requeridos en la misma carpeta:
 *   - Minerguard_TEcho_Final.ino
 *   - utilities.h  (el definitivo de LILYGO T-Echo que subiste)
 ********************************************************************/

#include "utilities.h"

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <bluefruit.h>
#include <lmic.h>
#include <hal/hal.h>
#include <TinyGPSPlus.h>

#include <GxEPD.h>
#include <GxDEPG0150BN/GxDEPG0150BN.h>
#include <Fonts/FreeMonoBold9pt7b.h>
#include <Fonts/FreeMonoBold12pt7b.h>
#include <Fonts/FreeMonoBold18pt7b.h>
#include <GxIO/GxIO_SPI/GxIO_SPI.h>
#include <GxIO/GxIO.h>

/* =========================================================
   CONFIGURACION DEL TAG
   ========================================================= */
#define BUTTON_PIN UserButton_Pin

static const uint16_t NODE_ID = 6;
static const char PERSON_NAME[] = "Hector Quiroz";
static const char NODE_LABEL[]  = "6";

// No cambiar la banda cardiaca.
static const char BAND_MAC_TARGET[] = "E5:FD:8A:F2:F3:AF";
static const uint8_t BAND_MAC_NORMAL[6]   = { 0xE5, 0xFD, 0x8A, 0xF2, 0xF3, 0xAF };
static const uint8_t BAND_MAC_REVERSED[6] = { 0xAF, 0xF3, 0xF2, 0x8A, 0xFD, 0xE5 };



/* =========================================================
   ESTADO GLOBAL GPS L76K
   =========================================================
   Estas variables deben declararse ANTES de las funciones
   processGpsNmeaLine(), readGPS(), hasFreshGpsFix() y
   printGpsDiagnostic(), porque PlatformIO compila main.cpp
   como C++ estándar.
   ========================================================= */
TinyGPSPlus gps;

static const uint8_t GPS_FLAG_MASK = 0x10;       // bit GPS válido en flags
static const uint8_t GPS_LAT_OFFSET = 36;        // int32 BE, latitud * 1e6
static const uint8_t GPS_LON_OFFSET = 40;        // int32 BE, longitud * 1e6
static const uint8_t GPS_SATS_OFFSET = 44;       // uint8
static const uint8_t GPS_HDOP_X10_OFFSET = 45;   // uint8; 255 = inválido
static const uint8_t EXTENDED_PAYLOAD_SIZE = 46;
static const uint32_t GPS_MAX_AGE_MS = 15000;

uint32_t gpsChars = 0;
uint32_t gpsSentences = 0;
uint32_t gpsGgaCount = 0;
uint32_t gpsRmcCount = 0;
uint32_t gpsGsvCount = 0;
int gpsGgaFixQuality = 0;
int gpsGgaSatellites = 0;
float gpsGgaHdop = 99.0f;
char gpsRmcStatus = 'V';
String gpsNmeaLine = "";
uint32_t lastGpsDiagnostic = 0;

// Estado de encendido/apagado lógico del GNSS.
// El módulo parte encendido y luego se controla según el beacon.
bool gpsModuleActive = true;
bool gpsNewFixSinceWake = false;
uint32_t gpsActivatedAt = 0;

// Recuperación del L76K después de salir del modo beacon.
bool gpsWakeRecoveryPending = false;
bool gpsWakeRecoveryRunning = false;
uint32_t gpsCharsAtActivation = 0;
uint32_t gpsLastRecoveryAt = 0;
uint8_t gpsRecoveryAttempts = 0;

static const uint32_t GPS_NMEA_START_TIMEOUT_MS = 10000;
static const uint32_t GPS_RECOVERY_COOLDOWN_MS = 15000;
static const uint8_t GPS_MAX_RECOVERY_ATTEMPTS = 3;

static const uint8_t GPS_ACTIVE_FLAG_MASK = 0x20; // GPS encendido/buscando

/* =========================================================
   GPS L76K
   ========================================================= */
String getGpsField(const String &data, int fieldIndex) {
  int currentField = 0;
  int startIndex = 0;

  for (int i = 0; i <= data.length(); i++) {
    if (i == data.length() || data.charAt(i) == ',') {
      if (currentField == fieldIndex) {
        return data.substring(startIndex, i);
      }
      currentField++;
      startIndex = i + 1;
    }
  }
  return "";
}

void processGpsNmeaLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line.indexOf("GGA") >= 0) {
    gpsGgaCount++;
    gpsGgaFixQuality = getGpsField(line, 6).toInt();
    gpsGgaSatellites = getGpsField(line, 7).toInt();

    String hdopField = getGpsField(line, 8);
    if (hdopField.length() > 0) {
      gpsGgaHdop = hdopField.toFloat();
    }
  }

  if (line.indexOf("RMC") >= 0) {
    gpsRmcCount++;
    String statusField = getGpsField(line, 2);
    if (statusField.length() > 0) {
      gpsRmcStatus = statusField.charAt(0);
    }
  }

  if (line.indexOf("GSV") >= 0) {
    gpsGsvCount++;
  }
}

void resetGPS() {
  pinMode(Gps_Wakeup_Pin, OUTPUT);
  digitalWrite(Gps_Wakeup_Pin, HIGH);

  gpsModuleActive = true;
  gpsNewFixSinceWake = false;
  gpsActivatedAt = millis();
  gpsCharsAtActivation = gpsChars;

#if !defined(VERSION_1)
  pinMode(Gps_Reset_Pin, OUTPUT);
  digitalWrite(Gps_Reset_Pin, HIGH);
  delay(10);
  digitalWrite(Gps_Reset_Pin, LOW);
  delay(10);
  digitalWrite(Gps_Reset_Pin, HIGH);
  delay(500);
#endif
}

void readGPS() {
  if (!gpsModuleActive || gpsWakeRecoveryRunning) {
    while (SerialGPS.available()) {
      (void)SerialGPS.read();
    }
    return;
  }

  while (SerialGPS.available()) {
    char c = (char)SerialGPS.read();
    gpsChars++;

    if (gps.encode(c)) {
      gpsSentences++;

      if (gps.location.isUpdated()) {
        gpsNewFixSinceWake = true;
      }
    }

    if (c == '\n') {
      processGpsNmeaLine(gpsNmeaLine);
      gpsNmeaLine = "";
    } else if (c != '\r') {
      gpsNmeaLine += c;
      if (gpsNmeaLine.length() > 180) {
        gpsNmeaLine = "";
      }
    }
  }
}

void delayReadingGps(uint32_t ms) {
  uint32_t start = millis();
  while ((millis() - start) < ms) {
    if (!gpsWakeRecoveryRunning) {
      readGPS();
    } else {
      while (SerialGPS.available()) {
        (void)SerialGPS.read();
      }
    }
    delay(5);
  }
}

void configureGpsPcas() {
  SerialGPS.write("$PCAS04,5*1C\r\n");  // GPS + GLONASS
  SerialGPS.flush();
  delay(250);

  SerialGPS.write("$PCAS03,1,1,1,1,1,1,1,1,0,0,,,0,0*02\r\n");
  SerialGPS.flush();
  delay(250);

  SerialGPS.write("$PCAS11,3*1E\r\n");  // modo vehículo
  SerialGPS.flush();
  delay(250);
}

void performGpsHardwareRecovery(const char *reason) {
  if (!gpsModuleActive || gpsWakeRecoveryRunning) return;

  gpsWakeRecoveryRunning = true;
  gpsWakeRecoveryPending = false;

  SerialMon.print("[GPS-RECOVERY] Inicio | motivo=");
  SerialMon.println(reason);

  while (SerialGPS.available()) {
    (void)SerialGPS.read();
  }

  gpsNmeaLine = "";
  gpsNewFixSinceWake = false;
  gpsGgaFixQuality = 0;
  gpsGgaSatellites = 0;
  gpsGgaHdop = 99.0f;
  gpsRmcStatus = 'V';

  // Despertar y reinicializar físicamente el L76K.
  digitalWrite(Gps_Wakeup_Pin, HIGH);

#if !defined(VERSION_1)
  digitalWrite(Gps_Reset_Pin, HIGH);
  delay(10);
  digitalWrite(Gps_Reset_Pin, LOW);
  delay(10);
  digitalWrite(Gps_Reset_Pin, HIGH);
  delay(500);
#else
  delay(500);
#endif

  configureGpsPcas();

  while (SerialGPS.available()) {
    (void)SerialGPS.read();
  }

  gpsActivatedAt = millis();
  gpsCharsAtActivation = gpsChars;
  gpsLastRecoveryAt = millis();
  gpsWakeRecoveryRunning = false;

  SerialMon.print("[GPS-RECOVERY] Listo | intento=");
  SerialMon.println(gpsRecoveryAttempts);
}

void setupGPS() {
  pinMode(Gps_pps_Pin, INPUT);

  SerialGPS.setPins(Gps_Rx_Pin, Gps_Tx_Pin);
  SerialGPS.begin(9600);
  SerialGPS.flush();

  pinMode(Gps_Wakeup_Pin, OUTPUT);
#if !defined(VERSION_1)
  pinMode(Gps_Reset_Pin, OUTPUT);
#endif

  gpsModuleActive = true;
  gpsRecoveryAttempts = 1;
  performGpsHardwareRecovery("inicio");

  SerialMon.println("[GPS] Inicializado: RX=P1.9 TX=P1.8, 9600 baud");
}

void serviceGpsWakeRecovery() {
  if (!gpsModuleActive || gpsWakeRecoveryRunning) return;

  uint32_t now = millis();

  if (gpsWakeRecoveryPending && !(LMIC.opmode & OP_TXRXPEND)) {
    gpsRecoveryAttempts++;
    performGpsHardwareRecovery("despertar desde modo beacon");
    return;
  }

  bool noNewNmea = gpsChars == gpsCharsAtActivation;
  bool startTimedOut = (now - gpsActivatedAt) >= GPS_NMEA_START_TIMEOUT_MS;
  bool cooldownOk = (now - gpsLastRecoveryAt) >= GPS_RECOVERY_COOLDOWN_MS;

  if (noNewNmea &&
      startTimedOut &&
      cooldownOk &&
      gpsRecoveryAttempts < GPS_MAX_RECOVERY_ATTEMPTS &&
      !(LMIC.opmode & OP_TXRXPEND)) {

    gpsRecoveryAttempts++;
    performGpsHardwareRecovery("sin caracteres NMEA");
  }
}

bool hasFreshGpsFix() {
  return gpsModuleActive &&
         gpsNewFixSinceWake &&
         (millis() - gpsActivatedAt >= 1000) &&
         gps.location.isValid() &&
         gps.location.age() <= GPS_MAX_AGE_MS &&
         gps.location.lat() >= -90.0 &&
         gps.location.lat() <= 90.0 &&
         gps.location.lng() >= -180.0 &&
         gps.location.lng() <= 180.0 &&
         (gpsGgaFixQuality > 0 || gpsRmcStatus == 'A');
}

uint8_t getGpsStatusHr20() {
  return hasFreshGpsFix() ? 1 : 0;
}

void printGpsDiagnostic() {
  uint32_t now = millis();
  if ((now - lastGpsDiagnostic) < 5000) return;
  lastGpsDiagnostic = now;

  SerialMon.print("[GPS] mode=");
  if (!gpsModuleActive) {
    SerialMon.print("OFF/BEACON");
  } else if (gpsWakeRecoveryRunning || gpsWakeRecoveryPending) {
    SerialMon.print("ON/RECOVERY");
  } else {
    SerialMon.print("ON/BUSCANDO");
  }
  SerialMon.print(" newChars=");
  SerialMon.print(gpsChars - gpsCharsAtActivation);
  SerialMon.print(" chars=");
  SerialMon.print(gpsChars);
  SerialMon.print(" sentences=");
  SerialMon.print(gpsSentences);
  SerialMon.print(" GGA=");
  SerialMon.print(gpsGgaCount);
  SerialMon.print(" RMC=");
  SerialMon.print(gpsRmcCount);
  SerialMon.print(" GSV=");
  SerialMon.print(gpsGsvCount);
  SerialMon.print(" fixQ=");
  SerialMon.print(gpsGgaFixQuality);
  SerialMon.print(" rmc=");
  SerialMon.print(gpsRmcStatus);
  SerialMon.print(" sats=");
  SerialMon.print(gps.satellites.isValid() ? gps.satellites.value() : 0);
  SerialMon.print(" valid=");
  SerialMon.print(hasFreshGpsFix() ? "YES" : "NO");
  SerialMon.print(" HR20=");
  SerialMon.print(getGpsStatusHr20());

  if (gps.location.isValid()) {
    SerialMon.print(" lat=");
    SerialMon.print(gps.location.lat(), 6);
    SerialMon.print(" lon=");
    SerialMon.print(gps.location.lng(), 6);
    SerialMon.print(" age=");
    SerialMon.print(gps.location.age());
  }

  SerialMon.println();
}

/* =========================================================
   LORAWAN MCCI LMIC + SX1262 + UG65
   =========================================================
   Diagnostico V4 ya comprobó EV_TXSTART / EV_TXCOMPLETE.
   Esta versión integra ese bloque al firmware completo con:
   pantalla, beacons, banda cardiaca, panico y doble click; payload 46B.
   ========================================================= */

static const uint8_t LORAWAN_APP_PORT = 1;
static bool lmicJoined = false;
static bool lmicTxPending = false;

// IMPORTANTE LMIC:
// AppEUI / JoinEUI y DevEUI van en little-endian, es decir, invertidos.
// AppKey va normal, igual que en UG65.
static const u1_t PROGMEM APPEUI[8] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00 };
static const u1_t PROGMEM DEVEUI[8] = { 0xE6, 0xF0, 0xCC, 0xAB, 0xE7, 0x6A, 0xE7, 0xCB };
static const u1_t PROGMEM APPKEY[16] = { 0x38, 0xA8, 0x52, 0x30, 0x8D, 0x24, 0x35, 0x5D, 0x14, 0x28, 0xA4, 0xEC, 0x85, 0x3E, 0xDF, 0x83 };

void os_getArtEui(u1_t* buf) { memcpy_P(buf, APPEUI, 8); }
void os_getDevEui(u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }
void os_getDevKey(u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

class T_EchoHalConfiguration_t : public Arduino_LMIC::HalConfiguration_t {
public:
  virtual u1_t queryBusyPin(void) override { return LoRa_Busy; }
  virtual bool queryUsingDcdc(void) override { return true; }
  virtual bool queryUsingDIO2AsRfSwitch(void) override { return true; }
  virtual bool queryUsingDIO3AsTCXOSwitch(void) override { return true; }
};

static T_EchoHalConfiguration_t myLmicConfig;

const lmic_pinmap lmic_pins = {
  .nss = LoRa_Cs,
  .rxtx = LMIC_UNUSED_PIN,
  .rst = LoRa_Rst,
  .dio = {LoRa_Dio1, LMIC_UNUSED_PIN, LMIC_UNUSED_PIN},
  .rxtx_rx_active = 0,
  .rssi_cal = 10,
  .spi_freq = 8000000,
  .pConfig = &myLmicConfig,
};

void setupLoRaWAN();
void onEvent(ev_t ev);
bool sendLoRaWANPayloadNow(const uint8_t *data, uint8_t len);

// UUID MinerGuard usado en el codigo Heltec.
static const uint8_t MINERGUARD_UUID[16] = {
  0xE2, 0xC5, 0x6D, 0xB5, 0xDF, 0xFB, 0x48, 0xD2,
  0xB0, 0x60, 0xD0, 0xF5, 0xA7, 0x10, 0x96, 0xE0
};

/* =========================================================
   DISPLAY E-PAPER T-ECHO
   ========================================================= */
SPIClass    *dispPort = nullptr;
GxIO_Class  *io       = nullptr;
GxEPD_Class *display  = nullptr;

static const uint16_t EPD_W = 200;
static const uint16_t EPD_H = 200;

static bool screenNeedsUpdate = true;
static uint32_t lastScreenUpdate = 0;
static const uint32_t SCREEN_MIN_INTERVAL_MS = 1800;

char scrLine1[32] = "Iniciando";
char scrLine2[32] = "Buscando Beacons";
char scrLine3[32] = "Hector Quiroz";

bool heartBigFrame = false;

/* =========================================================
   BLE HEART RATE / BATTERY
   ========================================================= */
BLEClientService        svcHR(UUID16_SVC_HEART_RATE);
BLEClientCharacteristic chrHR(UUID16_CHR_HEART_RATE_MEASUREMENT);
BLEClientService        svcBAT(UUID16_SVC_BATTERY);
BLEClientCharacteristic chrBAT(UUID16_CHR_BATTERY_LEVEL);

volatile bool bleConnected = false;
volatile bool hrValid = false;
volatile uint8_t hrBpm = 0;
volatile bool bandBatValid = false;
volatile uint8_t bandBatPct = 0;

uint32_t beatIntervalMs = 1000;
uint32_t lastBeatMs = 0;
uint32_t nextBeatMs = 0;
uint32_t lastLedPulseMs = 0;

uint32_t lastScanKick = 0;


/* =========================================================
   BEACONS
   ========================================================= */
struct BeaconReading {
  bool valid;
  uint16_t major;
  uint16_t minor;
  int8_t rssi;
  uint32_t seenAt;
};

BeaconReading topBeacons[3] = {
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0}
};

BeaconReading snapshotA[3] = {
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0}
};

BeaconReading snapshotB[3] = {
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0},
  {false, 0, 0, -127, 0}
};

static const uint32_t BEACON_TIMEOUT_MS = 15000;

// =========================================================
// SELECTOR AUTOMÁTICO BEACON / GPS
// =========================================================
// GPS se enciende si:
//   - no existe beacon reciente, o
//   - el beacon más fuerte cae a -94 dBm o menos.
//
// GPS se apaga si:
//   - existe beacon reciente, y
//   - el beacon más fuerte alcanza -85 dBm o más.
//
// La zona -93 a -86 dBm entrega histéresis.
// Estos valores son más adecuados para volver al modo beacon al reingresar.
static const int8_t GPS_ON_BEACON_RSSI_DBM   = -94;
static const int8_t GPS_OFF_BEACON_RSSI_DBM  = -85;
static const uint32_t BEACON_SWITCH_RECENT_MS = 7000;
static const uint32_t GPS_SWITCH_CONFIRM_MS   = 1500;
static const uint32_t GPS_MODE_CHECK_MS       = 300;
static const uint32_t SELECTOR_LOG_INTERVAL_MS = 2000;

uint32_t lastSelectorLog = 0;

bool gpsPendingModeValid = false;
bool gpsPendingDesiredActive = true;
uint32_t gpsPendingSince = 0;
uint32_t lastGpsModeCheck = 0;

/* =========================================================
   PANICO / ENVIO
   ========================================================= */
volatile bool panicActive = false;
volatile bool isPressingButton = false;

bool buttonPrev = false;
uint32_t buttonPressStart = 0;
bool buttonHeld = false;
uint32_t panicEndMs = 0;

// Iluminacion de pantalla por doble click del USER.
// Se detecta con interrupcion para no perder clicks mientras la e-paper
// esta haciendo display->update(), que bloquea el loop por algunos segundos.
static bool backlightOn = false;
static const uint8_t BACKLIGHT_ON_LEVEL  = HIGH;
static const uint8_t BACKLIGHT_OFF_LEVEL = LOW;

static const uint32_t HOLD_TIME_MS = 1500;
static const uint32_t PANIC_DURATION_MS = 60000;
static const uint32_t DOUBLE_CLICK_MS = 650;
static const uint32_t BUTTON_DEBOUNCE_MS = 35;

volatile bool backlightToggleRequest = false;
volatile uint32_t isrLastButtonChange = 0;
volatile uint32_t isrButtonPressStart = 0;
volatile uint32_t isrLastShortRelease = 0;

volatile bool requestImmediateTx = false;
volatile bool snapshotATaken = false;
uint32_t lastPeriodicSend = 0;
static const uint32_t TX_INTERVAL_MS = 15000;

uint8_t appData[64];
uint8_t appDataSize = 0;

/* =========================================================
   PROTOTIPOS
   ========================================================= */
void boardInit();
void setupDisplay();
void drawMainScreen();
void drawSplash(const char *title, const char *sub);
void drawHeart(int cx, int cy, int size, bool big);
void drawTopBeaconsList(int x, int y);
void requestScreenUpdate(const char *l1, const char *l2, const char *l3);
void updateDisplayPosition();
void handlePanicButton();
void userButtonISR();
void processBacklightToggle();
void setScreenBacklight(bool on);
void toggleScreenBacklight();
void updateLedHeartbeat();

void setupGPS();
void resetGPS();
void readGPS();
void delayReadingGps(uint32_t ms);
void configureGpsPcas();
void performGpsHardwareRecovery(const char *reason);
void serviceGpsWakeRecovery();
void processGpsNmeaLine(String line);
String getGpsField(const String &data, int fieldIndex);
bool hasFreshGpsFix();
uint8_t getGpsStatusHr20();
uint8_t getGpsSatellitesPayload();
uint8_t getGpsHdopX10Payload();
void writeInt32BE(uint8_t *out, uint8_t offset, int32_t value);
void printGpsDiagnostic();
void setGpsModuleActive(bool active, const char *reason);
void updateGpsModeFromBeacons();
bool hasRecentBeaconForGpsControl();

bool matchBandByMac(const ble_gap_addr_t &addr);
void macToString(const ble_gap_addr_t &addr, char *out, size_t len);
void scan_cb(ble_gap_evt_adv_report_t *report);
void connect_cb(uint16_t conn_handle);
void disconnect_cb(uint16_t conn_handle, uint8_t reason);
void hr_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len);
void bat_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len);

bool parseIBeacon(ble_gap_evt_adv_report_t *report, uint16_t &major, uint16_t &minor);
void updateTopBeacon(uint16_t major, uint16_t minor, int8_t rssi);
void cleanupOldBeacons();
void sortTopBeacons();

uint8_t encodeRSSI(int8_t rssi);
void buildExtendedPayload(uint8_t *out, uint8_t &sz, bool panic);
void printPayloadHex(const uint8_t *data, uint8_t len);

/* =========================================================
   SETUP
   ========================================================= */
void setup() {
  boardInit();

  SerialMon.println("======================================");
  SerialMon.println("[BOOT] SKETCH: V9 GPS AUTO + WAKE RECOVERY");
  SerialMon.print("[BOOT] NODE_ID: ");
  SerialMon.println(NODE_ID);
  SerialMon.print("[BOOT] PERSON_NAME: ");
  SerialMon.println(PERSON_NAME);
  SerialMon.print("[BOOT] NODE_LABEL: ");
  SerialMon.println(NODE_LABEL);
  SerialMon.print("[BOOT] DevEUI UG65: ");
  SerialMon.println("CBE76AE7ABCCF0E6");
  SerialMon.println("======================================");

  drawSplash("MINERGUARD", "Iniciando T-Echo");
  delayReadingGps(1200);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(BUTTON_PIN), userButtonISR, CHANGE);

  Bluefruit.begin(0, 1);
  Bluefruit.setName(NODE_LABEL);
  Bluefruit.setTxPower(4);

  svcHR.begin();
  chrHR.begin();

  svcBAT.begin();
  chrBAT.begin();

  Bluefruit.Central.setConnectCallback(connect_cb);
  Bluefruit.Central.setDisconnectCallback(disconnect_cb);

  Bluefruit.Scanner.setRxCallback(scan_cb);
  Bluefruit.Scanner.filterRssi(-100);
  Bluefruit.Scanner.setInterval(160, 160);
  Bluefruit.Scanner.useActiveScan(false);
  Bluefruit.Scanner.restartOnDisconnect(true);
  Bluefruit.Scanner.start(0);

  setupLoRaWAN();

  requestScreenUpdate("Minerguard", "Escaneando...", PERSON_NAME);

  lastPeriodicSend = millis();
  nextBeatMs = millis() + beatIntervalMs;
}

/* =========================================================
   LOOP
   ========================================================= */
void loop() {
  uint32_t now = millis();

  // Consumir NMEA continuamente, igual que en el logger CSV funcional.
  readGPS();

  // Mantiene viva la maquina LoRaWAN LMIC.
  os_runloop_once();

  // Procesa el doble click capturado por interrupcion. No refresca pantalla.
  processBacklightToggle();

  // Mantener scanner activo como en Heltec.
  if (now - lastScanKick > 1500) {
    lastScanKick = now;
    if (!Bluefruit.Scanner.isRunning()) {
      Bluefruit.Scanner.start(0);
    }
  }

  handlePanicButton();
  updateLedHeartbeat();

  // Mantiene BLE/beacons siempre activos y decide si el GNSS debe
  // estar encendido o en standby según el RSSI del beacon más fuerte.
  updateGpsModeFromBeacons();

  // Reinicialización robusta al salir del modo beacon.
  serviceGpsWakeRecovery();

  // Snapshot A a mitad de ventana, igual a la idea del codigo Heltec.
  uint32_t elapsed = now - lastPeriodicSend;
  if (elapsed >= 15000 && !snapshotATaken) {
    cleanupOldBeacons();
    sortTopBeacons();
    memcpy(snapshotA, topBeacons, sizeof(topBeacons));
    snapshotATaken = true;
  }

  // Preparar payload cada 15s o inmediatamente por panico.
  if (elapsed >= TX_INTERVAL_MS || requestImmediateTx) {
    requestImmediateTx = false;
    buildExtendedPayload(appData, appDataSize, panicActive);

    SerialMon.print("[PAYLOAD 46B] ");
    printPayloadHex(appData, appDataSize);
    SerialMon.println();

    if (lmicJoined) {
      sendLoRaWANPayloadNow(appData, appDataSize);
    } else {
      SerialMon.println("[LMIC] Payload listo, esperando EV_JOINED para TX real.");
    }
  }

  // Actualizar posicion por timeout de beacons.
  static uint32_t lastPositionRefresh = 0;
  if (now - lastPositionRefresh > 2000) {
    lastPositionRefresh = now;
    cleanupOldBeacons();
    sortTopBeacons();
    updateDisplayPosition();
  }

  // Refresco de e-paper: lento, no como TFT.
  if (screenNeedsUpdate && (now - lastScreenUpdate >= SCREEN_MIN_INTERVAL_MS)) {
    if (!(LMIC.opmode & OP_TXRXPEND)) {
      lastScreenUpdate = now;
      screenNeedsUpdate = false;
      drawMainScreen();
    }
  }

  // Segunda pasada LMIC al final del loop para no atrasar eventos.
  os_runloop_once();

  readGPS();
  printGpsDiagnostic();
}

/* =========================================================
   HARDWARE / DISPLAY
   ========================================================= */
void boardInit() {
  SerialMon.begin(MONITOR_SPEED);
  delay(200);

  pinMode(Power_Enable_Pin, OUTPUT);
  digitalWrite(Power_Enable_Pin, HIGH);

  pinMode(ePaper_Backlight, OUTPUT);
  digitalWrite(ePaper_Backlight, BACKLIGHT_OFF_LEVEL);
  backlightOn = false;

  pinMode(GreenLed_Pin, OUTPUT);
  pinMode(RedLed_Pin, OUTPUT);
  pinMode(BlueLed_Pin, OUTPUT);

  digitalWrite(GreenLed_Pin, HIGH);
  digitalWrite(RedLed_Pin, HIGH);
  digitalWrite(BlueLed_Pin, HIGH);

  // Inicia GPS con la misma secuencia que el logger CSV funcional.
  setupGPS();

  setupDisplay();
}

void setupDisplay() {
  dispPort = new SPIClass(
    NRF_SPIM2,
    ePaper_Miso,
    ePaper_Sclk,
    ePaper_Mosi
  );

  io = new GxIO_Class(
    *dispPort,
    ePaper_Cs,
    ePaper_Dc,
    ePaper_Rst
  );

  display = new GxEPD_Class(
    *io,
    ePaper_Rst,
    ePaper_Busy
  );

  dispPort->begin();
  display->init();
  display->setRotation(3);
  SerialMon.println("[DISPLAY] Rotacion forzada: 3");
  display->setTextColor(GxEPD_BLACK);

  // Limpieza agresiva de e-paper para evitar nombres/frames fantasma.
  display->fillScreen(GxEPD_WHITE);
  display->update();
  delayReadingGps(200);
  display->fillScreen(GxEPD_BLACK);
  display->update();
  delayReadingGps(250);
  display->fillScreen(GxEPD_WHITE);
  display->update();
  delayReadingGps(250);
}

void drawSplash(const char *title, const char *sub) {
  display->fillScreen(GxEPD_WHITE);
  display->fillRect(0, 0, EPD_W, 34, GxEPD_BLACK);

  display->setTextColor(GxEPD_WHITE);
  display->setFont(&FreeMonoBold12pt7b);
  display->setCursor(18, 24);
  display->print(title);

  display->setTextColor(GxEPD_BLACK);
  display->setFont(&FreeMonoBold9pt7b);
  display->setCursor(18, 82);
  display->print(sub);

  display->drawRoundRect(16, 112, 168, 46, 8, GxEPD_BLACK);
  display->setCursor(34, 142);
  display->print("BLE + BEACONS");

  display->update();
}

void drawMainScreen() {
  display->fillScreen(GxEPD_WHITE);

  if (panicActive) {
    display->fillRect(0, 0, EPD_W, 34, GxEPD_BLACK);
    display->setTextColor(GxEPD_WHITE);
    display->setFont(&FreeMonoBold12pt7b);
    display->setCursor(38, 24);
    display->print("PANICO");

    display->setTextColor(GxEPD_BLACK);
    display->setFont(&FreeMonoBold18pt7b);
    display->setCursor(28, 108);
    display->print("PANICO");

    display->setFont(&FreeMonoBold9pt7b);
    display->setCursor(16, 155);
    display->print("Enviando alerta");
    display->update();
    return;
  }

  bool showHeart = bleConnected && hrValid;

  // Panel superior, equivalente al layout Heltec:
  // BPM grande a la izquierda + corazon a la derecha.
  display->drawFastHLine(0, 68, EPD_W, GxEPD_BLACK);

  if (showHeart) {
    char bpmText[8];
    snprintf(bpmText, sizeof(bpmText), "%u", hrBpm);

    display->setFont(&FreeMonoBold18pt7b);
    display->setCursor(14, 48);
    if (hrBpm < 100) display->print(" ");
    display->print(bpmText);

    display->setFont(&FreeMonoBold9pt7b);
    display->setCursor(91, 48);
    display->print("BPM");

    heartBigFrame = !heartBigFrame;
    drawHeart(158, 35, heartBigFrame ? 18 : 14, heartBigFrame);
  } else {
    display->setFont(&FreeMonoBold12pt7b);
    display->setCursor(10, 42);
    display->print(scrLine1);
  }

  // Zona inferior de beacons/estado.
  display->setFont(&FreeMonoBold12pt7b);
  display->setCursor(10, 98);
  display->print(scrLine2);

  display->setFont(&FreeMonoBold9pt7b);
  display->setCursor(10, 128);
  display->print(scrLine3);

  drawTopBeaconsList(10, 150);

  if (isPressingButton && !panicActive) {
    display->drawRoundRect(6, 174, 188, 22, 4, GxEPD_BLACK);
    display->setFont(&FreeMonoBold9pt7b);
    display->setCursor(14, 191);
    display->print("Mantenga: panico");
  }

  display->update();
}

void drawHeart(int cx, int cy, int size, bool big) {
  int r = size / 3;

  if (big) {
    display->drawCircle(cx, cy, size + 7, GxEPD_BLACK);
    display->drawCircle(cx, cy, size + 2, GxEPD_BLACK);
  }

  display->fillCircle(cx - r, cy - r, r, GxEPD_BLACK);
  display->fillCircle(cx + r, cy - r, r, GxEPD_BLACK);
  display->fillTriangle(
    cx - 2 * r, cy - r,
    cx + 2 * r, cy - r,
    cx, cy + 2 * r,
    GxEPD_BLACK
  );

  if (big) {
    display->fillCircle(cx - r - 2, cy - r - 3, 3, GxEPD_WHITE);
  }
}

void drawTopBeaconsList(int x, int y) {
  display->setFont(&FreeMonoBold9pt7b);

  if (!topBeacons[0].valid) {
    display->setCursor(x, y + 18);
    display->print("Beacons: --");
    return;
  }

  display->setCursor(x, y + 13);
  display->print("TOP RSSI");

  for (int i = 0; i < 3; i++) {
    if (!topBeacons[i].valid) continue;

    int yy = y + 31 + (i * 15);
    display->setCursor(x, yy);
    display->print(i + 1);
    display->print(":PK");
    display->print(topBeacons[i].minor);
    display->print(" ");
    display->print(topBeacons[i].rssi);
  }
}

/* =========================================================
   PANTALLA INTELIGENTE
   ========================================================= */
void requestScreenUpdate(const char *l1, const char *l2, const char *l3) {
  bool changed =
    strncmp(scrLine1, l1, sizeof(scrLine1) - 1) != 0 ||
    strncmp(scrLine2, l2, sizeof(scrLine2) - 1) != 0 ||
    strncmp(scrLine3, l3, sizeof(scrLine3) - 1) != 0;

  if (!changed) return;

  strncpy(scrLine1, l1, sizeof(scrLine1) - 1);
  strncpy(scrLine2, l2, sizeof(scrLine2) - 1);
  strncpy(scrLine3, l3, sizeof(scrLine3) - 1);

  scrLine1[sizeof(scrLine1) - 1] = '\0';
  scrLine2[sizeof(scrLine2) - 1] = '\0';
  scrLine3[sizeof(scrLine3) - 1] = '\0';

  screenNeedsUpdate = true;
}

void updateDisplayPosition() {
  if (panicActive) {
    screenNeedsUpdate = true;
    return;
  }

  char l1[32] = "Buscando...";
  char l2[32] = "";
  char l3[32] = "";
  snprintf(l3, sizeof(l3), "%s", PERSON_NAME);

  if (bleConnected && hrValid) {
    snprintf(l1, sizeof(l1), "HR: %u bpm", hrBpm);

    if (topBeacons[0].valid) {
      snprintf(l2, sizeof(l2), "PK ACTUAL:%u", topBeacons[0].minor);
    } else {
      snprintf(l2, sizeof(l2), "PK: Fuera rango");
    }
  } else {
    if (topBeacons[0].valid && !gpsModuleActive) {
      snprintf(l1, sizeof(l1), "PK ACTUAL");
      snprintf(l2, sizeof(l2), "%u", topBeacons[0].minor);
    } else if (gpsModuleActive && hasFreshGpsFix()) {
      snprintf(l1, sizeof(l1), "GPS ACTIVO");
      snprintf(l2, sizeof(l2), "SAT:%u", getGpsSatellitesPayload());
    } else if (gpsModuleActive && (gpsWakeRecoveryPending || gpsWakeRecoveryRunning)) {
      snprintf(l1, sizeof(l1), "GPS INICIANDO");
      snprintf(l2, sizeof(l2), "Recovery");
    } else if (gpsModuleActive) {
      snprintf(l1, sizeof(l1), "GPS BUSCANDO");
      snprintf(l2, sizeof(l2), "Sin fix");
    } else {
      snprintf(l1, sizeof(l1), "Minerguard");
      snprintf(l2, sizeof(l2), "Escaneando...");
    }
  }

  requestScreenUpdate(l1, l2, l3);
}

/* =========================================================
   BOTON DE PANICO / LED
   ========================================================= */
void handlePanicButton() {
  bool reading = (digitalRead(BUTTON_PIN) == LOW);
  uint32_t now = millis();

  if (reading != isPressingButton) {
    isPressingButton = reading;
    screenNeedsUpdate = true;
  }

  if (reading) {
    if (!buttonPrev) {
      buttonPressStart = now;
      buttonHeld = false;
    }

    if (!buttonHeld && (now - buttonPressStart) >= HOLD_TIME_MS) {
      buttonHeld = true;

      if (!panicActive) {
        panicActive = true;
        panicEndMs = now + PANIC_DURATION_MS;

        requestImmediateTx = true;
        screenNeedsUpdate = true;
      }
    }
  }

  buttonPrev = reading;

  if (panicActive && ((int32_t)(now - panicEndMs) >= 0)) {
    panicActive = false;
    requestImmediateTx = true;
    screenNeedsUpdate = true;
  }
}

void userButtonISR() {
  uint32_t now = millis();

  // Debounce por software dentro de la ISR.
  if ((now - isrLastButtonChange) < BUTTON_DEBOUNCE_MS) {
    return;
  }
  isrLastButtonChange = now;

  bool pressed = (digitalRead(BUTTON_PIN) == LOW);

  if (pressed) {
    isrButtonPressStart = now;
    return;
  }

  uint32_t pressDuration = now - isrButtonPressStart;

  // Solo los clicks cortos participan en el doble click.
  // Una pulsacion larga queda reservada exclusivamente para panico.
  if (pressDuration < HOLD_TIME_MS) {
    if (isrLastShortRelease != 0 && (now - isrLastShortRelease) <= DOUBLE_CLICK_MS) {
      backlightToggleRequest = true;
      isrLastShortRelease = 0;
    } else {
      isrLastShortRelease = now;
    }
  } else {
    isrLastShortRelease = 0;
  }
}

void processBacklightToggle() {
  bool shouldToggle = false;

  noInterrupts();
  if (backlightToggleRequest) {
    backlightToggleRequest = false;
    shouldToggle = true;
  }
  interrupts();

  if (shouldToggle && !panicActive) {
    toggleScreenBacklight();
  }

  // Si queda un click suelto y no llega el segundo, se descarta.
  noInterrupts();
  if (isrLastShortRelease != 0 && (millis() - isrLastShortRelease) > DOUBLE_CLICK_MS) {
    isrLastShortRelease = 0;
  }
  interrupts();
}

void setScreenBacklight(bool on) {
  backlightOn = on;
  pinMode(ePaper_Backlight, OUTPUT);
  digitalWrite(ePaper_Backlight, backlightOn ? BACKLIGHT_ON_LEVEL : BACKLIGHT_OFF_LEVEL);

  SerialMon.print("[USER] Backlight ");
  SerialMon.println(backlightOn ? "ON" : "OFF");
}

void toggleScreenBacklight() {
  setScreenBacklight(!backlightOn);
}

void updateLedHeartbeat() {
  uint32_t now = millis();

  if (panicActive) {
    if (now - lastLedPulseMs >= 250) {
      lastLedPulseMs = now;
      digitalWrite(RedLed_Pin, !digitalRead(RedLed_Pin));
      digitalWrite(GreenLed_Pin, HIGH);
      digitalWrite(BlueLed_Pin, HIGH);
    }
    return;
  }

  if (!bleConnected) {
    if (now - lastLedPulseMs >= 500) {
      lastLedPulseMs = now;
      digitalWrite(BlueLed_Pin, !digitalRead(BlueLed_Pin));
      digitalWrite(RedLed_Pin, HIGH);
      digitalWrite(GreenLed_Pin, HIGH);
    }
    return;
  }

  if (bleConnected && !hrValid) {
    if (now - lastLedPulseMs >= 300) {
      lastLedPulseMs = now;
      digitalWrite(GreenLed_Pin, !digitalRead(GreenLed_Pin));
      digitalWrite(RedLed_Pin, HIGH);
      digitalWrite(BlueLed_Pin, HIGH);
    }
    return;
  }

  if (hrValid && hrBpm > 0) {
    if ((int32_t)(now - nextBeatMs) >= 0) {
      lastBeatMs = now;
      nextBeatMs = now + beatIntervalMs;
      digitalWrite(RedLed_Pin, LOW);
      digitalWrite(GreenLed_Pin, HIGH);
      digitalWrite(BlueLed_Pin, HIGH);
    }

    if (now - lastBeatMs > 100) {
      digitalWrite(RedLed_Pin, HIGH);
    }
  }
}

/* =========================================================
   BLE
   ========================================================= */
bool matchBandByMac(const ble_gap_addr_t &addr) {
  return memcmp(addr.addr, BAND_MAC_REVERSED, 6) == 0 ||
         memcmp(addr.addr, BAND_MAC_NORMAL, 6) == 0;
}

void macToString(const ble_gap_addr_t &addr, char *out, size_t len) {
  const uint8_t *a = addr.addr;
  snprintf(out, len, "%02X:%02X:%02X:%02X:%02X:%02X",
           a[5], a[4], a[3], a[2], a[1], a[0]);
}

void scan_cb(ble_gap_evt_adv_report_t *report) {
  uint16_t major = 0;
  uint16_t minor = 0;

  if (parseIBeacon(report, major, minor)) {
    updateTopBeacon(major, minor, report->rssi);
  }

  if (!bleConnected && matchBandByMac(report->peer_addr)) {
    char macbuf[18];
    macToString(report->peer_addr, macbuf, sizeof(macbuf));

    SerialMon.print("[BLE] Banda encontrada: ");
    SerialMon.println(macbuf);

    Bluefruit.Central.connect(report);
    return;
  }

  Bluefruit.Scanner.resume();
}

void connect_cb(uint16_t conn_handle) {
  bleConnected = true;
  requestScreenUpdate("Banda Conectada", "Sincronizando...", PERSON_NAME);

  SerialMon.println("[BLE] Banda conectada");

  if (svcHR.discover(conn_handle) && chrHR.discover()) {
    chrHR.setNotifyCallback(hr_notify_cb);
    chrHR.enableNotify();
    SerialMon.println("[BLE] HR notify activo");
  } else {
    SerialMon.println("[BLE] HR no encontrado");
  }

  if (svcBAT.discover(conn_handle) && chrBAT.discover()) {
    chrBAT.setNotifyCallback(bat_notify_cb);
    chrBAT.enableNotify();

    uint8_t v = 0;
    if (chrBAT.read(&v, 1)) {
      bandBatPct = v;
      bandBatValid = true;
    }
  }

  Bluefruit.Scanner.start(0);
}

void disconnect_cb(uint16_t, uint8_t) {
  bleConnected = false;
  hrValid = false;
  bandBatValid = false;

  requestScreenUpdate("Banda desconecta", "Reintentando...", PERSON_NAME);
  SerialMon.println("[BLE] Banda desconectada");

  Bluefruit.Scanner.start(0);
}

void hr_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len) {
  (void)chr;

  if (len < 2) return;

  uint8_t flags = data[0];
  uint8_t idx = 1;
  uint16_t bpm = 0;

  if (flags & 0x01) {
    if (len < 3) return;
    bpm = (uint16_t)data[idx] | ((uint16_t)data[idx + 1] << 8);
    idx += 2;
  } else {
    bpm = data[idx++];
  }

  if (flags & 0x08) {
    if (idx + 1 < len) idx += 2;
  }

  uint32_t rrIntervalMs = 0;

  if (flags & 0x10) {
    while (idx + 1 < len) {
      uint16_t rr = (uint16_t)data[idx] | ((uint16_t)data[idx + 1] << 8);
      idx += 2;

      if (rr > 0) {
        rrIntervalMs = ((uint32_t)rr * 1000UL) / 1024UL;
      }
    }
  }

  if (rrIntervalMs == 0 && bpm > 0) {
    rrIntervalMs = 60000UL / bpm;
  }

  if (bpm >= 30 && bpm <= 240) {
    hrBpm = (uint8_t)bpm;
    hrValid = true;
    beatIntervalMs = rrIntervalMs > 0 ? rrIntervalMs : beatIntervalMs;

    SerialMon.print("[HR] BPM=");
    SerialMon.println(hrBpm);

    updateDisplayPosition();
  }
}

void bat_notify_cb(BLEClientCharacteristic *chr, uint8_t *data, uint16_t len) {
  (void)chr;

  if (len < 1) return;

  bandBatPct = data[0];
  bandBatValid = true;

  SerialMon.print("[BAT] Banda=");
  SerialMon.print(bandBatPct);
  SerialMon.println("%");
}

/* =========================================================
   BEACONS
   ========================================================= */
bool parseIBeacon(ble_gap_evt_adv_report_t *report, uint16_t &major, uint16_t &minor) {
  const uint8_t *data = report->data.p_data;
  uint8_t len = report->data.len;

  for (uint8_t i = 0; i < len; ) {
    uint8_t fieldLen = data[i];

    if (fieldLen == 0) break;
    if ((uint16_t)i + fieldLen >= len) break;

    uint8_t type = data[i + 1];
    const uint8_t *payload = &data[i + 2];
    uint8_t payloadLen = fieldLen - 1;

    if (type == BLE_GAP_AD_TYPE_MANUFACTURER_SPECIFIC_DATA && payloadLen >= 25) {
      bool appleIBeacon =
        payload[0] == 0x4C &&
        payload[1] == 0x00 &&
        payload[2] == 0x02 &&
        payload[3] == 0x15;

      if (appleIBeacon && memcmp(&payload[4], MINERGUARD_UUID, 16) == 0) {
        major = ((uint16_t)payload[20] << 8) | payload[21];
        minor = ((uint16_t)payload[22] << 8) | payload[23];
        return true;
      }
    }

    i += fieldLen + 1;
  }

  return false;
}

void updateTopBeacon(uint16_t major, uint16_t minor, int8_t rssi) {
  uint32_t now = millis();
  bool updated = false;

  for (int i = 0; i < 3; i++) {
    if (topBeacons[i].valid &&
        topBeacons[i].major == major &&
        topBeacons[i].minor == minor) {

      // Filtro rápido: da mayor peso a la medición nueva.
      // Esto permite volver al modo beacon rápidamente al reingresar.
      float smoothed = (topBeacons[i].rssi * 0.35f) + (rssi * 0.65f);
      topBeacons[i].rssi = (int8_t)lround(smoothed);
      topBeacons[i].seenAt = now;
      updated = true;
      break;
    }
  }

  if (!updated) {
    for (int i = 0; i < 3; i++) {
      if (!topBeacons[i].valid) {
        topBeacons[i].valid = true;
        topBeacons[i].major = major;
        topBeacons[i].minor = minor;
        topBeacons[i].rssi = rssi;
        topBeacons[i].seenAt = now;
        updated = true;
        break;
      }
    }
  }

  if (!updated) {
    int worst = 0;

    for (int i = 1; i < 3; i++) {
      if (topBeacons[i].rssi < topBeacons[worst].rssi) {
        worst = i;
      }
    }

    if (rssi > topBeacons[worst].rssi + 3) {
      topBeacons[worst].valid = true;
      topBeacons[worst].major = major;
      topBeacons[worst].minor = minor;
      topBeacons[worst].rssi = rssi;
      topBeacons[worst].seenAt = now;
    }
  }

  sortTopBeacons();
  updateDisplayPosition();
}

void cleanupOldBeacons() {
  uint32_t now = millis();

  for (int i = 0; i < 3; i++) {
    if (topBeacons[i].valid && (now - topBeacons[i].seenAt > BEACON_TIMEOUT_MS)) {
      topBeacons[i].valid = false;
      topBeacons[i].rssi = -127;
    }
  }
}

void sortTopBeacons() {
  for (int i = 0; i < 2; i++) {
    for (int j = i + 1; j < 3; j++) {
      if (!topBeacons[i].valid && topBeacons[j].valid) {
        BeaconReading tmp = topBeacons[i];
        topBeacons[i] = topBeacons[j];
        topBeacons[j] = tmp;
      } else if (topBeacons[i].valid &&
                 topBeacons[j].valid &&
                 topBeacons[j].rssi > topBeacons[i].rssi) {
        BeaconReading tmp = topBeacons[i];
        topBeacons[i] = topBeacons[j];
        topBeacons[j] = tmp;
      }
    }
  }
}

bool hasRecentBeaconForGpsControl() {
  uint32_t now = millis();

  return topBeacons[0].valid &&
         (now - topBeacons[0].seenAt <= BEACON_SWITCH_RECENT_MS);
}

void setGpsModuleActive(bool active, const char *reason) {
  if (gpsModuleActive == active) return;

  if (active) {
    // Quitar bytes antiguos antes de despertar.
    while (SerialGPS.available()) {
      (void)SerialGPS.read();
    }

    gpsNmeaLine = "";
    gpsNewFixSinceWake = false;
    gpsGgaFixQuality = 0;
    gpsRmcStatus = 'V';

    digitalWrite(Gps_Wakeup_Pin, HIGH);
    gpsModuleActive = true;
    gpsActivatedAt = millis();
    gpsCharsAtActivation = gpsChars;
    gpsRecoveryAttempts = 0;
    gpsWakeRecoveryPending = true;

    SerialMon.print("[POSICION] GPS ENCENDIDO/PENDIENTE RECOVERY | motivo=");
    SerialMon.println(reason);
  } else {
    // WAKEUP en LOW lleva el GNSS a standby.
    digitalWrite(Gps_Wakeup_Pin, LOW);

    gpsModuleActive = false;
    gpsWakeRecoveryPending = false;
    gpsWakeRecoveryRunning = false;
    gpsNewFixSinceWake = false;
    gpsGgaFixQuality = 0;
    gpsRmcStatus = 'V';

    SerialMon.print("[POSICION] GPS APAGADO | usando BEACON | motivo=");
    SerialMon.println(reason);
  }

  gpsPendingModeValid = false;

  // Actualizar el contenido de pantalla inmediatamente.
  // Antes solo se marcaba screenNeedsUpdate y podía seguir mostrando GPS
  // aunque internamente ya se hubiese cambiado a beacon.
  updateDisplayPosition();
  screenNeedsUpdate = true;
}

void updateGpsModeFromBeacons() {
  uint32_t now = millis();

  if (now - lastGpsModeCheck < GPS_MODE_CHECK_MS) return;
  lastGpsModeCheck = now;

  cleanupOldBeacons();
  sortTopBeacons();

  bool beaconRecent = hasRecentBeaconForGpsControl();
  int8_t strongestRssi = beaconRecent ? topBeacons[0].rssi : -127;

  if (now - lastSelectorLog >= SELECTOR_LOG_INTERVAL_MS) {
    lastSelectorLog = now;

    SerialMon.print("[SELECTOR] beacon=");
    SerialMon.print(beaconRecent ? "SI" : "NO");
    SerialMon.print(" rssi=");
    SerialMon.print(strongestRssi);
    SerialMon.print(" gps=");
    SerialMon.print(gpsModuleActive ? "ON" : "OFF");
    SerialMon.print(" umbralOFF=");
    SerialMon.print(GPS_OFF_BEACON_RSSI_DBM);
    SerialMon.print(" umbralON=");
    SerialMon.println(GPS_ON_BEACON_RSSI_DBM);
  }

  bool desiredActive = gpsModuleActive;
  bool definitiveDecision = false;
  const char *reason = "histeresis";

  if (!beaconRecent) {
    desiredActive = true;
    definitiveDecision = true;
    reason = "sin beacon reciente";
  } else if (strongestRssi <= GPS_ON_BEACON_RSSI_DBM) {
    desiredActive = true;
    definitiveDecision = true;
    reason = "beacon debil";
  } else if (strongestRssi >= GPS_OFF_BEACON_RSSI_DBM) {
    desiredActive = false;
    definitiveDecision = true;
    reason = "beacon fuerte";
  }

  // Zona de histéresis: mantener el modo actual.
  if (!definitiveDecision || desiredActive == gpsModuleActive) {
    gpsPendingModeValid = false;
    return;
  }

  if (!gpsPendingModeValid || gpsPendingDesiredActive != desiredActive) {
    gpsPendingModeValid = true;
    gpsPendingDesiredActive = desiredActive;
    gpsPendingSince = now;

    SerialMon.print("[POSICION] Cambio pendiente GPS=");
    SerialMon.print(desiredActive ? "ON" : "OFF");
    SerialMon.print(" RSSI_FILTRADO=");
    SerialMon.print(beaconRecent ? strongestRssi : -127);
    SerialMon.print(" motivo=");
    SerialMon.println(reason);
    return;
  }

  if (now - gpsPendingSince >= GPS_SWITCH_CONFIRM_MS) {
    setGpsModuleActive(desiredActive, reason);
  }
}


/* =========================================================
   LORAWAN LMIC
   ========================================================= */
void setupLoRaWAN() {
  SerialMon.println("[LMIC] Inicializando MCCI LMIC SX1262...");

  pinMode(LoRa_Cs, OUTPUT);
  digitalWrite(LoRa_Cs, HIGH);
  pinMode(LoRa_Rst, OUTPUT);
  pinMode(LoRa_Busy, INPUT);
  pinMode(LoRa_Dio1, INPUT);

  SPI.setPins(LoRa_Miso, LoRa_Sclk, LoRa_Mosi);
  SPI.begin();

  os_init_ex(&lmic_pins);
  LMIC_reset();

#if defined(CFG_us915)
  LMIC_selectSubBand(1);  // US915 SubBand 2: canales 8-15 + 65
  SerialMon.println("[LMIC] US915 SubBand 2 seleccionada");
#endif

  LMIC_setClockError(MAX_CLOCK_ERROR * 5 / 100);
  lmicJoined = false;
  lmicTxPending = false;

  SerialMon.println("[LMIC] Iniciando JOIN OTAA...");
  LMIC_startJoining();
}

bool sendLoRaWANPayloadNow(const uint8_t *data, uint8_t len) {
  if (!lmicJoined) {
    SerialMon.println("[LMIC] TX cancelado: aun no hay EV_JOINED.");
    return false;
  }

  if (LMIC.opmode & OP_TXRXPEND) {
    SerialMon.println("[LMIC] TX pendiente, se omite este ciclo.");
    return false;
  }

  LMIC_setTxData2(LORAWAN_APP_PORT, (xref2u1_t)data, len, 0);
  lmicTxPending = true;

  SerialMon.print("[LMIC] Uplink encolado FPort ");
  SerialMon.print(LORAWAN_APP_PORT);
  SerialMon.print(" bytes=");
  SerialMon.println(len);
  return true;
}

void onEvent(ev_t ev) {
  SerialMon.print(os_getTime());
  SerialMon.print(": ");

  switch (ev) {
    case EV_JOINING:
      SerialMon.println("EV_JOINING");
      requestScreenUpdate("LoRaWAN", "JOINING...", PERSON_NAME);
      break;

    case EV_JOINED:
      SerialMon.println("EV_JOINED");
      lmicJoined = true;
      lmicTxPending = false;
      LMIC_setLinkCheckMode(0);
      requestScreenUpdate("LoRaWAN", "JOINED", PERSON_NAME);
      break;

    case EV_JOIN_FAILED:
      SerialMon.println("EV_JOIN_FAILED");
      lmicJoined = false;
      lmicTxPending = false;
      requestScreenUpdate("LoRaWAN", "JOIN FAILED", PERSON_NAME);
      break;

    case EV_REJOIN_FAILED:
      SerialMon.println("EV_REJOIN_FAILED");
      lmicJoined = false;
      lmicTxPending = false;
      break;

    case EV_TXSTART:
      SerialMon.println("EV_TXSTART");
      break;

    case EV_TXCOMPLETE:
      SerialMon.println("EV_TXCOMPLETE");
      lmicTxPending = false;

      if (LMIC.txrxFlags & TXRX_ACK) {
        SerialMon.println("[LMIC] ACK recibido");
      }

      if (LMIC.dataLen) {
        SerialMon.print("[LMIC] Downlink bytes: ");
        SerialMon.println(LMIC.dataLen);
      }
      break;

    case EV_RESET:
      SerialMon.println("EV_RESET");
      break;

    case EV_RXSTART:
      SerialMon.println("EV_RXSTART");
      break;

    case EV_LINK_DEAD:
      SerialMon.println("EV_LINK_DEAD");
      break;

    case EV_LINK_ALIVE:
      SerialMon.println("EV_LINK_ALIVE");
      break;

    default:
      SerialMon.print("EV_");
      SerialMon.println((unsigned)ev);
      break;
  }
}

/* =========================================================
   PAYLOAD 46 BYTES
   Bytes 0..35  = estructura MinerGuard/Heltec original
   Bytes 36..39 = latitud * 1e6, int32 big-endian
   Bytes 40..43 = longitud * 1e6, int32 big-endian
   Byte 44      = satélites
   Byte 45      = HDOP * 10; 255 = no válido

   HR20 NO ES el byte 19.
   HR20 se obtiene en Node-RED desde el bit GPS 0x10 de flags.
   ========================================================= */
uint8_t encodeRSSI(int8_t rssi) {
  return (uint8_t)(rssi + 127);
}

void writeInt32BE(uint8_t *out, uint8_t offset, int32_t value) {
  out[offset + 0] = (uint8_t)((value >> 24) & 0xFF);
  out[offset + 1] = (uint8_t)((value >> 16) & 0xFF);
  out[offset + 2] = (uint8_t)((value >> 8) & 0xFF);
  out[offset + 3] = (uint8_t)(value & 0xFF);
}

uint8_t getGpsSatellitesPayload() {
  if (!gps.satellites.isValid()) return 0;
  uint32_t sats = gps.satellites.value();
  return (uint8_t)(sats > 255 ? 255 : sats);
}

uint8_t getGpsHdopX10Payload() {
  if (!gps.hdop.isValid()) return 255;

  long value = lround(gps.hdop.hdop() * 10.0);
  if (value < 0) value = 0;
  if (value > 254) value = 254;
  return (uint8_t)value;
}

void buildExtendedPayload(uint8_t *out, uint8_t &sz, bool panic) {
  Bluefruit.Scanner.stop();

  cleanupOldBeacons();
  sortTopBeacons();

  memcpy(snapshotB, topBeacons, sizeof(topBeacons));

  uint8_t flags = 0;

  const bool gpsFixValid = hasFreshGpsFix();

  if (panic) flags |= 0x01;
  if (hrValid) flags |= 0x02;
  if (bandBatValid) flags |= 0x04;
  if (bleConnected) flags |= 0x08;
  if (gpsFixValid) flags |= GPS_FLAG_MASK;
  if (gpsModuleActive) flags |= GPS_ACTIVE_FLAG_MASK;

  out[0] = flags;
  out[1] = hrValid ? hrBpm : 0;
  out[2] = bandBatValid ? bandBatPct : 0;
  out[3] = (uint8_t)(NODE_ID & 0xFF);
  out[4] = (uint8_t)((NODE_ID >> 8) & 0xFF);
  out[5] = bleConnected ? 1 : 0;

  for (int i = 0; i < 3; i++) {
    int base = 6 + (i * 5);

    if (snapshotA[i].valid) {
      out[base + 0] = (uint8_t)((snapshotA[i].major >> 8) & 0xFF);
      out[base + 1] = (uint8_t)(snapshotA[i].major & 0xFF);
      out[base + 2] = (uint8_t)((snapshotA[i].minor >> 8) & 0xFF);
      out[base + 3] = (uint8_t)(snapshotA[i].minor & 0xFF);
      out[base + 4] = encodeRSSI(snapshotA[i].rssi);
    } else {
      memset(&out[base], 0, 5);
    }
  }

  for (int i = 0; i < 3; i++) {
    int base = 21 + (i * 5);

    if (snapshotB[i].valid) {
      out[base + 0] = (uint8_t)((snapshotB[i].major >> 8) & 0xFF);
      out[base + 1] = (uint8_t)(snapshotB[i].major & 0xFF);
      out[base + 2] = (uint8_t)((snapshotB[i].minor >> 8) & 0xFF);
      out[base + 3] = (uint8_t)(snapshotB[i].minor & 0xFF);
      out[base + 4] = encodeRSSI(snapshotB[i].rssi);
    } else {
      memset(&out[base], 0, 5);
    }
  }

  // Mantener intactos los 36 bytes originales.
  // El GPS se agrega al final para no destruir Major/Minor/RSSI de beacon 3.
  int32_t latE6 = 0;
  int32_t lonE6 = 0;

  if (gpsFixValid) {
    latE6 = (int32_t)lround(gps.location.lat() * 1000000.0);
    lonE6 = (int32_t)lround(gps.location.lng() * 1000000.0);
  }

  writeInt32BE(out, GPS_LAT_OFFSET, latE6);
  writeInt32BE(out, GPS_LON_OFFSET, lonE6);
  out[GPS_SATS_OFFSET] = gpsFixValid ? getGpsSatellitesPayload() : 0;
  out[GPS_HDOP_X10_OFFSET] = gpsFixValid ? getGpsHdopX10Payload() : 255;

  SerialMon.print("[PAYLOAD] GPS_ACTIVE=");
  SerialMon.print(gpsModuleActive ? 1 : 0);
  SerialMon.print(" GPS_VALID=");
  SerialMon.print(gpsFixValid ? 1 : 0);
  SerialMon.print(" lat=");
  SerialMon.print(gpsFixValid ? gps.location.lat() : 0.0, 6);
  SerialMon.print(" lon=");
  SerialMon.print(gpsFixValid ? gps.location.lng() : 0.0, 6);
  SerialMon.print(" sats=");
  SerialMon.print(out[GPS_SATS_OFFSET]);
  SerialMon.print(" hdop=");
  if (out[GPS_HDOP_X10_OFFSET] == 255) {
    SerialMon.println("NA");
  } else {
    SerialMon.println(out[GPS_HDOP_X10_OFFSET] / 10.0, 1);
  }

  sz = EXTENDED_PAYLOAD_SIZE;
  lastPeriodicSend = millis();
  snapshotATaken = false;

  Bluefruit.Scanner.start(0);
}

void printPayloadHex(const uint8_t *data, uint8_t len) {
  for (uint8_t i = 0; i < len; i++) {
    if (data[i] < 16) SerialMon.print("0");
    SerialMon.print(data[i], HEX);
    if (i < len - 1) SerialMon.print(" ");
  }
}
