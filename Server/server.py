import socket
import threading

HOST = "0.0.0.0"
PORT = 8000

def handle_client(conn: socket.socket, addr: tuple) -> None:
    print(f"Client connected: {addr}")
    with conn:
        buffer = b""
        while True:
            try:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    payload = line.decode("utf-8", errors="replace").strip()
                    if payload:
                        print(f"Received: {payload}")
                        conn.sendall(b"ACK\n")
            except ConnectionResetError:
                break
    print(f"Client disconnected: {addr}")


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