from http.server import HTTPServer, BaseHTTPRequestHandler
import threading


class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write('🤖 Bot is alive!')

    def log_message(self, format, *args):
        pass


def run_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), SimpleHandler)
    print(f"🌐 Keep-alive server started on port {port}")
    server.serve_forever()


def start_keep_alive():
    port = int(os.getenv("PORT", 8080))
    thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    thread.start()