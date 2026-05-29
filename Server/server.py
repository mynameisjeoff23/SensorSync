import logging
import os
import socket
import struct
import threading
import numpy
from scipy.io.wavfile import write 
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from PacketSerialTracker import PacketSerialTracker
from ChecksumTracker import ChecksumTracker
from LatencyTracker import LatencyTracker
from TranscriptChunk import TranscriptChunk

HOST = "0.0.0.0"
PORT = 8000
HEADER_FORMAT = "<4sIIHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_LEN = 4096
AUDIO_FREQUENCY = 16000
AUDIO_LENGTH_S = 5
MAX_SAMPLES_TO_KEEP = AUDIO_FREQUENCY * AUDIO_LENGTH_S
MODEL_SIZE = "small"
MODEL_REPO_ID = f"Systran/faster-whisper-{MODEL_SIZE}"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

_whisper_model = None
_whisper_model_lock = threading.Lock()


def ensure_whisper_model_available() -> str:
    logger.info("Checking for Whisper model %s on disk", MODEL_REPO_ID)
    try:
        model_path = snapshot_download(repo_id=MODEL_REPO_ID, local_files_only=True)
        logger.info("Whisper model found on disk at %s; internet access is not required.", model_path)
        return model_path
    except LocalEntryNotFoundError:
        logger.warning(
            "Whisper model %s is not on disk; internet access is required to download it once.",
            MODEL_REPO_ID,
        )
        model_path = snapshot_download(repo_id=MODEL_REPO_ID)
        logger.info("Whisper model downloaded to %s", model_path)
        return model_path


def get_whisper_model() -> WhisperModel:
    global _whisper_model

    with _whisper_model_lock:
        if _whisper_model is None:
            model_path = ensure_whisper_model_available()
            _whisper_model = WhisperModel(model_path, device="cpu", compute_type="int8")

        return _whisper_model

def scale_right_justified_int24_to_int32(samples: numpy.ndarray) -> numpy.ndarray:
    """Scale 24-bit PCM stored in int32 containers up to full int32 range."""
    if samples.size == 0:
        return samples

    max_abs = int(numpy.max(numpy.abs(samples.astype(numpy.int64))))

    # right justified 24 bit
    if max_abs <= 0x7FFFFF:
        scaled = samples.astype(numpy.int64) << 8
        return numpy.clip(scaled, numpy.iinfo(numpy.int32).min, numpy.iinfo(numpy.int32).max).astype(numpy.int32)

    logger.debug("Audio already appears to be full-width int32 before saving")
    return samples


def recv_exact(conn: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = conn.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("Socket closed while reading frame")
        chunks.extend(chunk)
    return bytes(chunks)


def handle_client(conn: socket.socket, addr: tuple) -> None:
    """ Handles a socket connection in a new thread when it connects to the server.
        This thread will run until the client disconnects.
        When the client disconnects, it will print the last 5 chunks of audio recieved.

    Args:
        conn (socket.socket): The socket connection to the client.
        addr (tuple): The address of the client.
    """
    client_id = f"{addr[0]}:{addr[1]}"
    logger.info("Client connected: %s", client_id)
    audio_chunks = TranscriptChunk()
    packet_tracker = PacketSerialTracker()
    checksum_tracker = ChecksumTracker()
    latency_tracker = LatencyTracker()

    conn.settimeout(5.0)
    
    try:
        while True:
            header = recv_exact(conn, HEADER_SIZE)
            magic, startTime, packetSerial, audioLength, checksum = struct.unpack(HEADER_FORMAT, header)

            if magic != b"AUD0":
                raise ValueError(f"Invalid frame magic: {magic!r}")
            if not 0 <= audioLength <= MAX_PAYLOAD_LEN:
                raise ValueError(f"Audio length {audioLength} out of range [0, {MAX_PAYLOAD_LEN}]")
            if audioLength % 4 != 0:
                raise ValueError(f"Audio length {audioLength} is not divisible by 4")
            if not checksum_tracker.validate(magic, startTime, packetSerial, audioLength, checksum):
                raise ValueError(
                    f"Header checksum mismatch: got={checksum} expected={ChecksumTracker.compute_header_checksum(magic, startTime, packetSerial, audioLength)}"
                )

            previous_dropped_packets = packet_tracker.dropped_packets
            previous_serial = packet_tracker.last_serial

            packet = recv_exact(conn, audioLength)
            audio_chunks.add(packet)

            packet_tracker.observe(packetSerial)
            latency_tracker.observe(startTime)

            skipped_packets = packet_tracker.dropped_packets - previous_dropped_packets
            if skipped_packets > 0:
                logger.warning(
                    "[%s] Skipped %d packet(s): previous_serial=%s current_serial=%d start_time_us=%d payload_len=%d",
                    client_id,
                    skipped_packets,
                    previous_serial,
                    packetSerial,
                    startTime,
                    audioLength,
                )

            logger.debug(audio_chunks.first20())

    except socket.timeout:
        logger.warning("[%s] Server reset connection after idle timeout.", client_id)
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
        logger.info("[%s] Connection closed by client: %s", client_id, e)
    except ConnectionError as e:
        logger.info("[%s] Connection closed while reading packet: %s", client_id, e)
    except ValueError as e:
        logger.warning("[%s] Server reset connection after faulty packet: %s", client_id, e)

    finally:
        conn.close()    
        logger.info("Client disconnected: %s", client_id)

        if audio_chunks:
            serverPath = os.path.dirname(os.path.abspath(__file__))
            audioPath = serverPath + "/ReceivedAudio/"
            os.makedirs(audioPath, exist_ok=True)

            totalAudio = audio_chunks.asFloat32()
            write(audioPath + f"audio_{addr[1]}.wav", AUDIO_FREQUENCY, totalAudio)


def main():
    get_whisper_model()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        logger.info("TCP server listening on %s:%s", HOST, PORT)
        try:
            while True:
                conn, addr = server.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            logger.info("Shutting down server")


if __name__ == "__main__":
    main()