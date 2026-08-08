import socket
import struct
import time
import logging
import numpy as np

try:
    import pyaudio
except ImportError:
    print("ERROR: pyaudio not installed. Install it with: pip install pyaudio")
    exit(1)

logger = logging.getLogger(__name__)

# Configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024  # samples per chunk (matches SAMPLE_BUFFER_SIZE on ESP32)
AUDIO_DEVICE_INDEX = None  # None = default device

# Protocol constants
HEADER_FORMAT = "<4sIIHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAGIC = b"AUD0"
MAX_PAYLOAD_LEN = 4096
UINT32_MASK = 0xFFFFFFFF


def get_monotonic_time_us() -> int:
    """Return a microsecond timestamp truncated to uint32, like the ESP32 micros() value."""
    return int(time.monotonic_ns() // 1000) & UINT32_MASK


def compute_header_checksum(magic, start_time_us, packet_serial, payload_len):
    """Compute checksum matching ESP32 implementation."""
    sum_val = 0

    # Coerce inputs to plain Python ints to avoid numpy scalar surprises
    start_time_us = int(start_time_us) & UINT32_MASK
    packet_serial = int(packet_serial) & UINT32_MASK
    payload_len = int(payload_len) & 0xFFFF

    # Add magic bytes
    for byte in magic:
        sum_val = (sum_val + int(byte)) & 0xFFFF

    # Add start_time_us bytes (little-endian)
    for i in range(4):
        sum_val = (sum_val + ((start_time_us >> (i * 8)) & 0xFF)) & 0xFFFF

    # Add packet_serial bytes (little-endian)
    for i in range(4):
        sum_val = (sum_val + ((packet_serial >> (i * 8)) & 0xFF)) & 0xFFFF

    # Add payload_len bytes (little-endian)
    for i in range(2):
        sum_val = (sum_val + ((payload_len >> (i * 8)) & 0xFF)) & 0xFFFF

    return int(sum_val & 0xFFFF)


def capture_and_send_audio():
    """Capture audio from microphone and send to server in ESP32 format."""
    
    # Initialize PyAudio
    pa = pyaudio.PyAudio()
    
    # List available devices if needed
    logger.info("Available audio devices:")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        logger.info(f"  Device {i}: {info['name']} (channels: {info['maxInputChannels']})")
    
    # Open audio stream. Prefer 24-bit input if available so we can pack into
    # 32-bit little-endian containers with proper sign-extension.
    stream_format = None
    try:
        # Try 24-bit first
        stream = pa.open(
            format=pyaudio.paInt24,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            input_device_index=AUDIO_DEVICE_INDEX
        )
        stream_format = 'int24'
    except Exception:
        try:
            # Fallback to 32-bit
            stream = pa.open(
                format=pyaudio.paInt32,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
                input_device_index=AUDIO_DEVICE_INDEX
            )
            stream_format = 'int32'
        except Exception as e:
            logger.error(f"Failed to open audio stream: {e}")
            pa.terminate()
            return

    logger.info(f"Opened audio stream: {SAMPLE_RATE}Hz, mono, {stream_format}")
    
    # Connect to server
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((SERVER_HOST, SERVER_PORT))
        logger.info(f"Connected to server at {SERVER_HOST}:{SERVER_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to server: {e}")
        stream.stop_stream()
        stream.close()
        pa.terminate()
        return
    
    packet_serial = 0
    
    try:
        logger.info("Starting audio capture and transmission...")
        while True:
            # Read audio chunk from microphone
            try:
                audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            except Exception as e:
                logger.warning(f"Error reading audio: {e}")
                continue

            # If device provided 24-bit samples (3 bytes/sample), convert from
            # little-endian 3-byte signed ints to 32-bit signed little-endian
            # containers by sign-extending the top byte.
            if stream_format == 'int24':
                # audio_data length should be CHUNK_SIZE * 3
                if len(audio_data) % 3 != 0:
                    logger.error(f"Invalid int24 audio length: {len(audio_data)}")
                    continue

                arr = np.frombuffer(audio_data, dtype=np.uint8)
                frames = arr.reshape(-1, 3)
                # little-endian: b0 + (b1<<8) + (b2<<16)
                vals = (frames[:,0].astype(np.int32)
                    | (frames[:,1].astype(np.int32) << 8)
                    | (frames[:,2].astype(np.int32) << 16))
                # Sign-extend 24-bit to 32-bit safely using unsigned ops to
                # avoid Python-int promotion during bitwise OR.
                mask_sign = (vals & 0x800000) != 0
                uvals = vals.astype(np.uint32)
                if mask_sign.any():
                    uvals[mask_sign] |= np.uint32(0xFF000000)
                vals = uvals.view(np.int32)

                payload = vals.astype('<i4').tobytes()
            else:
                # stream_format == 'int32'
                samples = np.frombuffer(audio_data, dtype=np.int32)
                # Assume lower 24 bits are the meaningful audio; mask and sign-extend
                vals = samples & 0x00FFFFFF
                mask_sign = (vals & 0x800000) != 0
                uvals = vals.astype(np.uint32)
                if mask_sign.any():
                    uvals[mask_sign] |= np.uint32(0xFF000000)
                vals = uvals.view(np.int32)
                payload = vals.astype('<i4').tobytes()
            payload_len = len(payload)
            
            # Verify payload is valid
            if payload_len % 4 != 0:
                logger.error(f"Invalid payload length: {payload_len}")
                continue
            
            if payload_len > MAX_PAYLOAD_LEN:
                logger.error(f"Payload too large: {payload_len} > {MAX_PAYLOAD_LEN}")
                continue
            
            # Create and send header
            # Force plain Python ints for all header fields
            current_time_us = int(get_monotonic_time_us()) & UINT32_MASK
            packet_serial = int(packet_serial) & UINT32_MASK
            payload_len = int(payload_len)
            checksum = int(compute_header_checksum(MAGIC, current_time_us, packet_serial, payload_len))

            try:
                header = struct.pack(
                    HEADER_FORMAT,
                    MAGIC,
                    current_time_us,
                    packet_serial,
                    payload_len,
                    checksum,
                )
            except Exception as e:
                # Log detailed info to diagnose conversion errors
                logger.exception("Failed packing header")
                logger.error(
                    "Header field types and values: magic=%r(%s), current_time_us=%r(%s), packet_serial=%r(%s), payload_len=%r(%s), checksum=%r(%s)",
                    MAGIC,
                    type(MAGIC),
                    current_time_us,
                    type(current_time_us),
                    packet_serial,
                    type(packet_serial),
                    payload_len,
                    type(payload_len),
                    checksum,
                    type(checksum),
                )
                break
            
            try:
                client.sendall(header)
                client.sendall(payload)
                logger.debug(f"Sent packet {packet_serial}: {payload_len} bytes")
            except Exception as e:
                logger.exception("Failed to send packet")
                break
            
            packet_serial = (packet_serial + 1) & UINT32_MASK
            
            # time.sleep(0.01)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Unexpected error during capture/send loop")
    finally:
        logger.info("Cleaning up...")
        stream.stop_stream()
        stream.close()
        pa.terminate()
        client.close()
        logger.info("Done")


if __name__ == "__main__":
    capture_and_send_audio()
