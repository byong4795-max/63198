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
        body {{ margin: 0; padding: 20px; background: #1a1a1a; color: #fff; font-family: Arial; text-align: center; }}
        #canvas {{ max-width: 100%; border: 2px solid #0066cc; margin: 20px 0; }}
        #qrContainer {{ background: #fff; padding: 20px; border-radius: 10px; display: inline-block; margin: 20px 0; }}
        #qr {{ max-width: 300px; }}
        .info {{ font-size: 18px; margin: 20px 0; }}
        button {{ padding: 10px 20px; font-size: 16px; background: #0066cc; color: #fff; border: none; border-radius: 5px; cursor: pointer; margin: 5px; }}
        button:hover {{ background: #0052a3; }}
    </style>
</head>
<body>
    <h1>手機鏡頭特效展示</h1>
    <div class="info">用手機掃描下方 QR Code，或直接訪問連結</div>
    <div id="qrContainer">
        <img id="qr" src="/qr" alt="QR Code">
    </div>
    <div class="info">連結: <a href="__PHONE_URL__" style="color: #0066cc;">__PHONE_URL__</a></div>
    <div class="info">__NOTE_TEXT__</div>
    <h2>電腦顯示:</h2>
    <canvas id="canvas" width="640" height="480"></canvas>
    <div>
        <button onclick="changeEffect()">切換特效 (SPACE)</button>
        <button onclick="downloadImage()">保存截圖 (S)</button>
    </div>
    <div id="status" style="font-size: 14px; color: #aaa;">等待手機連接...</div>
    <script>
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const status = document.getElementById('status');
        let effectMode = 0;
        const modes = ['正常', '像素化', '黑白', '反相', '邊緣'];

        function applyEffect() {
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const data = imageData.data;
            if (effectMode === 1) {
                const size = 12;
                for (let y = 0; y < canvas.height; y += size) {
                    for (let x = 0; x < canvas.width; x += size) {
                        const idx = (x + y * canvas.width) * 4;
                        const r = data[idx];
                        const g = data[idx + 1];
                        const b = data[idx + 2];
                        for (let dy = 0; dy < size && y + dy < canvas.height; dy++) {
                            for (let dx = 0; dx < size && x + dx < canvas.width; dx++) {
                                const pidx = (x + dx + (y + dy) * canvas.width) * 4;
                                data[pidx] = r;
                                data[pidx + 1] = g;
                                data[pidx + 2] = b;
                            }
                        }
                    }
                }
            } else if (effectMode === 2) {
                for (let i = 0; i < data.length; i += 4) {
                    const gray = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
                    data[i] = data[i + 1] = data[i + 2] = gray;
                }
            } else if (effectMode === 3) {
                for (let i = 0; i < data.length; i += 4) {
                    data[i] = 255 - data[i];
                    data[i + 1] = 255 - data[i + 1];
                    data[i + 2] = 255 - data[i + 2];
                }
            } else if (effectMode === 4) {
                const copy = new Uint8ClampedArray(data);
                const w = canvas.width;
                const h = canvas.height;
                for (let y = 1; y < h - 1; y++) {
                    for (let x = 1; x < w - 1; x++) {
                        const idx = (x + y * w) * 4;
                        let gx = 0;
                        let gy = 0;
                        for (let dy = -1; dy <= 1; dy++) {
                            for (let dx = -1; dx <= 1; dx++) {
                                const p = (x + dx + (y + dy) * w) * 4;
                                const gray = copy[p] * 0.299 + copy[p + 1] * 0.587 + copy[p + 2] * 0.114;
                                gx += gray * dx;
                                gy += gray * dy;
                            }
                        }
                        const val = 255 - Math.min(255, Math.sqrt(gx * gx + gy * gy));
                        data[idx] = data[idx + 1] = data[idx + 2] = val;
                    }
                }
            }
            ctx.putImageData(imageData, 0, 0);
        }

        function updateFrame() {
            fetch('/frame')
                .then(r => {
                    if (!r.ok) throw new Error('no frame');
                    return r.blob();
                })
                .then(blob => {
                    const url = URL.createObjectURL(blob);
                    const img = new Image();
                    img.onload = () => {
                        ctx.drawImage(img, 0, 0);
                        applyEffect();
                        status.textContent = '已連接: ' + modes[effectMode];
                        URL.revokeObjectURL(url);
                    };
                    img.src = url;
                })
                .catch(() => {
                    status.textContent = '等待手機連接...';
                });
            setTimeout(updateFrame, 100);
        }
        updateFrame();

        function changeEffect() {
            effectMode = (effectMode + 1) % modes.length;
            status.textContent = '已連接: ' + modes[effectMode];
        }
        function downloadImage() {
            canvas.toBlob(blob => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'photo_' + Date.now() + '.png';
                a.click();
            });
        }
        document.addEventListener('keydown', e => {
            if (e.code === 'Space') changeEffect();
            if (e.key === 's' || e.key === 'S') downloadImage();
        });
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
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            self.send_response(200)
            self.send_header('Content-type', 'image/png')
            self.send_header('Content-Length', len(img_bytes.getvalue()))
            self.end_headers()
            self.wfile.write(img_bytes.getvalue())
        elif self.path == '/phone':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            phone_html = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>手機攝影頭分享</title>
    <style>
        body { margin: 0; padding: 0; background: #000; overflow: hidden; color: #fff; font-family: Arial, sans-serif; }
        #canvas { display: block; width: 100vw; height: 100vh; object-fit: cover; }
        #info { position: absolute; top: 10px; left: 10px; color: #fff; background: rgba(0,0,0,0.7); padding: 10px; border-radius: 5px; font-family: monospace; z-index: 10; }
        #fallback { position: absolute; top: 70px; left: 10px; color: #fff; background: rgba(0,0,0,0.7); padding: 12px; border-radius: 5px; z-index: 10; display: none; }
        #fallback input, #fallback button { display: block; margin-top: 8px; font-size: 16px; }
        #fallback button { padding: 10px 15px; background: #0066cc; color: #fff; border: none; border-radius: 5px; }
    </style>
</head>
<body>
    <canvas id="canvas"></canvas>
    <div id="info">初始化中...</div>
    <div id="fallback">
        <div>攝影機無法使用，請拍照並上傳：</div>
        <input id="fileInput" type="file" accept="image/*;capture=camera">
        <button id="sendPhoto">上傳照片</button>
    </div>
    <script>
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const info = document.getElementById('info');
        const fallback = document.getElementById('fallback');
        const fileInput = document.getElementById('fileInput');
        const sendPhoto = document.getElementById('sendPhoto');

        function resizeCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        function showFallback(message) {
            info.textContent = message;
            fallback.style.display = 'block';
