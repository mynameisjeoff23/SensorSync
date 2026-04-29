import socket
import threading
import os
import struct
from collections import deque
import numpy
from scipy.io.wavfile import write 
from PacketSerialTracker import PacketSerialTracker
from ChecksumTracker import ChecksumTracker
from LatencyTracker import LatencyTracker

HOST = "0.0.0.0"
PORT = 8000
HEADER_FORMAT = "<4sIIHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_LEN = 4096
AUDIO_FREQUENCY = 16000
AUDIO_LENGTH_S = 5
MAX_SAMPLES_TO_KEEP = AUDIO_FREQUENCY * AUDIO_LENGTH_S

def scale_right_justified_int24_to_int32(samples: numpy.ndarray) -> numpy.ndarray:
    """Scale 24-bit PCM stored in int32 containers up to full int32 range."""
    if samples.size == 0:
        return samples

    max_abs = int(numpy.max(numpy.abs(samples.astype(numpy.int64))))

    # If values fit in signed 24-bit range, they are likely right-justified int24.
    if max_abs <= 0x7FFFFF:
        scaled = samples.astype(numpy.int64) << 8
        return numpy.clip(scaled, numpy.iinfo(numpy.int32).min, numpy.iinfo(numpy.int32).max).astype(numpy.int32)

    print("Audio scaled before saving")
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
    print(f"Client connected: {addr}")
    audio_chunks = deque()
    samples_kept = 0
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

            packet = recv_exact(conn, audioLength)
            audio = numpy.frombuffer(packet, dtype='<i4').astype(numpy.int32)  # small-endian int32

            packet_tracker.observe(packetSerial)
            latency_tracker.observe(startTime)

            audio_chunks.append(audio)
            samples_kept += audio.size

            while samples_kept > MAX_SAMPLES_TO_KEEP and audio_chunks:
                overflow = samples_kept - MAX_SAMPLES_TO_KEEP
                oldest = audio_chunks[0]

                if overflow >= oldest.size:
                    samples_kept -= oldest.size
                    audio_chunks.popleft()
                else:
                    audio_chunks[0] = oldest[overflow:]
                    samples_kept -= overflow

            print(f"Frame start={startTime} len={audioLength} first={packet[:20]!r}")

    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout) as e:
        print(f"Connection lost with {addr}: {e}")
    except (ConnectionError, ValueError) as e:
        print(f"Received invalid audio chunk, skipping: {e}")

    finally:
        conn.close()    
        print(f"Client disconnected: {addr}")

        if audio_chunks:
            serverPath = os.path.dirname(os.path.abspath(__file__))
            audioPath = serverPath + "/ReceivedAudio/"
            os.makedirs(audioPath, exist_ok=True)

            totalAudio = numpy.concatenate(list(audio_chunks), dtype=numpy.int32)
            totalAudio = scale_right_justified_int24_to_int32(totalAudio)
            write(audioPath + f"audio_{addr[1]}.wav", AUDIO_FREQUENCY, totalAudio)


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        print(f"TCP server listening on {HOST}:{PORT}")
        try:
            while True:
                conn, addr = server.accept()
                thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                thread.start()
        except KeyboardInterrupt:
            print("Shutting down server")


if __name__ == "__main__":
    main()