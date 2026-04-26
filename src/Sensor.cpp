#include <Arduino.h>                                          // can be deleted if using Arduino IDE
#include <WiFi.h>
#include <driver/i2s.h>
#if __has_include("config.local.h")
#include "config.local.h"
#endif

#define I2S_MIC_SERIAL_CLOCK GPIO_NUM_32
#define I2S_MIC_LEFT_RIGHT_CLOCK GPIO_NUM_25
#define I2S_MIC_SERIAL_DATA GPIO_NUM_33

#define I2S_PORT I2S_NUM_0

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_SSID"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_PASSWORD"
#endif

#ifndef SERVER_HOST
#define SERVER_HOST "127.0.0.1"     //replace with your server's IP address or hostname
#endif

#ifndef SERVER_PORT
#define SERVER_PORT 8000
#endif

constexpr uint16_t OUTPUT_LEN = 2048;
constexpr uint16_t SAMPLE_BUFFER_SIZE = 512;
constexpr uint16_t SAMPLE_RATE = 16000;

const char* ssid = WIFI_SSID;
const char* pw = WIFI_PASSWORD;
const char* serverHost = SERVER_HOST;
uint16_t port = SERVER_PORT;
WiFiClient client;

constexpr uint32_t WIFI_RECONNECT_ATTEMPT_MS = 10000;
constexpr uint32_t WIFI_RECONNECT_BACKOFF_MS = 10000;

int32_t raw_samples[SAMPLE_BUFFER_SIZE];
uint8_t outputBuffer[OUTPUT_LEN];
uint16_t bufferIndex = 0;

volatile char outputFull  = 0;

i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_RIGHT,
    .communication_format = I2S_COMM_FORMAT_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 4,
    .dma_buf_len = 1024,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0};

i2s_pin_config_t i2s_mic_pins = {
    .bck_io_num = I2S_MIC_SERIAL_CLOCK,
    .ws_io_num = I2S_MIC_LEFT_RIGHT_CLOCK,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_MIC_SERIAL_DATA};

struct __attribute__((packed)) AudioFrameHeader {
    char magic[4];
    uint32_t start_time_us;
    uint16_t payload_len;
    uint16_t checksum;
};

uint16_t computeHeaderChecksum(const char magic[4], uint32_t startTimeUs, uint16_t payloadLen) {
    uint16_t sum = 0;
    for (uint8_t i = 0; i < 4; i++) {
        sum = static_cast<uint16_t>(sum + static_cast<uint8_t>(magic[i]));
    }

    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>(startTimeUs & 0xFF));
    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>((startTimeUs >> 8) & 0xFF));
    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>((startTimeUs >> 16) & 0xFF));
    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>((startTimeUs >> 24) & 0xFF));

    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>(payloadLen & 0xFF));
    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>((payloadLen >> 8) & 0xFF));
    return sum;
}

void i2s_install() {

    esp_err_t install = i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
    if (install != ESP_OK){
        Serial.println("Failed to install I2S driver");
        Serial.printf("i2s_driver_install err: %d\n", install);
    }
}

void i2s_setpin() {

    esp_err_t set_pin = i2s_set_pin(I2S_NUM_0, &i2s_mic_pins);
    if (set_pin != ESP_OK){
        Serial.println("Failed to set I2S pins");
        Serial.printf("i2s_set_pin err: %d\n", set_pin);
    }
}

void reconnectWifiBlocking() {

    client.stop();

    while (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected, attempting reconnect...");

        // One reconnect attempt per retry cycle.
        WiFi.disconnect();
        WiFi.begin(ssid, pw);

        unsigned long attemptStart = millis();
        while (WiFi.status() != WL_CONNECTED && (millis() - attemptStart) < WIFI_RECONNECT_ATTEMPT_MS) {
            delay(250);
        }

        if (WiFi.status() == WL_CONNECTED) {
            break;
        }

        Serial.println("WiFi reconnection failed. Retrying after backoff...");
        delay(WIFI_RECONNECT_BACKOFF_MS);
    }

    Serial.print("WiFi reconnected. IP: ");
    Serial.println(WiFi.localIP());
}

void setup() {

    Serial.begin(115200);
    Serial.println();

    delay(1000);
    
    WiFi.begin(ssid, pw);                                       // Wifi setup
    
    while(WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print('.');
    }
    WiFi.setSleep(false);
    
    Serial.print('\n');
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    Serial.println(WiFi.subnetMask());
    
    while(!client.connect(serverHost, port)) {
        Serial.println("Connection to TCP server failed, retrying...");
        delay(1000);
    }

    i2s_install();
    i2s_setpin();
}

void loop() {

    static unsigned long time = micros();

    // Keep Wi-Fi connected before doing TCP work.
    if (WiFi.status() != WL_CONNECTED) {
        reconnectWifiBlocking();
    }
    else {
        // Check if still connected
        if (!client.connected()) {
            Serial.println("Disconnected from server, reconnecting...");
            while(!client.connect(serverHost, port)) {
                Serial.println("Reconnection failed, retrying...");
                delay(10000);
            }
            Serial.println("Reconnected to server!");
        }

        

        if (!outputFull){

            size_t bytes_read = 0;
            i2s_read(I2S_NUM_0, raw_samples, sizeof(int32_t) * SAMPLE_BUFFER_SIZE, &bytes_read, portMAX_DELAY);
            int samples_read = bytes_read / sizeof(int32_t);
            // dump the samples out to the serial channel.
            for (int i = 0; i < 20; i++)
            {
                Serial.printf("%ld ", raw_samples[i]);
            }
            Serial.println();
            
            for (int16_t i = 0; i < samples_read; i++) {
                if (bufferIndex > OUTPUT_LEN - 4) {
                    outputFull = 1;
                    break;
                }

                // load into buffer as small-endian
                int32_t sample = raw_samples[i];
                outputBuffer[bufferIndex] = sample & 0xFF;               // lower byte
                outputBuffer[bufferIndex + 1] = (sample >> 8) & 0xFF;    // lower middle byte
                outputBuffer[bufferIndex + 2] = (sample >> 16) & 0xFF;   // middle byte
                outputBuffer[bufferIndex + 3] = (sample >> 24) & 0xFF;   // upper byte

                bufferIndex += 4;
            }
                
        }
        
        if (outputFull){
            
            unsigned long oldTime = time;
            outputFull = 0;                                               // start audio sampling before 
            time = micros();                                              // time intensive tasks

            AudioFrameHeader header = {
                {'A', 'U', 'D', '0'},
                static_cast<uint32_t>(oldTime),
                bufferIndex,
                0
            };
            header.checksum = computeHeaderChecksum(header.magic, header.start_time_us, header.payload_len);

            // Send a fixed-size binary frame header followed by the exact payload length.
            client.write(reinterpret_cast<const uint8_t*>(&header), sizeof(header));
            client.write(outputBuffer, bufferIndex);

            bufferIndex = 0;
            outputFull = 0;
        }
    }
}