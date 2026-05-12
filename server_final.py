#!/usr/bin/env python3
import http.server
import socketserver
import qrcode
import socket
import os
import threading
import urllib.request
import json
from io import BytesIO

PORT = 8000
current_frame = None
frame_lock = threading.Lock()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def get_ngrok_url():
    try:
        with urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels', timeout=1) as res:
            data = json.loads(res.read().decode())
            for tunnel in data.get('tunnels', []):
                public_url = tunnel.get('public_url')
                proto = tunnel.get('proto')
                if public_url and proto in ('http', 'https'):
                    return public_url
    except Exception:
        return None
    return None


class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            ip = get_local_ip()
            public_url = get_ngrok_url()
            if public_url:
                phone_url = public_url.rstrip('/') + '/phone'
                note_text = '偵測到 ngrok 公開連結，可跨網路連線。'
            else:
                phone_url = f'http://{ip}:{PORT}/phone'
                note_text = '此連結僅限本機或同一 Wi-Fi。若要不同網路連線，請執行 ngrok http 8000。'

            html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>手機鏡頭特效</title>
    <style>
        body { margin: 0; padding: 20px; background: #081b2b; color: #fff; font-family: Arial, sans-serif; text-align: center; }
        #qr { width: 240px; height: 240px; }
        .info { margin: 12px 0; font-size: 16px; }
        a { color: #59c; }
    </style>
</head>
<body>
    <h1>手機鏡頭傳送頁面</h1>
    <div class="info">請掃描 QR Code，或從手機打開下方連結。</div>
    <div><img id="qr" src="/qr" alt="QR Code"></div>
    <div class="info">手機連結：<a href="__PHONE_URL__">__PHONE_URL__</a></div>
    <div class="info">__NOTE_TEXT__</div>
    <h2>電腦預覽</h2>
    <canvas id="canvas" width="640" height="480" style="max-width:100%; border:2px solid #3aa;"></canvas>
    <div class="info" id="status">等待手機上傳畫面...</div>
    <script>
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const status = document.getElementById('status');

        function refreshFrame() {
            fetch('/frame')
                .then(res => {
                    if (!res.ok) throw new Error('no frame');
                    return res.blob();
                })
                .then(blob => {
                    const url = URL.createObjectURL(blob);
                    const img = new Image();
                    img.onload = () => {
                        const scale = Math.min(canvas.width / img.width, canvas.height / img.height);
                        const w = img.width * scale;
                        const h = img.height * scale;
                        const x = (canvas.width - w) / 2;
                        const y = (canvas.height - h) / 2;
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                        ctx.drawImage(img, x, y, w, h);
                        URL.revokeObjectURL(url);
                        status.textContent = '已連接，畫面已更新';
                    };
                    img.src = url;
                })
                .catch(() => {
                    status.textContent = '等待手機連接...';
                })
                .finally(() => setTimeout(refreshFrame, 400));
        }
        refreshFrame();
    </script>
</body>
</html>'''
            html = html.replace('__PHONE_URL__', phone_url).replace('__NOTE_TEXT__', note_text)
            self.wfile.write(html.encode())
        elif self.path == '/qr':
            ip = get_local_ip()
            public_url = get_ngrok_url()
            if public_url:
                url = public_url.rstrip('/') + '/phone'
            else:
                url = f'http://{ip}:{PORT}/phone'
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')
            buf = BytesIO()
            img.save(buf, format='PNG')
            data = buf.getvalue()
            self.send_response(200)
            self.send_header('Content-type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == '/phone':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            phone_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>手機鏡頭上傳</title>
    <style>
        body { margin: 0; background: black; color: white; font-family: Arial, sans-serif; }
        #video, #canvas { width: 100vw; height: 100vh; object-fit: cover; }
        #panel { position: absolute; top: 10px; left: 10px; z-index: 10; background: rgba(0,0,0,0.6); padding: 12px; border-radius: 8px; }
        button { padding: 10px 12px; border: none; border-radius: 6px; background: #29a; color: black; font-weight: bold; cursor: pointer; }
        input { margin-top: 8px; width: 100%; }
    </style>
</head>
<body>
    <video id="video" autoplay playsinline muted></video>
    <div id="panel">
        <div id="message">嘗試開啟攝影機...</div>
        <div id="fallback" style="display:none; margin-top:8px;">
            <input id="fileInput" type="file" accept="image/*;capture=camera">
            <button id="uploadButton">上傳照片</button>
        </div>
    </div>
    <script>
        const video = document.getElementById('video');
        const message = document.getElementById('message');
        const fallback = document.getElementById('fallback');
        const fileInput = document.getElementById('fileInput');
        const uploadButton = document.getElementById('uploadButton');
        const canvas = document.createElement('canvas');

        async function startCamera() {
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                showFallback('目前裝置不支援攝影機，請拍照上傳。');
                return;
            }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
                video.srcObject = stream;
                await video.play();
                message.textContent = '攝影機已啟動，正在傳送畫面...';
                fallback.style.display = 'none';
                requestAnimationFrame(captureFrame);
            } catch (err) {
                showFallback('無法啟動攝影機，請拍照上傳。');
            }
        }

        function showFallback(text) {
            message.textContent = text;
            fallback.style.display = 'block';
            video.style.display = 'none';
        }

        function captureFrame() {
            if (!video.videoWidth || !video.videoHeight) {
                requestAnimationFrame(captureFrame);
                return;
            }
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            canvas.toBlob(blob => {
                if (blob) fetch('/upload', { method: 'POST', body: blob });
            }, 'image/jpeg', 0.7);
            setTimeout(() => requestAnimationFrame(captureFrame), 250);
        }

        uploadButton.addEventListener('click', () => {
            const file = fileInput.files[0];
            if (!file) return;
            fetch('/upload', { method: 'POST', body: file });
            message.textContent = '已上傳照片，請回到電腦頁面查看。';
        });

        startCamera();
    </script>
</body>
</html>'''
            self.wfile.write(phone_html.encode())
        elif self.path == '/frame':
            global current_frame
            with frame_lock:
                if current_frame:
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(current_frame)))
                    self.end_headers()
                    self.wfile.write(current_frame)
                else:
                    self.send_response(404)
                    self.end_headers()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/upload':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            global current_frame
            with frame_lock:
                current_frame = body
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))

if __name__ == '__main__':
    ip = get_local_ip()
    print(f'伺服器已啟動: http://{ip}:{PORT}')
    print(f'手機訪問: http://{ip}:{PORT}/phone')
    print(f'電腦顯示: http://{ip}:{PORT}/')
    print('按 Ctrl+C 停止')

    with socketserver.TCPServer(('0.0.0.0', PORT), MyHandler) as httpd:
        httpd.serve_forever()
