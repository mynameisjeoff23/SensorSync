import os
from psutil import cpu_count
import socket
import struct
import logging
import threading
from time import time
from pathlib import Path
from scipy.io.wavfile import write 
from faster_whisper import WhisperModel

from LatencyTracker import LatencyTracker
from TranscriptChunk import TranscriptChunk
from ChecksumTracker import ChecksumTracker
from PacketSerialTracker import PacketSerialTracker

HOST = "0.0.0.0"
PORT = 8000
HEADER_FORMAT = "<4sIIHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_LEN = 4096
AUDIO_FREQUENCY = 16000
AUDIO_LENGTH_S = 5
#PRINT_TRANSCRIPT_OUTPUT = True
MAX_SAMPLES_TO_KEEP = AUDIO_FREQUENCY * AUDIO_LENGTH_S
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny")
MODEL_REPO_ID = f"Systran/faster-whisper-{MODEL_SIZE}"
MODEL_PATH = os.environ.get("WHISPER_MODEL_PATH", "").strip()
NUM_CORES = cpu_count(logical = False)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_whisper_model = None
_whisper_model_lock = threading.Lock()


def _resolve_local_model_path() -> str | None:
    if not MODEL_PATH:
        return None

    resolved_path = Path(MODEL_PATH).expanduser()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Whisper model path does not exist: {resolved_path}")

    return str(resolved_path)


def ensure_whisper_model_available() -> str:
    local_model_path = _resolve_local_model_path()
    if local_model_path is not None:
        logger.info("Using Whisper model from local path %s", local_model_path)
        return local_model_path

    logger.info("Using Whisper model name %s", MODEL_SIZE)
    return MODEL_SIZE


def get_whisper_model() -> WhisperModel:
    global _whisper_model

    with _whisper_model_lock:
        if _whisper_model is None:
            model_source = ensure_whisper_model_available()
            _whisper_model = WhisperModel(model_source, 
                                          device="cpu", 
                                          compute_type="int8",
                                          cpu_threads=NUM_CORES,
                                          num_workers=2)    #TODO: change num_workers and quantify performance

        return _whisper_model


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
    #speech = Speech(printOut=True)

    conn.settimeout(5.0)
    
    try:
        transcriptionStart = time()
        logger.info("Transcription Starting Soon...")

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

            if time() - transcriptionStart > 1.0:
                start_trans = time()
                with _whisper_model_lock:
                    segments, info = _whisper_model.transcribe(audio_chunks.asFloat32(), 
                                                               beam_size=1,
                                                               language='en',
                                                               without_timestamps=True,
                                                               vad_filter=True,
                                                               vad_parameters=dict(min_silence_duration_ms=500))
                    text = " ".join(segment.text for segment in segments)
                trans_duration = time() - start_trans

                rendered_text = text.strip()
                logger.info("[%s] %s (%.2fs)", client_id, rendered_text, trans_duration)
                transcriptionStart = time()


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
    try:
        get_whisper_model()
    except (FileNotFoundError, RuntimeError) as e:
        logger.error("%s", e)
        raise SystemExit(1) from e

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