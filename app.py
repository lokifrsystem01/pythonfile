#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer

import os

import json

import requests




PORT = int(os.environ.get("PORT", 10000))  # Render auto-assigns port

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")




GROQ_URL = "https://api.groq.com/v1/chat/completions"







class ProxyHandler(BaseHTTPRequestHandler):




    def _send_headers(self, status=200):

        self.send_response(status)

        self.send_header("Content-Type", "application/json")

        self.send_header("Access-Control-Allow-Origin", "*")

        self.end_headers()




    def do_POST(self):

        if self.path != "/v1/chat/completions":

            self._send_headers(404)

            self.wfile.write(b'{"error":"Not Found"}')

            return




        content_length = int(self.headers.get("Content-Length", 0))

        request_data = self.rfile.read(content_length)

        request_json = json.loads(request_data.decode("utf-8"))




        print("\n📩 Request from ESP32:")

        print(json.dumps(request_json, indent=2))




        headers = {

            "Authorization": f"Bearer {GROQ_API_KEY}",

            "Content-Type": "application/json"

        }




        print("🚀 Forwarding to Groq…")

        groq_res = requests.post(GROQ_URL, headers=headers, json=request_json)




        resp_json = groq_res.json()

        print("\n📨 Groq Response:")

        print(json.dumps(resp_json, indent=2))




        self._send_headers(groq_res.status_code)

        self.wfile.write(json.dumps(resp_json).encode("utf-8"))







def run():

    server_address = ("0.0.0.0", PORT)

    httpd = HTTPServer(server_address, ProxyHandler)

    print(f"🌍 Server online at port {PORT}")

    httpd.serve_forever()







if __name__ == "__main__":

    run()