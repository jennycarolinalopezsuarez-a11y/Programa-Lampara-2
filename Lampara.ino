#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>

// ===================== PINES =====================
// XIAO ESP32-C6
// D9  = GPIO20 -> lámpara normal
// D10 = GPIO18 -> incendio
// D7  -> sismico
// D8  -> homaq

static const int LED_ONBOARD    = 15;   // activo LOW típico
static const int NORM_LED_PIN   = D9;   // GPIO20
static const int FIRE_LED_PIN   = D10;  // GPIO18
static const int SISMIC_LED_PIN = D7;   // NUEVA salida
static const int HOMAQ_LED_PIN  = D8;   // NUEVA salida

static const int IN0_PIN = 0;           // HIGH = normal 60%
static const int IN1_PIN = 1;           // HIGH = normal 100%

// ===================== BLE ALERTA =====================
static const char* TARGET_NAME = "MindWare-ALERT";
static const uint32_t TRIGGER_COOLDOWN_MS = 1000;

BLEScan* pBLEScan = nullptr;
bool scanRunning = false;

uint32_t lastTriggerMs = 0;
volatile bool triggerRequested = false;
volatile uint16_t pendingMajor = 0;
volatile uint16_t pendingMinor = 0;

// ===================== BLE DIAGNOSTICO =====================
#define DIAG_DEVICE_NAME "MinerGuard-DIAG"
#define SERVICE_UUID     "12345678-1234-1234-1234-1234567890ab"
#define CHAR_STATUS_UUID "12345678-1234-1234-1234-1234567890ac"
#define CHAR_CMD_UUID    "12345678-1234-1234-1234-1234567890ad"

BLECharacteristic* statusChar = nullptr;

// ===================== PWM =====================
static const uint32_t PWM_FREQ = 5000;
static const uint8_t  PWM_RES  = 8;     // 0..255

static const uint8_t DUTY_60  = 180; // 60%
static const uint8_t DUTY_100 = 255; // 100%

// ===================== ESTADOS =====================
enum SystemMode {
  SYS_STANDBY,
  SYS_NORMAL,
  SYS_ALERT
};

SystemMode sysMode = SYS_STANDBY;

// ===================== ALERTAS =====================
enum AlertType {
  ALERT_NONE,
  ALERT_FIRE_100,
  ALERT_SISMIC_200,
  ALERT_HOMAQ_300
};

AlertType currentAlert = ALERT_NONE;

enum AlertState {
  AST_IDLE,

  // major 100 incendio
  AST_FIRE_LONG_ON,
  AST_FIRE_LONG_OFF,
  AST_FIRE_SHORT_ON,
  AST_FIRE_SHORT_OFF,

  // major 200 / 300
  AST_GENERIC_ON,
  AST_GENERIC_OFF,

  // gap entre repetición 1 y 2
  AST_REPEAT_GAP
};

AlertState alertState = AST_IDLE;
uint32_t stateStartMs = 0;
uint32_t genericTotalMs = 0;

uint8_t longCount = 0;     // cantidad de apagados largos completados
uint8_t shortCount = 0;
uint8_t shortTarget = 0;

// repetir rutina completa 2 veces
uint8_t alertRepeatCount = 0;
static const uint8_t ALERT_REPEAT_TARGET = 2;

// separación entre repetición 1 y 2
static const uint32_t ALERT_REPEAT_GAP_MS = 4000;

// ===================== UTIL =====================
static inline void onboardLed(bool on) {
  digitalWrite(LED_ONBOARD, on ? LOW : HIGH);
}

static inline bool in0Active() {
  return digitalRead(IN0_PIN) == HIGH;
}

static inline bool in1Active() {
  return digitalRead(IN1_PIN) == HIGH;
}

static inline bool wakeInputsActive() {
  return in0Active() || in1Active();
}

static String getResetReasonString() {
  esp_reset_reason_t reason = esp_reset_reason();
  switch (reason) {
    case ESP_RST_UNKNOWN:   return "UNKNOWN";
    case ESP_RST_POWERON:   return "POWERON";
    case ESP_RST_EXT:       return "EXT";
    case ESP_RST_SW:        return "SW";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WDT";
    case ESP_RST_TASK_WDT:  return "TASK_WDT";
    case ESP_RST_WDT:       return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_SDIO:      return "SDIO";
    default:                return "OTHER";
  }
}

/*
// ======== BATERIA (comentado hasta tener la placa nueva) ========
static const int VBAT_PIN = 2;

static float readBatteryVoltage() {
  int raw = analogRead(VBAT_PIN);
  // divisor 100k / 100k -> multiplicar por 2
  return ((float)raw / 4095.0f) * 3.3f * 2.0f;
}
*/

// ===================== BLE DIAGNOSTICO =====================
static void sendStatus() {
  String status = "{";
  status += "\"mode\":\"";
  if (sysMode == SYS_STANDBY) status += "STANDBY";
  else if (sysMode == SYS_NORMAL) status += "NORMAL";
  else status += "ALERT";
  status += "\",";
  status += "\"in0\":" + String(in0Active() ? 1 : 0) + ",";
  status += "\"in1\":" + String(in1Active() ? 1 : 0) + ",";
  status += "\"scan\":" + String(scanRunning ? 1 : 0) + ",";
  status += "\"alert\":\"";
  if (currentAlert == ALERT_NONE) status += "NONE";
  else if (currentAlert == ALERT_FIRE_100) status += "FIRE_100";
  else if (currentAlert == ALERT_SISMIC_200) status += "SISMIC_200";
  else if (currentAlert == ALERT_HOMAQ_300) status += "HOMAQ_300";
  status += "\",";
  status += "\"reset\":\"" + getResetReasonString() + "\"";
  status += "\"}";

  if (statusChar) {
    statusChar->setValue(status.c_str());
    statusChar->notify();
  }

  Serial.println("STATUS -> " + status);
}

class CmdCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *pCharacteristic) override {
    String cmd = pCharacteristic->getValue().c_str();
    cmd.trim();
    cmd.toLowerCase();

    Serial.println("CMD BLE: " + cmd);

    if (cmd == "status") {
      sendStatus();
    } else if (cmd == "reset") {
      Serial.println(">>> RESET POR BLE");
      delay(200);
      ESP.restart();
    } else if (cmd == "test") {
      Serial.println(">>> TEST SALIDAS");

      ledcWrite(NORM_LED_PIN, DUTY_60);
      delay(300);
      ledcWrite(NORM_LED_PIN, 0);

      ledcWrite(FIRE_LED_PIN, DUTY_100);
      delay(300);
      ledcWrite(FIRE_LED_PIN, 0);

      ledcWrite(SISMIC_LED_PIN, DUTY_100);
      delay(300);
      ledcWrite(SISMIC_LED_PIN, 0);

      ledcWrite(HOMAQ_LED_PIN, DUTY_100);
      delay(300);
      ledcWrite(HOMAQ_LED_PIN, 0);
    }
  }
};

// ===================== BLE SCAN =====================
static void startScan() {
  if (!scanRunning) {
    pBLEScan->start(0, nullptr, false);
    scanRunning = true;
    Serial.println("BLE scan ON");
  }
}

static void stopScan() {
  if (scanRunning) {
    pBLEScan->stop();
    scanRunning = false;
    Serial.println("BLE scan OFF");
  }
}

// ===================== SALIDAS =====================
static void allAlertOutputsOff() {
  ledcWrite(FIRE_LED_PIN, 0);
  ledcWrite(SISMIC_LED_PIN, 0);
  ledcWrite(HOMAQ_LED_PIN, 0);
}

static void setStandbyOutputs() {
  ledcWrite(NORM_LED_PIN, 0);
  allAlertOutputsOff();
  onboardLed(false);
}

static void setNormalOutputs() {
  // En modo normal solo D9 / GPIO20
  allAlertOutputsOff();

  if (in1Active()) {
    ledcWrite(NORM_LED_PIN, DUTY_100);
  } else if (in0Active()) {
    ledcWrite(NORM_LED_PIN, DUTY_60);
  } else {
    ledcWrite(NORM_LED_PIN, 0);
  }

  onboardLed(false);
}

static void setCurrentAlertOutput(bool on) {
  ledcWrite(NORM_LED_PIN, 0);
  allAlertOutputsOff();

  int duty = on ? DUTY_100 : 0;

  if (currentAlert == ALERT_FIRE_100) {
    ledcWrite(FIRE_LED_PIN, duty);
  } else if (currentAlert == ALERT_SISMIC_200) {
    ledcWrite(SISMIC_LED_PIN, duty);
  } else if (currentAlert == ALERT_HOMAQ_300) {
    ledcWrite(HOMAQ_LED_PIN, duty);
  }

  onboardLed(on);
}

// ===================== MODO SISTEMA =====================
static void enterStandby() {
  sysMode = SYS_STANDBY;
  currentAlert = ALERT_NONE;
  alertState = AST_IDLE;
  setStandbyOutputs();
  stopScan();
  Serial.println(">>> STANDBY");
}

static void enterNormal() {
  sysMode = SYS_NORMAL;
  currentAlert = ALERT_NONE;
  alertState = AST_IDLE;
  setNormalOutputs();
  startScan();
  Serial.println(">>> NORMAL");
}

// ===================== ALERTAS =====================
static void restartCurrentAlertCycle() {
  stateStartMs = millis();
  longCount = 0;
  shortCount = 0;
  genericTotalMs = millis();

  if (currentAlert == ALERT_FIRE_100) {
    alertState = AST_FIRE_LONG_ON;
    setCurrentAlertOutput(true);
  } else if (currentAlert == ALERT_SISMIC_200 || currentAlert == ALERT_HOMAQ_300) {
    alertState = AST_GENERIC_ON;
    setCurrentAlertOutput(true);
  }
}

static void finishAlert() {
  alertRepeatCount++;

  if (alertRepeatCount < ALERT_REPEAT_TARGET) {
    Serial.printf(">>> PAUSA ENTRE CICLOS %u/%u\n", alertRepeatCount, ALERT_REPEAT_TARGET);
    alertState = AST_REPEAT_GAP;
    stateStartMs = millis();
    setCurrentAlertOutput(false);
    return;
  }

  Serial.println(">>> ALERTA FINALIZADA");
  currentAlert = ALERT_NONE;
  alertState = AST_IDLE;
  sysMode = SYS_NORMAL;
  alertRepeatCount = 0;
  setNormalOutputs();
  lastTriggerMs = 0;
}

static void startAlert(uint16_t major, uint16_t minor) {
  sysMode = SYS_ALERT;
  pendingMajor = major;
  pendingMinor = minor;
  stateStartMs = millis();
  genericTotalMs = millis();
  alertRepeatCount = 0;
  longCount = 0;
  shortCount = 0;
  shortTarget = 0;

  if (major == 100 && minor >= 1 && minor <= 9) {
    currentAlert = ALERT_FIRE_100;
    shortTarget = (uint8_t)minor;
    alertState = AST_FIRE_LONG_ON;
    setCurrentAlertOutput(true);
    Serial.printf(">>> ALERTA INCENDIO 100 / minor=%u\n", minor);
    return;
  }

  if (major == 200 && minor == 10) {
    currentAlert = ALERT_SISMIC_200;
    alertState = AST_GENERIC_ON;
    setCurrentAlertOutput(true);
    Serial.println(">>> ALERTA SISMICO 200 / minor=10");
    return;
  }

  if (major == 300 && minor == 20) {
    currentAlert = ALERT_HOMAQ_300;
    alertState = AST_GENERIC_ON;
    setCurrentAlertOutput(true);
    Serial.println(">>> ALERTA HOMAQ 300 / minor=20");
    return;
  }

  Serial.printf("Alerta ignorada major=%u minor=%u\n", major, minor);
  currentAlert = ALERT_NONE;
  sysMode = SYS_NORMAL;
  setNormalOutputs();
}

static void updateAlert() {
  if (sysMode != SYS_ALERT) return;

  uint32_t now = millis();

  switch (alertState) {
    case AST_FIRE_LONG_ON:
      if (now - stateStartMs >= 1600) {
        setCurrentAlertOutput(false);
        alertState = AST_FIRE_LONG_OFF;
        stateStartMs = now;
      }
      break;

    case AST_FIRE_LONG_OFF: {
      // off 1 y off 2 = 1.6s
      // off 3 = 2.5s
      uint32_t fireOffDuration = (longCount >= 2) ? 2500 : 1600;

      if (now - stateStartMs >= fireOffDuration) {
        longCount++;

        if (longCount >= 3) {
          // terminó el tercer apagado largo, ahora vienen los pulsos cortos
          if (shortTarget == 0) {
            finishAlert();
          } else {
            alertState = AST_FIRE_SHORT_ON;
            stateStartMs = now;
            shortCount = 0;
            setCurrentAlertOutput(true);
          }
        } else {
          alertState = AST_FIRE_LONG_ON;
          stateStartMs = now;
          setCurrentAlertOutput(true);
        }
      }
      break;
    }

    case AST_FIRE_SHORT_ON:
      if (now - stateStartMs >= 700) {
        setCurrentAlertOutput(false);
        alertState = AST_FIRE_SHORT_OFF;
        stateStartMs = now;
      }
      break;

    case AST_FIRE_SHORT_OFF:
      if (now - stateStartMs >= 700) {
        shortCount++;
        if (shortCount >= shortTarget) {
          // terminó el ciclo incendio, ahora entra la pausa de 4s antes del siguiente ciclo
          finishAlert();
        } else {
          alertState = AST_FIRE_SHORT_ON;
          stateStartMs = now;
          setCurrentAlertOutput(true);
        }
      }
      break;

    case AST_GENERIC_ON:
      if (currentAlert == ALERT_SISMIC_200) {
        if (now - genericTotalMs >= 10000) {
          finishAlert();
        } else if (now - stateStartMs >= 1000) {
          setCurrentAlertOutput(false);
          alertState = AST_GENERIC_OFF;
          stateStartMs = now;
        }
      } else if (currentAlert == ALERT_HOMAQ_300) {
        if (now - genericTotalMs >= 10000) {
          finishAlert();
        } else if (now - stateStartMs >= 500) {
          setCurrentAlertOutput(false);
          alertState = AST_GENERIC_OFF;
          stateStartMs = now;
        }
      }
      break;

    case AST_GENERIC_OFF:
      if (currentAlert == ALERT_SISMIC_200) {
        if (now - genericTotalMs >= 10000) {
          finishAlert();
        } else if (now - stateStartMs >= 1000) {
          setCurrentAlertOutput(true);
          alertState = AST_GENERIC_ON;
          stateStartMs = now;
        }
      } else if (currentAlert == ALERT_HOMAQ_300) {
        if (now - genericTotalMs >= 10000) {
          finishAlert();
        } else if (now - stateStartMs >= 500) {
          setCurrentAlertOutput(true);
          alertState = AST_GENERIC_ON;
          stateStartMs = now;
        }
      }
      break;

    case AST_REPEAT_GAP:
      if (now - stateStartMs >= ALERT_REPEAT_GAP_MS) {
        Serial.println(">>> INICIO SIGUIENTE CICLO");
        restartCurrentAlertCycle();
      }
      break;

    case AST_IDLE:
    default:
      break;
  }
}

// ===================== CALLBACK BLE ALERTA =====================
class AlertCB : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice dev) override {
    if (sysMode == SYS_STANDBY || sysMode == SYS_ALERT) return;

    uint32_t now = millis();
    if (lastTriggerMs != 0 && (now - lastTriggerMs < TRIGGER_COOLDOWN_MS)) return;

    if (!dev.haveName()) return;
    String name = dev.getName().c_str();
    if (name != String(TARGET_NAME)) return;

    if (!dev.haveManufacturerData()) return;

    String mfg = dev.getManufacturerData();
    if (mfg.length() < 25) return;

    const uint8_t* raw = (const uint8_t*)mfg.c_str();

    // iBeacon Apple
    if (!(raw[0] == 0x4C && raw[1] == 0x00 && raw[2] == 0x02 && raw[3] == 0x15)) {
      return;
    }

    uint16_t major = ((uint16_t)raw[20] << 8) | raw[21];
    uint16_t minor = ((uint16_t)raw[22] << 8) | raw[23];

    bool valid =
      (major == 100 && minor >= 1 && minor <= 9) ||
      (major == 200 && minor == 10) ||
      (major == 300 && minor == 20);

    if (!valid) return;

    lastTriggerMs = now;
    pendingMajor = major;
    pendingMinor = minor;
    triggerRequested = true;

    Serial.printf("MATCH %s RSSI=%d major=%u minor=%u\n",
                  name.c_str(), dev.getRSSI(), major, minor);
  }
};

// ===================== SETUP =====================
void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println("XIAO ESP32-C6 - lampara normal + alertas + BLE diag");
  Serial.println("Entradas activas en HIGH");
  Serial.println("D9(GPIO20)=normal | D10(GPIO18)=incendio | D7=sismico | D8=homaq");

  pinMode(LED_ONBOARD, OUTPUT);
  pinMode(IN0_PIN, INPUT);
  pinMode(IN1_PIN, INPUT);

  ledcAttach(NORM_LED_PIN,   PWM_FREQ, PWM_RES);
  ledcAttach(FIRE_LED_PIN,   PWM_FREQ, PWM_RES);
  ledcAttach(SISMIC_LED_PIN, PWM_FREQ, PWM_RES);
  ledcAttach(HOMAQ_LED_PIN,  PWM_FREQ, PWM_RES);

  setStandbyOutputs();

  BLEDevice::init(DIAG_DEVICE_NAME);

  // Scan de alertas
  pBLEScan = BLEDevice::getScan();
  pBLEScan->setAdvertisedDeviceCallbacks(new AlertCB(), false);
  pBLEScan->setActiveScan(true);
  pBLEScan->setInterval(30);
  pBLEScan->setWindow(30);

  // Servicio BLE de diagnóstico
  BLEServer *server = BLEDevice::createServer();
  BLEService *svc = server->createService(SERVICE_UUID);

  statusChar = svc->createCharacteristic(
    CHAR_STATUS_UUID,
    BLECharacteristic::PROPERTY_NOTIFY
  );

  BLECharacteristic *cmdChar = svc->createCharacteristic(
    CHAR_CMD_UUID,
    BLECharacteristic::PROPERTY_WRITE
  );

  cmdChar->setCallbacks(new CmdCallback());

  svc->start();
  BLEDevice::getAdvertising()->start();

  if (wakeInputsActive()) {
    enterNormal();
  } else {
    enterStandby();
  }

  sendStatus();
}

// ===================== LOOP =====================
void loop() {
  // Si no está en alerta, mantener estado normal/standby
  if (sysMode != SYS_ALERT) {
    if (wakeInputsActive()) {
      if (sysMode == SYS_STANDBY) {
        enterNormal();
      } else {
        setNormalOutputs();
      }
    } else {
      if (sysMode != SYS_STANDBY) {
        enterStandby();
      }
    }
  }

  // Lanzar alerta
  if (triggerRequested && sysMode == SYS_NORMAL) {
    triggerRequested = false;
    startAlert(pendingMajor, pendingMinor);
  }

  // Actualizar alerta
  updateAlert();

  delay(1);
}