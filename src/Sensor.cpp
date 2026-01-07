#include <Arduino.h>                                          // can be deleted if using Arduino IDE
#include <Wifi.h>

constexpr uint16_t SOUNDPIN = 36;
constexpr uint16_t SAMPLES = 1024;
constexpr uint16_t SAMPLE_FREQUENCY = 1000;                   // sample frequency can't be very high due to analogRead limitations
constexpr uint32_t ALARM_VALUE = 1000000 / SAMPLE_FREQUENCY;  // in microseconds

const char* ssid = "ssid";                                    // change to your ssid
const char* pw = "pw";                                        // change to your password
const char* serverHost = "192.168.x.x";                       // change to host server IP
uint16_t port = 8000;
WiFiClient client;

uint16_t soundBuffer[SAMPLES];
uint16_t bufferIndex = 0;

hw_timer_t *timer = nullptr;
volatile char bufferFull = 0;

void IRAM_ATTR onTimer() {
    
    if (!bufferFull){
        soundBuffer[bufferIndex] = analogRead(SOUNDPIN);
        bufferIndex++;
    }
    if (bufferIndex == SAMPLES){
        bufferIndex = 0;
        bufferFull = 1; 
    }
}

void setup() {

    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println();

    pinMode(SOUNDPIN, INPUT);
    
    WiFi.begin(ssid, pw);                                       // Wifi setup

    while(WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print('.');
    }
    
    Serial.print('\n');
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());

    WiFiClient client;
    while(!client.connect(serverHost, port)) {
        Serial.println("Connection to TCP server failed, retrying...");
        delay(1000);
    }

    timer = timerBegin(0, 80, true);
    timerAttachInterrupt(timer, &onTimer, true);
    timerAlarmWrite(timer, ALARM_VALUE, true);
    timerAlarmEnable(timer);
}

void loop() {

    static unsigned long time = micros();

    if (bufferFull){

        char localBuffer[SAMPLES * 2];

        for (int i = 0; i < SAMPLES; i++) {
            localBuffer[i * 2] = (soundBuffer[i] >> 8) & 0xFF;        // high byte
            localBuffer[i * 2 + 1] = soundBuffer[i] & 0xFF;           // low byte
        }
        String timeHeader = "Time:" + String(time) +'\n';             // time at start of audio sample

        bufferFull = 0;                                               // start audio sampling before 
        time = micros();                                              // time intensive tasks
        
        String payload = String((const char*)localBuffer, SAMPLES * 2);
        int length = payload.length();
        String LengthHeader = "Length:" + String(length + 1) + '\n';
        
        // send data via TCP
        client.print(timeHeader);
        client.print(LengthHeader);
        client.print(payload);
        
    }

}