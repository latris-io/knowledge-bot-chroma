#!/usr/bin/env python3
"""
Health Proxy for ChromaDB v1 to v2 API Compatibility
Handles deprecated v1 API requests and provides appropriate responses
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse
import sys
import threading
import time
import os

class HealthProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging to reduce noise
        pass
    
    def do_GET(self):
        path = self.path
        
        # Handle v1 heartbeat requests (most common from Render)
        if path == '/api/v1/heartbeat':
            self.handle_v1_heartbeat()
        elif path == '/api/v1/version':
            self.handle_v1_version()
        elif path.startswith('/api/v2/'):
            self.proxy_to_chroma(path)
        elif path == '/' or path == '/health':
            self.handle_root_health()
        else:
            self.proxy_to_chroma(path)
    
    def do_POST(self):
        """Handle POST requests and proxy to ChromaDB"""
        self.proxy_to_chroma(self.path, method='POST')
    
    def do_DELETE(self):
        """Handle DELETE requests and proxy to ChromaDB"""
        self.proxy_to_chroma(self.path, method='DELETE')
    
    def do_PUT(self):
        """Handle PUT requests and proxy to ChromaDB"""
        self.proxy_to_chroma(self.path, method='PUT')
    
    def do_PATCH(self):
        """Handle PATCH requests and proxy to ChromaDB"""
        self.proxy_to_chroma(self.path, method='PATCH')
    
    def handle_v1_heartbeat(self):
        """Handle deprecated v1 heartbeat - check if ChromaDB is responsive via v2"""
        try:
            # Try to check ChromaDB health via v2 API
            chroma_response = self.check_chroma_health()
            if chroma_response:
                # Return success response for v1 heartbeat compatibility
                response = {"status": "ok", "message": "ChromaDB is healthy (v2 API active)"}
                self.send_json_response(200, response)
            else:
                self.send_error_response(503, "ChromaDB not ready")
        except Exception as e:
            self.send_error_response(503, f"Health check failed: {str(e)}")
    
    def handle_v1_version(self):
        """Handle v1 version requests"""
        try:
            # Try v2 version endpoint
            chroma_url = "http://localhost:8000/api/v2/version"
            req = urllib.request.Request(chroma_url)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read()
                # Proxy the v2 response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Fallback response for v1 compatibility
                response = {"error": "Unimplemented", "message": "The v1 API is deprecated. Please use /v2 apis"}
                self.send_json_response(410, response)
            else:
                self.send_error_response(e.code, f"ChromaDB error: {e.reason}")
        except Exception as e:
            self.send_error_response(503, f"Connection failed: {str(e)}")
    
    def handle_root_health(self):
        """Simple health check for root path"""
        if self.check_chroma_health():
            response = {"status": "healthy", "service": "ChromaDB Proxy", "chroma_api": "v2"}
            self.send_json_response(200, response)
        else:
            response = {"status": "unhealthy", "service": "ChromaDB Proxy"}
            self.send_json_response(503, response)
    
    def proxy_to_chroma(self, path, method='GET'):
        """Proxy requests directly to ChromaDB"""
        try:
            chroma_url = f"http://localhost:8000{path}"
            
            # Get request body for write operations
            request_data = None
            if method in ['POST', 'PUT', 'PATCH']:
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 0:
                    request_data = self.rfile.read(content_length)
            
            # Prepare request
            req = urllib.request.Request(chroma_url, data=request_data, method=method)
            
            # Copy relevant headers
            content_type = self.headers.get('Content-Type')
            if content_type:
                req.add_header('Content-Type', content_type)
            
            authorization = self.headers.get('Authorization')
            if authorization:
                req.add_header('Authorization', authorization)
            
            # Make request to ChromaDB
            with urllib.request.urlopen(req, timeout=30) as response:
                self.send_response(response.status)
                # Copy headers
                for header, value in response.headers.items():
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(response.read())
                
        except urllib.error.HTTPError as e:
            # Read error response body
            error_body = e.read() if hasattr(e, 'read') else b''
            self.send_response(e.code)
            # Copy error headers
            if hasattr(e, 'headers'):
                for header, value in e.headers.items():
                    self.send_header(header, value)
            self.end_headers()
            self.wfile.write(error_body)
            
        except Exception as e:
            self.send_error_response(503, f"Connection failed: {str(e)}")
    
    def check_chroma_health(self):
        """Check if ChromaDB is healthy via v2 API"""
        try:
            # Try v2 version endpoint
            req = urllib.request.Request("http://localhost:8000/api/v2/version")
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status == 200
        except:
            try:
                # Fallback: try v2 heartbeat
                req = urllib.request.Request("http://localhost:8000/api/v2/heartbeat")
                with urllib.request.urlopen(req, timeout=3) as response:
                    return response.status == 200
            except:
                return False
    
    def send_json_response(self, status_code, data):
        """Send JSON response"""
        response_data = json.dumps(data).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_data)))
        self.end_headers()
        self.wfile.write(response_data)
    
    def send_error_response(self, status_code, message):
        """Send error response"""
        response = {"error": "Service Error", "message": message}
        self.send_json_response(status_code, response)

def wait_for_chroma():
    """Wait for ChromaDB to be available before starting proxy"""
    print("🔍 Waiting for ChromaDB to be available...")
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request("http://localhost:8000/api/v2/version")
            with urllib.request.urlopen(req, timeout=2) as response:
                if response.status == 200:
                    print("✅ ChromaDB is available, starting health proxy")
                    return True
        except:
            pass
        time.sleep(2)
        print(f"⏳ Waiting for ChromaDB... ({attempt + 1}/{max_attempts})")
    
    print("⚠️ ChromaDB not available, starting proxy anyway")
    return False

def start_proxy_server():
    """Start the health proxy server"""
    port = int(os.environ.get('PROXY_PORT', 3000))
    
    # Wait for ChromaDB to be ready
    wait_for_chroma()
    
    # Start proxy server
    with socketserver.TCPServer(("", port), HealthProxyHandler) as httpd:
        print(f"🌐 Health proxy server running on port {port}")
        print(f"📋 Proxying ALL HTTP methods (GET/POST/DELETE/PUT/PATCH) to ChromaDB v2 API")
        httpd.serve_forever()

if __name__ == "__main__":
    try:
        start_proxy_server()
    except KeyboardInterrupt:
        print("\n🛑 Health proxy server stopped")
    except Exception as e:
        print(f"❌ Health proxy error: {e}")
        sys.exit(1) 