/*This code is designed for an ESP32 

  Serial communication will be encoded as follows:
    Total data sent will be one byte per send. 
    'X' is irrelevant data. 
    The four most significant bits will be IR sensor data, with 0xFX being motion detected, and 0x0X being no motion detected.
    The four least significant bits will be sound sensor data, with 0xXF being sound above a threshold detected, and 0xX0 being sound below the threshold.  */



#include "BluetoothSerial.h"

constexpr int PIRpin = 23;
String device_name = "Petah";

// Check if Bluetooth is available
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Bluetooth is not enabled! Please run `make menuconfig` to and enable it
#endif

// Check Serial Port Profile
#if !defined(CONFIG_BT_SPP_ENABLED)
#error Serial Port Profile for Bluetooth is not available or not enabled. It is only available for the ESP32 chip.
#endif

BluetoothSerial SerialBT;

void setup() {
  Serial.begin(115200);
  SerialBT.begin(device_name);  //Bluetooth device name
  pinMode(PIRpin, INPUT);
  //SerialBT.deleteAllBondedDevices(); //delete paired devices
  Serial.printf("The device with name \"%s\" is started.\nNow you can pair it with Bluetooth!\n", device_name.c_str());
}

void loop() {
  static unsigned long time0 = millis();
  unsigned long time1 = millis();
  static unsigned char PIRState = LOW;
  unsigned char PIRValue;
  unsigned char output = 0;

  // send sensor data every second
  if (time1 - time0 > 1000){
    PIRValue = digitalRead(PIRpin);

    if (PIRValue != PIRState){
      output |= 0xF0;
      PIRState = PIRValue;
    }
    else {
      output &= 0x0F;
      PIRState = PIRValue;
    }

    // here would go the logic for dealing with noise
    // output |= 0x0F; or output &= 0xF0;

    SerialBT.write(output);
    time0 = time1;
  }

}
