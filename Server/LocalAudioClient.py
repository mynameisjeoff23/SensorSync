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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
    
    # Add magic bytes
    for byte in magic:
        sum_val = (sum_val + byte) & 0xFFFF
    
    # Add start_time_us bytes (little-endian)
    for i in range(4):
        sum_val = (sum_val + ((start_time_us >> (i * 8)) & 0xFF)) & 0xFFFF
    
    # Add packet_serial bytes (little-endian)
    for i in range(4):
        sum_val = (sum_val + ((packet_serial >> (i * 8)) & 0xFF)) & 0xFFFF
    
    # Add payload_len bytes (little-endian)
    for i in range(2):
        sum_val = (sum_val + ((payload_len >> (i * 8)) & 0xFF)) & 0xFFFF
    
    return sum_val & 0xFFFF


def capture_and_send_audio():
    """Capture audio from microphone and send to server in ESP32 format."""
    
    # Initialize PyAudio
    pa = pyaudio.PyAudio()
    
    # List available devices if needed
    logger.info("Available audio devices:")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        logger.info(f"  Device {i}: {info['name']} (channels: {info['maxInputChannels']})")
    
    # Open audio stream
    try:
        stream = pa.open(
            format=pyaudio.paInt32,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE,
            input_device_index=AUDIO_DEVICE_INDEX
        )
    except Exception as e:
        logger.error(f"Failed to open audio stream: {e}")
        pa.terminate()
        return
    
    logger.info(f"Opened audio stream: {SAMPLE_RATE}Hz, mono, int32")
    
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
                samples = np.frombuffer(audio_data, dtype=np.int32)
            except Exception as e:
                logger.warning(f"Error reading audio: {e}")
                continue
            
            # Convert to bytes (little-endian int32)
            payload = samples.astype('<i4').tobytes()
            payload_len = len(payload)
            
            # Verify payload is valid
            if payload_len % 4 != 0:
                logger.error(f"Invalid payload length: {payload_len}")
                continue
            
            if payload_len > MAX_PAYLOAD_LEN:
                logger.error(f"Payload too large: {payload_len} > {MAX_PAYLOAD_LEN}")
                continue
            
            # Create and send header
            current_time_us = get_monotonic_time_us()
            checksum = compute_header_checksum(MAGIC, current_time_us, packet_serial, payload_len)
            
            header = struct.pack(HEADER_FORMAT, MAGIC, current_time_us, packet_serial, payload_len, checksum)
            
            try:
                client.sendall(header)
                client.sendall(payload)
                logger.debug(f"Sent packet {packet_serial}: {payload_len} bytes")
            except Exception as e:
                logger.error(f"Failed to send packet: {e}")
                break
            
            packet_serial += 1
            
            # time.sleep(0.01)
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        logger.info("Cleaning up...")
        stream.stop_stream()
        stream.close()
        pa.terminate()
        client.close()
        logger.info("Done")


if __name__ == "__main__":
    capture_and_send_audio()
