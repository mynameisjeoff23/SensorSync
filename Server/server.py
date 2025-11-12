from http.server import BaseHTTPRequestHandler
import socketserver

hostName = "xx.xx.xx.xx"
serverPort = 8000

class Server(BaseHTTPRequestHandler):
    
    def do_POST(self):
        contentLength = int(self.headers["Content-Length"])
        postData = self.rfile.read1(contentLength)
        print("Post Data: ", end="")
        print(postData.decode("utf-8"))
        self.send_response(200)

if __name__ == "__main__":
    webServer = socketserver.TCPServer((hostName, serverPort), Server)
    print(f"Server started at http://{hostName}:{serverPort}/")

    try:
        webServer.serve_forever()
    except:
        pass

    webServer.server_close()    
    print("Server stopped.")