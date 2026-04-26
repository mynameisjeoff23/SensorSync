import socket
import threading
import time
import io
import os
import struct
import numpy
from scipy.io.wavfile import write 

from CircularBuffer import CircularBuffer

HOST = "0.0.0.0"
PORT = 8000
HEADER_FORMAT = "<4sIHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_PAYLOAD_LEN = 2048


def compute_header_checksum(magic: bytes, start_time: int, payload_len: int) -> int:
    """Compute a simple 16-bit checksum over header fields except checksum itself."""
    header_without_checksum = struct.pack("<4sIH", magic, start_time, payload_len)
    return sum(header_without_checksum) & 0xFFFF


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
    buffer = CircularBuffer(80)

    conn.settimeout(5.0)
    time.sleep(0.5)                 # time for data to be received

    # 0 is Time header
    # 1 is Length header
    # 2 is Audio data
    dataType = 0
    
    try:
        while True:
            header = recv_exact(conn, HEADER_SIZE)
            magic, startTime, audioLength, checksum = struct.unpack(HEADER_FORMAT, header)

            if magic != b"AUD0":
                raise ValueError(f"Invalid frame magic: {magic!r}")
            if not 0 <= audioLength <= MAX_PAYLOAD_LEN:
                raise ValueError(f"Audio length {audioLength} out of range [0, {MAX_PAYLOAD_LEN}]")
            if audioLength % 4 != 0:
                raise ValueError(f"Audio length {audioLength} is not divisible by 4")
            expected_checksum = compute_header_checksum(magic, startTime, audioLength)
            if checksum != expected_checksum:
                raise ValueError(
                    f"Header checksum mismatch: got={checksum} expected={expected_checksum}"
                )

            packet = recv_exact(conn, audioLength)
            audio = numpy.frombuffer(packet, dtype='<i4').astype(numpy.int32)  # small-endian int32

            # Store audio chunk in circular buffer
            # Currently disregarding start time of audio clip
            # TODO: figure out what to do with time
            buffer.add(audio)
            print(f"Frame start={startTime} len={audioLength} first={packet[:20]!r}")

    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout) as e:
        print(f"Connection lost with {addr}: {e}")
    except (ConnectionError, ValueError) as e:
        print(f"Received invalid audio chunk, skipping: {e}")

    finally:
        conn.close()    
        print(f"Client disconnected: {addr}")

        if buffer.size() > 0:
            serverPath = os.path.dirname(os.path.abspath(__file__))
            audioPath = serverPath + "/ReceivedAudio/"
            os.makedirs(audioPath, exist_ok=True)

            totalAudio = numpy.concatenate([buffer.get() for x in range(buffer.size())], dtype=numpy.int32)
            sampleRate = 16000
            write(audioPath + f"audio_{addr[1]}.wav", sampleRate, totalAudio)


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