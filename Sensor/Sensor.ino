/*This code is designed for an ESP32 

  Serial communication will be encoded as follows:
    Total data sent will be two bytes per send. 
    First byte is PIR data, second is sound data
    F is no movement detected, and T is movement detected
    F is no sound detected, and T is sound detected.  */


#include "BluetoothSerial.h"

constexpr int PIRpin = 23;
constexpr int soundPin = 5;
String deviceName = "Petah";

// Check if Bluetooth is available
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
#endif

// Check Serial Port Profile
#if !defined(CONFIG_BT_SPP_ENABLED)
#error Serial Port Profile for Bluetooth is not available or not enabled. It is only available for the ESP32 chip.
#endif

BluetoothSerial SerialBT;
const char* pw = "9572";

void setup() {
  Serial.begin(115200);
  SerialBT.begin(deviceName);  //Bluetooth device name
  pinMode(PIRpin, INPUT);
  pinMode(soundPin, INPUT);
  //SerialBT.deleteAllBondedDevices(); //delete paired devices
  //SerialBT.setPin(pw, 4);
  Serial.printf("The device with name \"%s\" is started.\nNow you can pair it with Bluetooth!\n", deviceName.c_str());
}

void loop() {
  static unsigned long time0 = millis();
  static int8_t soundIsOn = 0;
  unsigned long time1 = millis();
  static uint8_t PIRState = LOW;
  uint8_t PIRValue, soundValue;
  uint8_t outputPIR = 0;
  uint8_t outputSound = 0;

  // send sensor data every second
  if (time1 - time0 > 1000){
    PIRValue = digitalRead(PIRpin);
    soundValue = digitalRead(soundPin);

    if (PIRValue != PIRState){
      outputPIR = 'T';
      PIRState = PIRValue;
    }
    else {
      outputPIR = 'F';
      PIRState = PIRValue;
    }

    if (soundValue == HIGH) {
      outputSound = 'T';
    }
    else {
      outputSound = 'F';
    }

    uint8_t data[] = {outputPIR, outputSound, '\n'};
    SerialBT.write(data, sizeof(data));

    time0 = time1;
  }

}
