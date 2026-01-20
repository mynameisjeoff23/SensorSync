import socket
import threading
import time
import io
import os
import numpy
from scipy.io.wavfile import write 

from CircularBuffer import CircularBuffer

HOST = "0.0.0.0"
PORT = 8000

def handle_client(conn: socket.socket, addr: tuple) -> None:
    """ Handles a socket connection in a new thread when it connects to the server.
        This thread will run until the client disconnects.
        When the client disconnects, it will print the last 5 chunks of audio recieved.

    Args:
        conn (socket.socket): The socket connection to the client.
        addr (tuple): The address of the client.
    """
    print(f"Client connected: {addr}")
    buffer = CircularBuffer(5)

    conn.settimeout(5.0)
    time.sleep(0.5)                 # time for data to be received

    # 0 is Time header
    # 1 is Length header
    # 2 is Audio data
    dataType = 0
    
    try:
        socketStream = b""
        while True:

            socketStream += conn.recv(4096)
            if not socketStream:
                break

            try:
                # Newline escape sequence is \xFF\xFF
                if b"\xFF\xFF" in socketStream: 

                    packet, socketStream = socketStream.split(b"\xFF\xFF", 1)
                    if not packet:
                        continue
                    
                    #TODO: Audio data could theoretically start with these strings, causing a bug
                    if packet.startswith(b"Time:"):
                        dataType = 0

                    elif packet.startswith(b"Length:"):
                        dataType = 1

                    else: 
                        dataType = 2

                    match dataType:
                        case 0:

                            # Decode time header. Time header details that start of the audio clip.
                            # Time will be in microseconds since the start of first audio recording.
                            startTime = 0
                            print(f"T: '{packet}'")
                            startTime = int(packet.rstrip().replace(b"Time:", b""))

                        case 1:

                            # Decode audio length header. Details the length of the audio clip in bytes.
                            # Since the audio is 16 bit, the length should always be even.
                            audioLength = 0
                            print(f"L: '{packet}'")
                            audioLength = int(packet.replace(b"Length:", b""))
                                                    
                        case 2:

                            # Read in audio data into uint16 array. Each sample is 2 bytes.
                            # MSB is first bit. Convert to int16 array. 
                            # Remove DC offset. Amplify to use full int16 range.
                            # Unsigned 12 bit ADC audio should fit into signed int16.
                            # TODO: change for when using I2S microphone.

                            if len(packet) != audioLength:
                                raise ValueError(f"Length of audio: {len(packet)} does not match length header: {audioLength}")
                            audio = numpy.frombuffer(packet, dtype='>u2')  # big-endian uint16
                            audio = audio.astype(numpy.int16)
                            audio = audio - numpy.mean(audio, dtype=numpy.int16)
                            audio = audio * 16

                            # Store audio chunk in circular buffer
                            # Currently disregarding start time of audio clip
                            # TODO: figure out what to do with time
                            buffer.add(audio)

                        case _:
                            raise ValueError("Invalid data type state")

            except ValueError as e:
                print(f"Received invalid audio chunk, skipping: {e}")
                continue

    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout) as e:
        print(f"Connection lost with {addr}: {e}")

    finally:
        conn.close()    
        print(f"Client disconnected: {addr}")

        if buffer.size() > 0:
            serverPath = os.path.dirname(os.path.abspath(__file__))
            audioPath = serverPath + "/ReceivedAudio/"
            os.makedirs(audioPath, exist_ok=True)

            totalAudio = numpy.concatenate([buffer.get() for x in range(buffer.size())], dtype=numpy.int16)
            sampleRate = 1000
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