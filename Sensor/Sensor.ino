#include <WiFi.h>
#include <HTTPClient.h>

constexpr int PIRpin = 23;
constexpr int soundPin = 5;

const char* ssid = "xxxxx";                                   // change to your ssid
const char* pw = "xxxxx";                                     // change to your password

IPAddress serverIP = IPAddress(192, 168, xxx, xxx);           // change to host server ip
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

    WiFiClient client;

    uint8_t PIRValue, soundValue;
    char* outputPIR;
    char* outputSound;
    
    PIRValue = digitalRead(PIRpin);
    soundValue = digitalRead(soundPin);

    if (PIRValue != PIRState){
      outputPIR = "T";
      PIRState = PIRValue;
    }
    else {
      outputPIR = "F";
      PIRState = PIRValue;
    }

    if (soundValue == HIGH) {
      outputSound = "T";
    }
    else {
      outputSound = "F";
    }

    char output[25];
    strcpy(output, "{\"Movement\":");
    strcat(output, outputPIR);
    strcat(output, ", \"Sound\":");
    strcat(output, outputSound);
    strcat(output, "}");
    
    Serial.println(output);

    if (client.connect(serverIP, port)){                      //connect and send http request
      client.println("POST / HTTP/1.1");
      client.println("Host: 192.168.xxx.xxx");
      client.println("Content-type: application/json");
      client.println("Content-length: 25");
      client.println("Connection: close");
      client.println();
      client.println(output);

      Serial.println("Data Sent");
      client.stop();
    } 
    else {
      Serial.print("Failed to connect to server: ");
      Serial.printf("time0: %lu, time1: %lu\n", time0, time1);
    }

    time0 = time1;
  }

}