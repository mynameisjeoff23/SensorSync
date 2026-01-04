import socket
import threading
import time
import io

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

    while True:

        # if the client disconnects, exit the loop
        if not conn:                    
            break

        data = conn.recv(4096)
        if not data:
            time.sleep(0.1)             # TODO: change, for now only recieves every ~1s
            continue
        else:
            with io.BytesIO(data) as stream:
                startTime = stream.readline()
                audioLength = stream.readline()
                audio = stream.read(audioLength)        # must read lenth because audio data may otherwise contain newlines
                buffer.append(audio)


    print(f"Client disconnected: {addr}")
    #TODO: write audio into wav file once done


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