// posture-cam.js
const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const yargs = require('yargs/yargs');
const { hideBin } = require('yargs/helpers');
const path = require('path');
const fs = require('fs');
const open = require('open');

// Parse command line arguments
const argv = yargs(hideBin(process.argv))
  .option('ip', {
    alias: 'i',
    description: 'Robot IP address',
    default: '192.168.4.1'
  })
  .option('port', {
    alias: 'p',
    description: 'Robot video server port',
    default: 5000
  })
  .option('webport', {
    alias: 'w',
    description: 'Port for the web interface',
    default: 3000
  })
  .help()
  .alias('help', 'h')
  .argv;

// Configuration
const config = {
  robotIp: argv.ip,
  robotPort: argv.port,
  webPort: argv.webport
};

console.log(`Starting with configuration:`, config);

// Setup web server
const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Create public directory if it doesn't exist
const publicDir = path.join(__dirname, 'public');
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir);
}

// Create an index.html file with necessary scripts
const htmlPath = path.join(publicDir, 'index.html');
fs.writeFileSync(htmlPath, `
<!DOCTYPE html>
<html>
<head>
  <title>MoveNet Posture Camera</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- TensorFlow.js -->
  <script src="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.10.0"></script>
  <!-- MoveNet model -->
  <script src="https://cdn.jsdelivr.net/npm/@tensorflow-models/pose-detection"></script>
  
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 0;
      background-color: #f0f0f0;
    }
    .container {
      max-width: 1000px;
      margin: 0 auto;
      padding: 20px;
    }
    .video-container {
      position: relative;
      margin-bottom: 20px;
    }
    #videoElement {
      display: none;
    }
    #canvas {
      display: block;
      background-color: #333;
      max-width: 100%;
      border-radius: 8px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .controls {
      display: flex;
      gap: 10px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    button {
      padding: 8px 16px;
      background-color: #4285f4;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
    }
    button:hover {
      background-color: #3b78e7;
    }
    button:disabled {
      background-color: #cccccc;
      cursor: not-allowed;
    }
    .stats {
      background-color: rgba(0,0,0,0.7);
      color: white;
      padding: 10px;
      border-radius: 4px;
      position: absolute;
      top: 10px;
      left: 10px;
      font-size: 14px;
    }
    .settings {
      margin-top: 20px;
      background-color: white;
      padding: 15px;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .setting-row {
      display: flex;
      align-items: center;
      margin-bottom: 10px;
    }
    select, input {
      padding: 5px;
      margin-right: 10px;
    }
    label {
      margin-right: 10px;
      min-width: 150px;
    }
    .loading {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(0,0,0,0.8);
      color: white;
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 1000;
      font-size: 24px;
    }
    .loader {
      border: 6px solid #f3f3f3;
      border-top: 6px solid #3498db;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      animation: spin 2s linear infinite;
      margin-right: 20px;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  </style>
</head>
<body>
  <div id="loading" class="loading">
    <div class="loader"></div>
    <div>Loading MoveNet model...</div>
  </div>
  
  <div class="container">
    <h1>MoveNet Posture Camera</h1>
    
    <div class="video-container">
      <video id="videoElement" width="640" height="480" autoplay></video>
      <canvas id="canvas" width="640" height="480"></canvas>
      <div id="stats" class="stats">
        FPS: 0<br>
        Processing: 0ms
      </div>
    </div>
    
    <div class="controls">
      <button id="toggleSkeletonBtn">Toggle Skeleton</button>
      <button id="screenshotBtn">Take Screenshot</button>
      <button id="pauseBtn">Pause Processing</button>
      <button id="mirrorBtn">Mirror View</button>
    </div>
    
    <div class="settings">
      <h2>Settings</h2>
      
      <div class="setting-row">
        <label for="modelSelect">Model:</label>
        <select id="modelSelect">
          <option value="lightning">MoveNet Lightning (faster)</option>
          <option value="thunder">MoveNet Thunder (more accurate)</option>
        </select>
      </div>
      
      <div class="setting-row">
        <label for="scaleInput">Processing Scale:</label>
        <input type="range" id="scaleInput" min="0.1" max="1.0" step="0.1" value="0.5">
        <span id="scaleValue">0.5</span>
      </div>
      
      <div class="setting-row">
        <label for="confidenceInput">Confidence Threshold:</label>
        <input type="range" id="confidenceInput" min="0.1" max="0.9" step="0.05" value="0.3">
        <span id="confidenceValue">0.3</span>
      </div>
    </div>
  </div>

  <script>
    // Configuration
    const config = {
      robotIp: "${config.robotIp}",
      robotPort: ${config.robotPort},
      scale: 0.5,
      confidenceThreshold: 0.3,
      modelType: 'lightning',
      showSkeleton: true,
      mirrorView: false,
      processingEnabled: true
    };
    
    // Performance tracking
    const stats = {
      lastFpsUpdateTime: 0,
      frameCount: 0,
      fps: 0,
      processingTime: 0
    };
    
    // DOM elements
    const video = document.getElementById('videoElement');
    const canvas = document.getElementById('canvas');
    const ctx = canvas.getContext('2d');
    const statsElement = document.getElementById('stats');
    const toggleSkeletonBtn = document.getElementById('toggleSkeletonBtn');
    const screenshotBtn = document.getElementById('screenshotBtn');
    const pauseBtn = document.getElementById('pauseBtn');
    const mirrorBtn = document.getElementById('mirrorBtn');
    const modelSelect = document.getElementById('modelSelect');
    const scaleInput = document.getElementById('scaleInput');
    const scaleValue = document.getElementById('scaleValue');
    const confidenceInput = document.getElementById('confidenceInput');
    const confidenceValue = document.getElementById('confidenceValue');
    const loadingElement = document.getElementById('loading');
    
    // Global variables
    let detector = null;
    let streamSocket = null;
    let animationId = null;
    let lastPose = null;
    
    // Initialize the app
    async function init() {
      try {
        await setupPoseDetector();
        setupVideoStream();
        setupEventListeners();
      } catch (error) {
        console.error('Initialization error:', error);
        alert('Failed to initialize: ' + error.message);
      }
    }
    
    // Setup pose detector
    async function setupPoseDetector() {
      const modelConfig = {
        modelType: poseDetection.movenet.modelType[config.modelType === 'thunder' ? 'SINGLEPOSE_THUNDER' : 'SINGLEPOSE_LIGHTNING']
      };
      
      detector = await poseDetection.createDetector(
        poseDetection.SupportedModels.MoveNet, 
        modelConfig
      );
      
      console.log('MoveNet detector initialized with model:', config.modelType);
      loadingElement.style.display = 'none';
    }
    
    // Change the detector model
    async function changeDetectorModel() {
      loadingElement.style.display = 'flex';
      loadingElement.children[1].textContent = 'Changing model...';
      
      try {
        const modelConfig = {
          modelType: poseDetection.movenet.modelType[config.modelType === 'thunder' ? 'SINGLEPOSE_THUNDER' : 'SINGLEPOSE_LIGHTNING']
        };
        
        // Cleanup old detector
        detector = null;
        
        // Create new detector
        detector = await poseDetection.createDetector(
          poseDetection.SupportedModels.MoveNet, 
          modelConfig
        );
        
        console.log('MoveNet detector changed to:', config.modelType);
      } catch (error) {
        console.error('Error changing model:', error);
        alert('Failed to change model: ' + error.message);
      } finally {
        loadingElement.style.display = 'none';
      }
    }
    
    // Setup WebSocket for video stream
    function setupVideoStream() {
      streamSocket = new WebSocket(\`ws://\${window.location.host}/stream\`);
      
      streamSocket.onopen = () => {
        console.log('WebSocket connected');
      };
      
      streamSocket.onmessage = async (event) => {
        try {
          // Check if we're processing a frame already
          if (!config.processingEnabled || stats.processing) {
            return;
          }

          const blob = await event.data.arrayBuffer();
          const imageUrl = URL.createObjectURL(new Blob([blob], { type: 'image/jpeg' }));
          
          // Load the image
          const img = new Image();
          img.onload = async () => {
            // Draw the image on the canvas
            if (config.mirrorView) {
              ctx.save();
              ctx.scale(-1, 1);
              ctx.drawImage(img, -canvas.width, 0, canvas.width, canvas.height);
              ctx.restore();
            } else {
              ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
            }
            
            // Process pose if enabled
            if (config.processingEnabled) {
              stats.processing = true;
              const startTime = performance.now();
              
              try {
                const poses = await detector.estimatePoses(img, {
                  maxPoses: 1,
                  flipHorizontal: false
                });
                
                if (poses.length > 0) {
                  lastPose = poses[0];
                  
                  // Draw skeleton if enabled
                  if (config.showSkeleton) {
                    drawSkeleton(lastPose);
                  }
                }
              } catch (error) {
                console.error('Pose detection error:', error);
              }
              
              stats.processingTime = performance.now() - startTime;
              stats.processing = false;
            }
            
            // Update FPS counter
            updateFps();
            
            // Update stats display
            statsElement.innerHTML = \`
              FPS: \${stats.fps}<br>
              Processing: \${stats.processingTime.toFixed(1)}ms<br>
              Model: \${config.modelType}<br>
              Scale: \${config.scale}
            \`;
            
            // Cleanup
            URL.revokeObjectURL(imageUrl);
          };
          
          img.src = imageUrl;
        } catch (error) {
          console.error('Error processing frame:', error);
        }
      };
      
      streamSocket.onclose = () => {
        console.log('WebSocket connection closed');
        // Try to reconnect after a delay
        setTimeout(setupVideoStream, 5000);
      };
      
      streamSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    }
    
    // Setup event listeners
    function setupEventListeners() {
      toggleSkeletonBtn.addEventListener('click', () => {
        config.showSkeleton = !config.showSkeleton;
        toggleSkeletonBtn.textContent = config.showSkeleton ? 'Hide Skeleton' : 'Show Skeleton';
      });
      
      screenshotBtn.addEventListener('click', () => {
        const dataUrl = canvas.toDataURL('image/png');
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = \`screenshot_\${new Date().toISOString().replace(/:/g, '-')}.png\`;
        link.click();
      });
      
      pauseBtn.addEventListener('click', () => {
        config.processingEnabled = !config.processingEnabled;
        pauseBtn.textContent = config.processingEnabled ? 'Pause Processing' : 'Resume Processing';
      });
      
      mirrorBtn.addEventListener('click', () => {
        config.mirrorView = !config.mirrorView;
        mirrorBtn.textContent = config.mirrorView ? 'Normal View' : 'Mirror View';
      });
      
      modelSelect.addEventListener('change', () => {
        config.modelType = modelSelect.value;
        changeDetectorModel();
      });
      
      scaleInput.addEventListener('input', () => {
        config.scale = parseFloat(scaleInput.value);
        scaleValue.textContent = config.scale.toFixed(1);
      });
      
      confidenceInput.addEventListener('input', () => {
        config.confidenceThreshold = parseFloat(confidenceInput.value);
        confidenceValue.textContent = config.confidenceThreshold.toFixed(2);
      });
    }
    
    // Draw skeleton on canvas
    function drawSkeleton(pose) {
      const keypoints = pose.keypoints;
      
      // Define connections between keypoints for skeleton
      const connections = [
        ['nose', 'left_eye'], ['nose', 'right_eye'],
        ['left_eye', 'left_ear'], ['right_eye', 'right_ear'],
        ['left_shoulder', 'right_shoulder'], 
        ['left_shoulder', 'left_elbow'], ['left_elbow', 'left_wrist'],
        ['right_shoulder', 'right_elbow'], ['right_elbow', 'right_wrist'],
        ['left_shoulder', 'left_hip'], ['right_shoulder', 'right_hip'],
        ['left_hip', 'right_hip'],
        ['left_hip', 'left_knee'], ['left_knee', 'left_ankle'],
        ['right_hip', 'right_knee'], ['right_knee', 'right_ankle']
      ];
      
      // Create lookup for keypoints by name
      const keypointLookup = {};
      keypoints.forEach(keypoint => {
        keypointLookup[keypoint.name] = keypoint;
      });
      
      // Draw keypoints
      keypoints.forEach(keypoint => {
        if (keypoint.score >= config.confidenceThreshold) {
          ctx.beginPath();
          ctx.arc(keypoint.x, keypoint.y, 5, 0, 2 * Math.PI);
          ctx.fillStyle = 'green';
          ctx.fill();
        }
      });
      
      // Draw connections
      ctx.strokeStyle = 'red';
      ctx.lineWidth = 2;
      
      connections.forEach(([name1, name2]) => {
        const keypoint1 = keypointLookup[name1];
        const keypoint2 = keypointLookup[name2];
        
        if (keypoint1 && keypoint2 && 
            keypoint1.score >= config.confidenceThreshold && 
            keypoint2.score >= config.confidenceThreshold) {
          ctx.beginPath();
          ctx.moveTo(keypoint1.x, keypoint1.y);
          ctx.lineTo(keypoint2.x, keypoint2.y);
          ctx.stroke();
        }
      });
    }
    
    // Update FPS counter
    function updateFps() {
      const now = performance.now();
      stats.frameCount++;
      
      if (now - stats.lastFpsUpdateTime >= 1000) {
        stats.fps = Math.round(stats.frameCount * 1000 / (now - stats.lastFpsUpdateTime));
        stats.frameCount = 0;
        stats.lastFpsUpdateTime = now;
      }
    }
    
    // Initialize when the page loads
    window.addEventListener('load', init);
  </script>
</body>
</html>
`);

// Create a simple proxy server to forward the video stream
app.get('/video_feed', async (req, res) => {
  try {
    console.log('Proxying video feed request to robot');
    const response = await fetch(`http://${config.robotIp}:${config.robotPort}/video_feed`);
    
    if (!response.ok) {
      throw new Error(`Failed to fetch video feed: ${response.statusText}`);
    }
    
    res.set({
      'Content-Type': response.headers.get('content-type'),
      'Cache-Control': 'no-store'
    });
    
    response.body.pipe(res);
  } catch (error) {
    console.error('Error proxying video feed:', error);
    res.status(500).send('Error fetching video feed');
  }
});

// Handle WebSocket connections
wss.on('connection', async (ws) => {
  console.log('Client connected');
  
  const videoUrl = `http://${config.robotIp}:${config.robotPort}/video_feed`;
  let abortController = new AbortController();
  
  // Send frames to the client
  const streamFrames = async () => {
    try {
      const response = await fetch(videoUrl, { 
        signal: abortController.signal
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch video stream: ${response.statusText}`);
      }
      
      // Process the MJPEG stream
      let buffer = Buffer.alloc(0);
      
      const reader = response.body.getReader();
      
      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          console.log('Stream ended');
          break;
        }
        
        // Append new data to buffer
        buffer = Buffer.concat([buffer, Buffer.from(value)]);
        
        // Look for JPEG markers
        while (buffer.length > 0) {
          // Find start and end markers of JPEG images
          const startMarker = buffer.indexOf(Buffer.from([0xFF, 0xD8])); // JPEG start
          
          if (startMarker === -1) {
            // No start marker found, clear buffer for next chunk
            buffer = Buffer.alloc(0);
            break;
          }
          
          // Look for end marker after start marker
          const endMarker = buffer.indexOf(Buffer.from([0xFF, 0xD9]), startMarker); // JPEG end
          
          if (endMarker === -1) {
            // End marker not found yet, keep current buffer and wait for more data
            if (startMarker > 0) {
              // Remove data before start marker
              buffer = buffer.subarray(startMarker);
            }
            break;
          }
          
          // Extract JPEG image
          const jpegImage = buffer.subarray(startMarker, endMarker + 2);
          
          // Remove processed data from buffer
          buffer = buffer.subarray(endMarker + 2);
          
          // Send frame to client if connection is still open
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(jpegImage);
          } else {
            // Connection closed, stop streaming
            return;
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Fetch aborted');
      } else {
        console.error('Error streaming frames:', error);
        
        // Send error to client
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ error: error.message }));
        }
        
        // Try to reconnect after a delay
        setTimeout(streamFrames, 5000);
      }
    }
  };
  
  // Start streaming frames
  streamFrames();
  
  // Handle client disconnect
  ws.on('close', () => {
    console.log('Client disconnected');
    abortController.abort();
  });
});

// Start the server
server.listen(config.webPort, () => {
  console.log(`Web interface running at http://localhost:${config.webPort}`);
  console.log('Open this URL in your browser to view the camera feed');
  
  // Open browser automatically
  open(`http://localhost:${config.webPort}`);
});