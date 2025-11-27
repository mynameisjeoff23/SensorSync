#include <WiFi.h>

constexpr int PIRpin = 23;
constexpr int soundPin = 5;

const char* ssid = "ssid";                                   // change to your ssid
const char* pw = "pw";                                     // change to your password

const char* serverHost = "192.168.x.x";                     // change to host server IP
uint16_t port = 8000;

void setup() {

  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  pinMode(PIRpin, INPUT);
  pinMode(soundPin, INPUT);
  
  WiFi.begin(ssid, pw);                                       // Wifi setup

  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print('.');
  }
  
  Serial.print('\n');
  Serial.print("WiFi connected. IP: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  static unsigned long time0 = millis();
  unsigned long time1 = millis();
  static uint8_t PIRState = LOW;

 
  if (time1 - time0 > 1000){                                  // send sensor data every second

    uint8_t PIRValue, soundValue;
    char outputPIR;
    char outputSound;
    
    PIRValue = digitalRead(PIRpin);
    soundValue = digitalRead(soundPin);

    if (PIRValue != PIRState) {
      outputPIR = 'T';
      PIRState = PIRValue;
    } else {
      outputPIR = 'F';
    }

    if (soundValue == HIGH) {
      outputSound = 'T';
    } else {
      outputSound = 'F';
    }

    String payload = "{\"Movement\":";
    payload = payload + outputPIR + ", \"Sound\":" + outputSound + "}";
    
    Serial.println(payload);

    WiFiClient client;
    if (client.connect(serverHost, port)) {
      client.println(payload);
      Serial.println("Sent via TCP");
      client.stop();
    } else {
      Serial.println("Failed to connect to TCP server");
    }

    time0 = time1;
  }

}