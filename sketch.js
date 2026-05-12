let peer;
let myId;
let video; // 手機端是本地相機，電腦端是接收到的遠端影像
let facemesh;
let predictions = [];
let isPhone = false;
let remoteStreamReady = false;

function setup() {
  createCanvas(windowWidth, windowHeight);

  const urlParams = new URLSearchParams(window.location.search);
  const room = urlParams.get('room');

  // 建立 PeerJS 物件，加入明確的 STUN 伺服器配置以利跨網路連線
  const peerConfig = {
    config: {
      'iceServers': [
        { url: 'stun:stun.l.google.com:19302' },
        { url: 'stun:stun1.l.google.com:19302' }
      ]
    }
  };

  if (room) {
    // 手機端模式
    isPhone = true;
    video = createCapture(VIDEO, (stream) => {
      peer = new Peer();
      peer = new Peer(peerConfig);
      peer.on('open', (id) => {
        peer.call(room, stream); // 撥號給電腦
      });
    });
    video.size(640, 480);
    video.hide();
  } else {
    // 電腦端模式
    peer = new Peer();
    peer = new Peer(peerConfig);
    peer.on('open', (id) => {
      myId = id;
      if (typeof updateQRCode === 'function') updateQRCode(id);
    });

    peer.on('call', (call) => {
      call.answer(); // 接聽手機的來電
      call.on('stream', (stream) => {
        // 接收手機影像
        video = createVideo();
        video.elt.srcObject = stream;
        video.elt.play();
        video.elt.muted = true; // 避免回音
        video.size(640, 480);
        video.hide();
        remoteStreamReady = true;
        
        // 初始化臉部偵測
        facemesh = ml5.facemesh(video, () => console.log("臉部偵測模型已準備好"));
        facemesh.on("predict", results => {
          predictions = results;
        });
      });
    });
  }
}

function draw() {
  background(0);
  
  let boxW = 640;
  let boxH = 480;
  let x = (width - boxW) / 2;
  let y = (height - boxH) / 2;

  if (isPhone) {
    fill(255);
    textAlign(CENTER, CENTER);
    textSize(24);
    text("手機端：影像傳送中", width / 2, height / 2);
  } else {
    // 電腦端繪製
    stroke(255);
    noFill();
    rect(x, y, boxW, boxH);

    if (remoteStreamReady && video) {
      image(video, x, y, boxW, boxH);
      drawFaceEffect(x, y);
    } else {
      fill(255);
      noStroke();
      textSize(24);
      textAlign(CENTER, CENTER);
      text('等待手機掃碼連線...', width / 2, height / 2);
    }
  }

  // 學生資訊
  fill(255);
  noStroke();
  textSize(20);
  textAlign(CENTER, CENTER);
  text('414730050 曹苡萱', width / 2, y - 20);
}

function drawFaceEffect(offsetX, offsetY) {
  predictions.forEach(prediction => {
    const keypoints = prediction.scaledMesh;

    // 1. 畫紅鼻子 (點位 5 是鼻子中心)
    const nose = keypoints[5];
    fill(255, 0, 0, 200);
    noStroke();
    ellipse(offsetX + nose[0], offsetY + nose[1], 40, 40);

    // 2. 畫貓鬚 (點位 234, 454 是臉頰邊緣)
    stroke(255, 200);
    strokeWeight(4);
    line(offsetX + nose[0] - 20, offsetY + nose[1], offsetX + nose[0] - 100, offsetY + nose[1] - 20);
    line(offsetX + nose[0] - 20, offsetY + nose[1] + 15, offsetX + nose[0] - 100, offsetY + nose[1] + 20);
    line(offsetX + nose[0] + 20, offsetY + nose[1], offsetX + nose[0] + 100, offsetY + nose[1] - 20);
    line(offsetX + nose[0] + 20, offsetY + nose[1] + 15, offsetX + nose[0] + 100, offsetY + nose[1] + 20);
  });
}

function windowResized() {
  resizeCanvas(windowWidth, windowHeight);
}
