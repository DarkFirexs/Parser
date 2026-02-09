from http.server import BaseHTTPRequestHandler
import os

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Читаем конфиги
        file_path = os.path.join(os.path.dirname(__file__), '..', 'configs_b64.txt')
        
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(content.encode())
        except:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Configs not found')
