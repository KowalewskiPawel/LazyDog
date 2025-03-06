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

// Global robot WebSocket connection
let robotSocket = null;
let robotSocketReconnectInterval = null;
let robotSocketAuthenticated = false;

// Initialize the robot WebSocket connection
async function initRobotWebSocket() {
  // Clear any existing reconnection timer
  if (robotSocketReconnectInterval) {
    clearInterval(robotSocketReconnectInterval);
    robotSocketReconnectInterval = null;
  }

  // Close existing socket if any
  if (robotSocket) {
    robotSocket.close();
    robotSocket = null;
    robotSocketAuthenticated = false;
  }

  const wsUrl = `ws://${config.robotIp}:8888`;
  console.log(`Connecting to robot WebSocket at ${wsUrl}`);

  try {
    robotSocket = new WebSocket(wsUrl);

    robotSocket.onopen = () => {
      console.log('Robot WebSocket connection established, authenticating...');

      // Send authentication immediately after connection
      robotSocket.send("admin:123456");
    };

    robotSocket.onmessage = (event) => {
      try {
        console.log('Received from robot:', event.data);

        // Check if this is the authentication response
        if (!robotSocketAuthenticated) {
          // Mark as authenticated after receiving the first response
          robotSocketAuthenticated = true;
          console.log('Robot WebSocket authenticated successfully');
        }
      } catch (error) {
        console.error('Error processing robot response:', error);
      }
    };

    robotSocket.onerror = (error) => {
      console.error('Robot WebSocket error:', error);
    };

    robotSocket.onclose = () => {
      console.log('Robot WebSocket connection closed');
      robotSocket = null;
      robotSocketAuthenticated = false;

      // Set up reconnection if not already in progress
      if (!robotSocketReconnectInterval) {
        robotSocketReconnectInterval = setInterval(() => {
          console.log('Attempting to reconnect to robot WebSocket...');
          initRobotWebSocket();
        }, 5000); // Try to reconnect every 5 seconds
      }
    };
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);

    // Set up reconnection if not already in progress
    if (!robotSocketReconnectInterval) {
      robotSocketReconnectInterval = setInterval(() => {
        console.log('Attempting to reconnect to robot WebSocket...');
        initRobotWebSocket();
      }, 5000); // Try to reconnect every 5 seconds
    }
  }
}

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// Create a proxy route for video feed
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

app.get('/robot-status', (req, res) => {
  res.json({
    connected: robotSocket !== null && robotSocket.readyState === WebSocket.OPEN,
    authenticated: robotSocketAuthenticated
  });
});

// Robot command endpoint using WebSocket
app.post('/camera-control', async (req, res) => {
  const { command } = req.body;

  if (!command) {
    return res.status(400).json({ success: false, message: 'No command provided' });
  }

  console.log(`Processing robot command: ${command}`);

  try {
    // Map the internal command names to robot commands if needed
    let robotCommand;

    // Simple mapping to keep the commands consistent
    switch (command) {
      case 'up':
        robotCommand = 'up';
        break;
      case 'forward':
        robotCommand = 'forward';
        break;
      case 'down':
        robotCommand = 'down';
        break;
      case 'backward':
        robotCommand = 'backward';
        break;
      case 'lookleft':
        robotCommand = 'lookleft';
        break;
      case 'left':
        robotCommand = 'left';
        break;
      case 'lookright':
        robotCommand = 'lookright';
        break;
      case 'right':
        robotCommand = 'right';
        break;
      case 'UDstop':
        robotCommand = 'UDstop';
        break;
      case 'LRstop':
        robotCommand = 'LRstop';
        break;
      case 'stop':
        robotCommand = 'DS';
        break;
      case 'stop-side':
        robotCommand = 'TS';
        break;
      case 'steadyMode':
        robotCommand = 'steady';
        break;
      // Keep other commands as they are
      default:
        robotCommand = command;
    }

    // Check if WebSocket is connected and authenticated
    if (!robotSocket || robotSocket.readyState !== WebSocket.OPEN) {
      console.log('WebSocket not connected, attempting to reconnect...');
      initRobotWebSocket();

      // Wait a short time for connection
      await new Promise(resolve => setTimeout(resolve, 1000));

      // If still not connected, return error
      if (!robotSocket || robotSocket.readyState !== WebSocket.OPEN) {
        return res.status(503).json({
          success: false,
          message: 'Robot WebSocket connection not available. Attempting to reconnect.'
        });
      }
    }

    // Check if authenticated
    if (!robotSocketAuthenticated) {
      return res.status(401).json({
        success: false,
        message: 'Robot WebSocket not authenticated yet. Please try again in a moment.'
      });
    }

    // Send the command through WebSocket
    console.log(`Sending robot command via WebSocket: ${robotCommand}`);
    robotSocket.send(robotCommand);

    return res.json({
      success: true,
      message: `Command '${robotCommand}' sent to robot`
    });
  } catch (error) {
    console.error('Error sending command to robot:', error);
    return res.status(500).json({
      success: false,
      message: `Error: ${error.message}`
    });
  }
});

// Add these functions to your existing posture-cam.js file

// Function to make the robot bark
function makeRobotBark() {
  if (!robotSocket || robotSocket.readyState !== WebSocket.OPEN || !robotSocketAuthenticated) {
    console.log('Cannot bark: WebSocket not connected or authenticated');
    return false;
  }

  console.log('Making robot bark at slouching user');
  robotSocket.send('bark');

  // Turn off buzzer after short delay (200ms for a quick bark)
  setTimeout(() => {
    robotSocket.send('bark');
  }, 200);

  return true;
}

// Create a new endpoint for barking
app.post('/robot-bark', (req, res) => {
  const success = makeRobotBark();
  res.json({
    success,
    message: success ? 'Robot barked successfully' : 'Failed to make robot bark'
  });
});

// Create a new bark sequence function (for more complex barking patterns)
function barkSequence(pattern = 'alert') {
  if (!robotSocket || robotSocket.readyState !== WebSocket.OPEN || !robotSocketAuthenticated) {
    console.log('Cannot bark sequence: WebSocket not connected or authenticated');
    return false;
  }

  const patterns = {
    short: [[0.1, 0.1]],
    normal: [[0.2, 0.1], [0.2, 0.1]],
    excited: [[0.1, 0.05], [0.1, 0.05], [0.2, 0.1]],
    alert: [[0.3, 0.1], [0.1, 0.05], [0.1, 0.05]]
  };

  const selectedPattern = patterns[pattern] || patterns.normal;

  // Execute bark sequence
  let currentIndex = 0;

  function executeNextBark() {
    if (currentIndex >= selectedPattern.length) return;

    const [duration, pause] = selectedPattern[currentIndex];
    robotSocket.send('bark');

    setTimeout(() => {
      robotSocket.send('bark');
      currentIndex++;

      if (currentIndex < selectedPattern.length) {
        setTimeout(executeNextBark, pause * 1000);
      }
    }, duration * 1000);
  }

  executeNextBark();
  return true;
}

// AI Integration endpoint
// Load environment variables
require('dotenv').config();

// AI Integration endpoint
app.post('/ai-response', async (req, res) => {
  const { prompt, model, personality } = req.body;
  
  try {
    let response;
    
    // Get API key from environment variables
    const claudeApiKey = process.env.CLAUDE_API_KEY;
    const grokApiKey = process.env.GROK_API_KEY;
    
    if (model === 'claude') {
      if (!claudeApiKey) {
        throw new Error('Claude API key not configured on server');
      }
      response = await getClaudeResponse(prompt, claudeApiKey, personality);
    } else if (model === 'grok') {
      if (!grokApiKey) {
        throw new Error('Grok API key not configured on server');
      }
      response = await getGrokResponse(prompt, grokApiKey, personality);
    } else {
      throw new Error('Unsupported model');
    }
    
    return res.json({
      success: true,
      response
    });
  } catch (error) {
    console.error('AI response error:', error);
    return res.status(500).json({
      success: false,
      message: `Error: ${error.message}`
    });
  }
});

// ... existing code ...

// Add a new endpoint for voice transcription and AI response
app.post('/voice-interaction', async (req, res) => {
  const { audioBlob, imageData, transcription } = req.body;
  
  try {
    // Get API key from environment variables
    const claudeApiKey = process.env.CLAUDE_API_KEY;
    
    if (!claudeApiKey) {
      throw new Error('Claude API key not configured on server');
    }
    
    // Get response from Claude with image and voice transcription
    const response = await getClaudeVoiceResponse(transcription, imageData, claudeApiKey);
    
    // Format response for robot speech
    const robotResponse = response.startsWith('speak:') ? response : `speak:${response}`;
    
    // Send the response to the robot
    if (robotSocket && robotSocket.readyState === WebSocket.OPEN && robotSocketAuthenticated) {
      robotSocket.send(robotResponse);
    }
    
    return res.json({
      success: true,
      response,
      originalTranscription: transcription
    });
  } catch (error) {
    console.error('Voice interaction error:', error);
    return res.status(500).json({
      success: false,
      message: `Error: ${error.message}`
    });
  }
});

// Claude API implementation with image and voice transcription support
async function getClaudeVoiceResponse(transcription, imageData, apiKey) {
  const anthropic = require('@anthropic-ai/sdk');
  const client = new anthropic.Anthropic({
    apiKey: apiKey
  });
  
  try {
    // Prepare messages with text and image
    const messages = [
      {
        role: 'user',
        content: [
          {
            type: 'text',
            text: `The user asked: "${transcription}". 
            
            If they're asking about their posture, provide a helpful analysis based on the image.
            If they're asking a general question, answer it appropriately.
            
            Format your response as a speech command that I can send directly to my robot. The format must be exactly "speak:YOUR MESSAGE HERE". Keep the response concise (under 150 characters).`
          }
        ]
      }
    ];
    
    // Add image if provided
    if (imageData) {
      // Remove the data:image/jpeg;base64, prefix if present
      const base64Image = imageData.replace(/^data:image\/\w+;base64,/, '');
      
      messages[0].content.push({
        type: 'image',
        source: {
          type: 'base64',
          media_type: 'image/jpeg',
          data: base64Image
        }
      });
    }
    
    // Use the current most appropriate model
    const response = await client.messages.create({
      model: 'claude-3-7-sonnet-20250219',
      max_tokens: 200,
      system: "You are a helpful robot assistant who provides concise and friendly responses. When analyzing posture, be specific but brief.",
      messages: messages
    });
    
    let responseText = response.content[0].text.trim();
    
    // Ensure response is in the correct format
    if (!responseText.startsWith('speak:')) {
      responseText = 'speak:' + responseText;
    }
    
    // Limit response length
    if (responseText.length > 158) { // "speak:" plus 150 characters
      responseText = responseText.substring(0, 158);
    }
    
    return responseText;
  } catch (error) {
    console.error('Claude API error:', error);
    // Fallback response if API call fails
    return 'speak:Sorry, I encountered an error processing your request.';
  }
}

// ... existing code ...
// AI Integration endpoint with image support
app.post('/claude-posture-response', async (req, res) => {
  const { postureIssues, imageData, personality } = req.body;
  
  try {
    // Get API key from environment variables
    const claudeApiKey = process.env.CLAUDE_API_KEY;
    
    if (!claudeApiKey) {
      throw new Error('Claude API key not configured on server');
    }
    
    // Get response from Claude with image analysis
    const response = await getClaudePostureResponse(postureIssues, imageData, claudeApiKey, personality);
    
    return res.json({
      success: true,
      response
    });
  } catch (error) {
    console.error('Claude posture analysis error:', error);
    return res.status(500).json({
      success: false,
      message: `Error: ${error.message}`
    });
  }
});

// Claude API implementation with image support
async function getClaudePostureResponse(postureIssues, imageData, apiKey, personality) {
  const anthropic = require('@anthropic-ai/sdk');
  const client = new anthropic.Anthropic({
    apiKey: apiKey
  });
  
  const systemPrompt = getSystemPrompt(personality);
  
  try {
    // Prepare messages with text and image
    const messages = [
      {
        role: 'user',
        content: [
          {
            type: 'text',
            text: `Analyze this posture detection image. The system detected these posture issues: ${postureIssues.join(', ')}. 
            
            Please create a response that I can send directly to my robot as a speech command. The command format must be exactly "speak:YOUR MESSAGE HERE" and should be no more than 100 characters long. Do not include any explanation or additional text - only provide the exact command to be sent.`
          }
        ]
      }
    ];
    
    // Add image if provided
    if (imageData) {
      // Remove the data:image/jpeg;base64, prefix if present
      const base64Image = imageData.replace(/^data:image\/\w+;base64,/, '');
      
      messages[0].content.push({
        type: 'image',
        source: {
          type: 'base64',
          media_type: 'image/jpeg',
          data: base64Image
        }
      });
    }
    
    // Use the current most appropriate model
    const response = await client.messages.create({
      model: 'claude-3-7-sonnet-20250219', // Or use a different available model
      max_tokens: 150,
      system: systemPrompt,
      messages: messages
    });
    
    let responseText = response.content[0].text.trim();
    
    // Ensure response is in the correct format
    if (!responseText.startsWith('speak:')) {
      responseText = 'speak:' + responseText;
    }
    
    // Limit response length
    if (responseText.length > 108) { // "speak:" plus 100 characters
      responseText = responseText.substring(0, 108);
    }
    
    return responseText;
  } catch (error) {
    console.error('Claude API error:', error);
    // Fallback response if API call fails
    return 'speak:Please fix your posture.';
  }
}

// Grok API implementation
async function getGrokResponse(prompt, apiKey, personality) {
  // Implementation would depend on Grok's API structure
  // This is a placeholder since Grok's API isn't widely available yet
  const response = await fetch('https://api.grok.ai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: 'grok-1',
      messages: [
        { role: 'system', content: getSystemPrompt(personality) },
        { role: 'user', content: prompt }
      ],
      max_tokens: 150
    })
  });

  const data = await response.json();
  return data.choices[0].message.content;
}

// Get system prompt based on personality
function getSystemPrompt(personality) {
  switch (personality) {
    case 'coach':
      return 'You are a supportive posture coach for a robot that monitors the user\'s posture. Provide short, encouraging reminders about sitting up straight. Keep responses under 100 characters.';
    case 'friendly':
      return 'You are a friendly robot companion who gently reminds users about good posture. Be warm and supportive. Keep responses under 100 characters.';
    case 'strict':
      return 'You are a strict posture monitor that firmly reminds users to fix their posture immediately. Be direct but not rude. Keep responses under 100 characters.';
    case 'random':
      return 'You are a creative robot assistant. Generate unexpected, funny, or surprising ways to remind someone about their posture. Also suggest random robot movements that might help. Be concise and keep responses under 100 characters.';
    default:
      return 'You are a posture monitoring robot. Provide short reminders about good posture. Keep responses under 100 characters.';
  }
}

// Create a new endpoint for bark sequences
app.post('/robot-bark-sequence', (req, res) => {
  const { pattern } = req.body;
  const success = barkSequence(pattern);
  res.json({
    success,
    message: success ? `Robot bark sequence '${pattern}' started` : 'Failed to start bark sequence'
  });
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

// Initialize WebSocket when server starts
server.listen(config.webPort, () => {
  console.log(`Web interface running at http://localhost:${config.webPort}`);
  console.log('Open this URL in your browser to view the camera feed');

  // Initialize robot WebSocket connection
  initRobotWebSocket();

  // Open browser automatically
  open(`http://localhost:${config.webPort}`);
});