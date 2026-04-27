# SensorSync
Project that uses a microcontroller to send sensor data to a locals server, which will then be used to process the sensor data.

## TCP Audio Protocol

SensorSync streams audio frames from the microcontroller to the Python server over TCP.

### Header (16 bytes, little-endian)

Each frame starts with this fixed-size header:

```text
magic            4 bytes   ASCII "AUD0"
start_time_us    4 bytes   uint32
packet_serial    4 bytes   uint32
payload_len      2 bytes   uint16
header_checksum  2 bytes   uint16
```

Python struct format:

```python
"<4sIIHH"
```

### Payload

- Variable length binary block of audio samples.
- Samples are little-endian `int32` values.
- `payload_len` must be in the interval `[0, 4096]`.
- `payload_len` must be divisible by 4.

### Header Checksum

`header_checksum` is the 16-bit sum of all bytes in the header fields before checksum:

- `magic` (4 bytes)
- `start_time_us` (4 bytes, little-endian bytes)
- `packet_serial` (4 bytes, little-endian bytes)
- `payload_len` (2 bytes, little-endian bytes)

Formula:

```text
checksum = (sum(header_without_checksum_bytes) & 0xFFFF)
```

### Receiver Validation Order

The server validates each frame in this order:

1. `magic == b"AUD0"`
2. `0 <= payload_len <= 4096`
3. `payload_len % 4 == 0`
4. `header_checksum` matches computed checksum
5. Read exactly `payload_len` bytes and decode as little-endian `int32`
