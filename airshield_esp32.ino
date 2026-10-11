/*
 AirShield AI - ESP32 + Plantower-compatible PM sensor starter firmware.
 IMPORTANT:
 - Verify sensor model, pinout, voltage, UART baud rate and packet format in its datasheet.
 - Never commit real Wi-Fi credentials or device tokens to a public repository.
 - This sketch assumes a Plantower-compatible 32-byte frame on Serial2.
*/

#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID = "CHANGE_ME";
const char* WIFI_PASSWORD = "CHANGE_ME";
const char* API_URL = "https://YOUR-APP-HOST/api/readings";
const char* DEVICE_TOKEN = "CHANGE_ME"; // Must match server DEVICE_TOKEN, if configured.

static const int SENSOR_RX_PIN = 16; // ESP32 RX <- sensor TX
static const int SENSOR_TX_PIN = 17; // ESP32 TX -> sensor RX (often not needed)
static const uint32_t SENSOR_BAUD = 9600;
HardwareSerial pmSerial(2);

unsigned long lastPost = 0;
const unsigned long POST_INTERVAL_MS = 10000;

bool readPlantower(uint16_t &pm25) {
  static uint8_t frame[32];
  while (pmSerial.available() >= 32) {
    if (pmSerial.peek() != 0x42) {
      pmSerial.read();
      continue;
    }
    size_t n = pmSerial.readBytes(frame, 32);
    if (n != 32 || frame[0] != 0x42 || frame[1] != 0x4D) continue;
    uint16_t frameLen = (uint16_t(frame[2]) << 8) | frame[3];
    if (frameLen < 28) continue;
    uint16_t sum = 0;
    for (int i = 0; i < 30; i++) sum += frame[i];
    uint16_t expected = (uint16_t(frame[30]) << 8) | frame[31];
    if (sum != expected) continue;

    // Plantower common frame: atmospheric/environmental PM2.5 at bytes 12-13.
    // Confirm byte definitions for your exact sensor firmware/model.
    pm25 = (uint16_t(frame[12]) << 8) | frame[13];
    return true;
  }
  return false;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(WiFi.status() == WL_CONNECTED ? "\nWi-Fi connected" : "\nWi-Fi not connected; will retry");
}

void postReading(float pm25) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return;
  }
  HTTPClient http;
  http.begin(API_URL);
  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_TOKEN) > 0 && strcmp(DEVICE_TOKEN, "CHANGE_ME") != 0) {
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
  }
  String body = "{\"device_id\":\"indoor_01\",\"pm25_ugm3\":" + String(pm25, 1) +
                ",\"source_type\":\"sensor\",\"quality_flag\":\"valid\",\"intervention\":\"baseline\"}";
  int status = http.POST(body);
  Serial.printf("POST status: %d\n", status);
  if (status > 0) Serial.println(http.getString());
  http.end();
}

void setup() {
  Serial.begin(115200);
  pmSerial.begin(SENSOR_BAUD, SERIAL_8N1, SENSOR_RX_PIN, SENSOR_TX_PIN);
  connectWiFi();
}

void loop() {
  uint16_t pm25 = 0;
  if (readPlantower(pm25)) {
    Serial.printf("PM2.5: %u ug/m3\n", pm25);
    if (millis() - lastPost >= POST_INTERVAL_MS) {
      postReading((float)pm25);
      lastPost = millis();
    }
  }
  delay(20);
}
