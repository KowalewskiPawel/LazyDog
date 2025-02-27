#!/usr/bin/env python3
# Enhanced Robot Watchdog with YOLO person detection and Claude-generated warning messages
# Simplified version without light/buzzer controls

import cv2
import time
import asyncio
import websockets
import json
import random
import threading
import os
import datetime
import argparse
import numpy as np
from queue import Queue
import base64
import sys
import anthropic  # pip install anthropic
from dotenv import load_dotenv
from ultralytics import YOLO  # pip install ultralytics

class RobotWatchdogAI:
    def __init__(self, robot_ip, claude_api_key=None):
        # Robot connection settings
        self.robot_ip = robot_ip
        self.ws_url = f"ws://{robot_ip}:8888"
        self.video_url = f"http://{robot_ip}:5000/video_feed"
        self.websocket = None
        
        # YOLO model for person detection
        self.model = None
        try:
            self.model = YOLO("yolov8n.pt")  # Load the smallest model for speed
            print("YOLO model loaded successfully!")
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            print("Falling back to motion detection")
            
        # Person detection settings
        self.person_detected = False
        self.person_count = 0
        self.person_boxes = []
        self.consecutive_person_detections = 0
        self.person_detection_threshold = 3  # How many consecutive detections to trigger
        self.person_detection_cooldown = 30  # Seconds between person alerts
        self.last_person_time = 0
        self.use_yolo = self.model is not None
        
        # Watchdog settings
        self.running = True
        self.watchdog_enabled = False
        self.alerts_enabled = True
        self.is_alerting = False
        self.detection_cooldown = 30  # Seconds between alerts
        self.last_alert_time = 0
        
        # Motion detection fallback
        self.avg = None
        self.motion_detected = False
        self.motion_area = None
        self.consecutive_detections = 0
        self.detection_threshold_count = 3
        self.detection_threshold = 2000
        self.last_motion_time = 0
        
        # New patrol mode settings
        self.patrol_mode = False
        self.patrol_thread = None
        self.patrol_interval = 60  # Time between patrol movements in seconds
        self.last_patrol_time = 0
        self.patrol_sequence = ["forward", "left", "forward", "right", "forward"]
        self.patrol_index = 0
        self.patrol_random = True  # Use random movements for patrol
        
        # AI vision settings
        self.claude_api_key = claude_api_key
        self.claude_client = None
        self.claude_model = "claude-3-7-sonnet-20250219"  # Can fall back to other models
        self.ai_enabled = claude_api_key is not None
        self.last_vision_analysis_time = 0
        self.vision_analysis_interval = 15  # Seconds between vision analysis
        self.intruder_description = ""
        self.generated_warning = ""
        
        # Frame processing
        self.frame_queue = Queue(maxsize=10)
        self.recent_frames = []  # Store recent frames for recording
        self.max_recent_frames = 50  # Max number of frames to keep
        
        # Fallback generic warnings (used when Claude is not available)
        self.generic_warnings = [
            "Intruder detected! The police has been notified.",
            "Warning! This area is under surveillance.",
            "Security alert! The homeowner has been notified.",
            "Unauthorized access detected! Security system activated.",
            "This is a security robot. Please identify yourself."
        ]
        self.last_message_index = -1
        
        # Create folder for saving detection images
        self.save_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "intruder_images")
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Initialize Claude client if API key provided
        if self.claude_api_key:
            self.claude_client = anthropic.Anthropic(api_key=self.claude_api_key)
            print(f"Claude API initialized with model: {self.claude_model}")
        
        print(f"Robot Watchdog initializing...")
        print(f"Robot IP: {robot_ip}")
        print(f"Video stream: {self.video_url}")
        print(f"WebSocket URL: {self.ws_url}")
        print(f"AI Vision: {'Enabled' if self.ai_enabled else 'Disabled'}")
        print(f"Person Detection: {'YOLO' if self.use_yolo else 'Motion-based (fallback)'}")
        
    async def connect_websocket(self):
        """Connect to robot's WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            await self.websocket.send("admin:123456")
            response = await self.websocket.recv()
            print(f"Connected to robot! Response: {response}")
            return True
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.websocket = None
            return False
            
    async def send_command(self, command):
        """Send command to robot via WebSocket"""
        tries = 3  # Number of connection retries
        for attempt in range(tries):
            try:
                if self.websocket is None:
                    await self.connect_websocket()
                    if self.websocket is None:
                        time.sleep(1)
                        continue
                        
                await self.websocket.send(command)
                print(f"Sent command: {command}")
                return await self.websocket.recv()
            except Exception as e:
                print(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                self.websocket = None
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
        return None
    
    async def send_command_multiple(self, command, times=3, delay=0.1):
        """Send a command multiple times with delay to ensure it's received"""
        responses = []
        for _ in range(times):
            response = await self.send_command(command)
            responses.append(response)
            await asyncio.sleep(delay)
        return responses
    
    async def bark_sequence(self, intensity="normal"):
        """Execute a bark with variable patterns"""
        patterns = {
            "short": [(0.1, 0.1)],
            "normal": [(0.2, 0.1), (0.2, 0.1)],
            "excited": [(0.1, 0.05), (0.1, 0.05), (0.2, 0.1)],
            "alert": [(0.3, 0.1), (0.1, 0.05), (0.1, 0.05)]
        }
        
        pattern = patterns.get(intensity, patterns["normal"])
        for duration, pause in pattern:
            await self.send_command_multiple("bark", times=2)
            await asyncio.sleep(duration)
            await self.send_command_multiple("bark", times=2)
            await asyncio.sleep(pause)
        
    def capture_video(self):
        """Capture video frames from robot's stream"""
        print(f"Starting video capture from {self.video_url}")
        
        retry_count = 0
        max_retries = 10
        
        while self.running and retry_count < max_retries:
            try:
                # Open video stream
                cap = cv2.VideoCapture(self.video_url)
                if not cap.isOpened():
                    print(f"Failed to open video stream, retrying ({retry_count+1}/{max_retries})...")
                    retry_count += 1
                    time.sleep(2)
                    continue
                
                print("Video stream successfully opened!")
                retry_count = 0  # Reset on success
                
                # Process frames
                while self.running:
                    ret, frame = cap.read()
                    if not ret:
                        print("Failed to read frame, reconnecting...")
                        break
                    
                    # Store frame in queue
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                    else:
                        try:
                            self.frame_queue.get_nowait()  # Remove old frame
                            self.frame_queue.put(frame)
                        except:
                            pass
                    
                    # Keep a list of recent frames (for recording)
                    self.recent_frames.append(frame.copy())
                    if len(self.recent_frames) > self.max_recent_frames:
                        self.recent_frames.pop(0)
                    
                    # Throttle capture rate
                    time.sleep(0.05)
                    
            except Exception as e:
                print(f"Video capture error: {e}")
                retry_count += 1
                time.sleep(2)
            finally:
                try:
                    cap.release()
                except:
                    pass
                    
        print("Video capture stopped")
    
    def detect_persons_yolo(self, frame):
        """Detect persons in the frame using YOLO"""
        if not self.watchdog_enabled or not self.use_yolo:
            return False
            
        try:
            # Run YOLO detection
            results = self.model(frame, classes=[0])  # Class 0 is person in COCO dataset
            
            # Process results
            self.person_boxes = []
            self.person_count = 0
            
            # Check for people in results
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Extract box coordinates and convert to integers
                    box_coords = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = [int(coord) for coord in box_coords]
                    conf = float(box.conf[0])
                    
                    # Only count high-confidence detections
                    if conf > 0.5:  # Confidence threshold
                        self.person_count += 1
                        self.person_boxes.append((x1, y1, x2, y2, conf))
            
            # Update person detection status
            previous_person_detected = self.person_detected
            self.person_detected = self.person_count > 0
            
            if self.person_detected:
                self.last_person_time = time.time()
                
                # Update consecutive detections
                self.consecutive_person_detections += 1
                
                # Check if we should trigger alert
                if (self.consecutive_person_detections >= self.person_detection_threshold and 
                        self.alerts_enabled and not self.is_alerting):
                    
                    # If Claude is enabled, send frame for analysis
                    if self.ai_enabled and time.time() - self.last_vision_analysis_time > self.vision_analysis_interval:
                        # Run vision analysis in separate thread to avoid blocking
                        analysis_thread = threading.Thread(
                            target=lambda: asyncio.run(self.analyze_frame_with_claude(frame.copy()))
                        )
                        analysis_thread.daemon = True
                        analysis_thread.start()
                    else:
                        # Trigger alert without vision analysis
                        asyncio.run(self.trigger_alert())
                
                # Save image on first detection
                if not previous_person_detected:
                    self.save_detection_image(frame)
            else:
                # Reset consecutive detections after 3 seconds of no person
                if time.time() - self.last_person_time > 3:
                    self.consecutive_person_detections = 0
            
            return self.person_detected
            
        except Exception as e:
            print(f"YOLO detection error: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    def detect_motion(self, frame):
        """Detect motion in the frame using background subtraction"""
        if not self.watchdog_enabled or self.use_yolo:
            return False
            
        try:
            # Convert to grayscale and blur
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)
            
            # Initialize background model if needed
            if self.avg is None:
                print("Initializing background model...")
                self.avg = gray.copy().astype("float")
                return False
                
            # Update background model
            cv2.accumulateWeighted(gray, self.avg, 0.5)
            
            # Compute difference between current frame and background
            frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(self.avg))
            
            # Threshold the delta image and dilate to fill holes
            thresh = cv2.threshold(frameDelta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Check for significant motion
            motion_detected = False
            largest_area = 0
            largest_contour = None
            
            for contour in contours:
                area = cv2.contourArea(contour)
                if area > self.detection_threshold:
                    if area > largest_area:
                        largest_area = area
                        largest_contour = contour
                    motion_detected = True
            
            # Update motion status
            prev_motion = self.motion_detected
            self.motion_detected = motion_detected
            
            if motion_detected and largest_contour is not None:
                # Get bounding box of motion area
                self.motion_area = cv2.boundingRect(largest_contour)
                self.last_motion_time = time.time()
                
                # Update consecutive detections
                self.consecutive_detections += 1
                
                # Check if we should trigger alert
                if (self.consecutive_detections >= self.detection_threshold_count and 
                        self.alerts_enabled and not self.is_alerting):
                    
                    # If AI is enabled, analyze the image first
                    if self.ai_enabled and time.time() - self.last_vision_analysis_time > self.vision_analysis_interval:
                        # Run vision analysis in separate thread to avoid blocking
                        analysis_thread = threading.Thread(
                            target=lambda: asyncio.run(self.analyze_frame_with_claude(frame.copy()))
                        )
                        analysis_thread.daemon = True
                        analysis_thread.start()
                    else:
                        # Trigger alert without vision analysis
                        asyncio.run(self.trigger_alert())
                    
                # Save frame if motion was just detected
                if not prev_motion:
                    self.save_detection_image(frame)
            else:
                # Reset consecutive detections after 3 seconds of no motion
                if time.time() - self.last_motion_time > 3:
                    self.consecutive_detections = 0
            
            return motion_detected
            
        except Exception as e:
            print(f"Motion detection error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def analyze_frame_with_claude(self, frame):
        """Use Claude to analyze the image and identify intruders"""
        if not self.ai_enabled or self.claude_client is None:
            return
            
        try:
            print("Analyzing frame with Claude Vision...")
            self.last_vision_analysis_time = time.time()
            
            # Convert frame to base64 for Claude API
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Step 1: First get intruder description
            try:
                description_message = self.claude_client.messages.create(
                    model=self.claude_model,
                    max_tokens=1024,
                    system="You are a security system that identifies potential intruders. Focus on providing a detailed description of any people you see, especially their clothing, physical appearance, what they're doing, and where they are in the image. This will be used to directly address the intruder.",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Analyze this security camera image of an intruder.
                                    
Please describe the person in detail, focusing on:
1. Their clothing (colors, style)
2. Physical appearance (height, build, hair, etc.)
3. What they appear to be doing
4. Where they are in the frame (near the door, in the hallway, etc.)

Keep your response under 50 words and focus only on describing the person."""
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": image_base64
                                    }
                                }
                            ]
                        }
                    ]
                )
                
                intruder_description = description_message.content[0].text
                print(f"Claude description: {intruder_description}")
                
                # Update intruder description
                self.intruder_description = intruder_description
                
                # Step 2: Generate warning message based on intruder description
                if "no people" not in intruder_description.lower() and len(intruder_description) > 10:
                    warning_message = await self.generate_warning_message(intruder_description)
                    
                    # Trigger alert with the warning message
                    await self.trigger_alert(warning_message)
                else:
                    # No person clearly detected, use generic alert
                    await self.trigger_alert()
                
            except Exception as e:
                print(f"Error with Claude description API: {e}")
                # Fall back to regular alert
                await self.trigger_alert()
            
        except Exception as e:
            print(f"Vision analysis error: {e}")
            await self.trigger_alert()  # Fall back to regular alert
    
    async def generate_warning_message(self, intruder_description):
        """Generate personalized warning message based on intruder description"""
        try:
            # Use Claude to generate a personalized warning message
            warning_message = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=1024,
                system="You are a security robot confronting an intruder. You should generate a direct, authoritative warning message addressing the intruder based on their appearance. Be intimidating but not threatening. Your message should sound like it's being spoken by a security system.",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Based on this description of an intruder, generate a warning message directly addressing them:

{intruder_description}

Generate a security robot warning message that:
1. Directly references the person's appearance (clothing, location, etc.)
2. Sounds authoritative and firm
3. Warns them they are being monitored/recorded
4. Tells them to leave immediately or identify themselves
5. Mentions that authorities have been notified

Keep the message under 100 characters and make it sound like a direct verbal warning from a security robot.
Do NOT use any placeholder expressions like [clothing]. Replace such placeholders with actual details from the description."""
                            }
                        ]
                    }
                ]
            )
            
            generated_warning = warning_message.content[0].text
            print(f"Generated warning: {generated_warning}")
            
            # Store the generated warning
            self.generated_warning = generated_warning
            
            return generated_warning
            
        except Exception as e:
            print(f"Warning generation error: {e}")
            # Fall back to generic warning
            return random.choice(self.generic_warnings)
    
    def save_detection_image(self, frame):
        """Save a detection image to disk"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"intruder_{timestamp}.jpg"
            filepath = os.path.join(self.save_dir, filename)
            
            # Create a copy for saving
            save_frame = frame.copy()
            
            # Add timestamp to the image
            timestamp_text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(save_frame, timestamp_text, (10, save_frame.shape[0] - 10), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
            
            # Draw bounding boxes for persons if using YOLO
            if self.use_yolo and self.person_boxes:
                for box in self.person_boxes:
                    x1, y1, x2, y2, conf = box
                    cv2.rectangle(save_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Person: {conf:.2f}"
                    cv2.putText(save_frame, label, (x1, y1 - 10), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Save image
            cv2.imwrite(filepath, save_frame)
            print(f"Saved detection image to {filepath}")
            
            # Save a short video clip if we have enough frames
            if len(self.recent_frames) > 10:
                self.save_detection_video(timestamp)
                
        except Exception as e:
            print(f"Error saving detection image: {e}")
            
    def save_detection_video(self, timestamp):
        """Save a short video of the detection"""
        try:
            filename = f"intruder_{timestamp}.mp4"
            filepath = os.path.join(self.save_dir, filename)
            
            # Get video properties from the first frame
            height, width = self.recent_frames[0].shape[:2]
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(filepath, fourcc, 10, (width, height))
            
            # Write frames to video
            for frame in self.recent_frames:
                out.write(frame)
                
            # Release video writer
            out.release()
            print(f"Saved detection video to {filepath}")
            
        except Exception as e:
            print(f"Error saving detection video: {e}")
    
    async def trigger_alert(self, warning_message=None):
        """Trigger alert when person is detected"""
        current_time = time.time()
        
        # Only alert if cooldown period has passed
        if current_time - self.last_alert_time < self.detection_cooldown:
            return
            
        # Mark as alerting and update last alert time
        self.is_alerting = True
        self.last_alert_time = current_time
        
        # Pause patrol mode during alert
        was_patrolling = self.patrol_mode
        if was_patrolling:
            self.toggle_patrol_mode(False)
        
        # Start alert sequence in a separate thread
        alert_thread = threading.Thread(
            target=lambda: asyncio.run(self.alert_sequence(warning_message, was_patrolling))
        )
        alert_thread.daemon = True
        alert_thread.start()
    
    async def alert_sequence(self, warning_message=None, resume_patrol=False):
        """Run the alert sequence"""
        try:
            print("⚠️ ALERT! Intruder detected!")
            
            # First, make the robot bark
            await self.bark_sequence("alert")
            
            # Use provided warning message or generic fallback
            if not warning_message:
                # Use generic warning message
                warning_message = random.choice(self.generic_warnings)
            
            # Speak the warning message directly addressing the intruder
            print(f"Speaking: {warning_message}")
            await self.send_command(f"speak:{warning_message}")
            
            # Enhanced movement sequence - make the robot look more alert
            # Turn head to look for intruder
            await self.send_command("lookLeft")
            await asyncio.sleep(0.5)
            await self.send_command("LRstop")
            await asyncio.sleep(0.5)
            await self.send_command("lookRight")
            await asyncio.sleep(0.5)
            await self.send_command("LRstop")
            
            # Turn body to face intruder
            direction = random.choice(["left", "right"])
            await self.send_command(direction)
            await asyncio.sleep(0.8)
            await self.send_command("TS")
            
            # Additional personalized message
            second_message = random.choice([
                "I've already called security.",
                "This area is off-limits. Leave now.",
                "Your face has been recorded.",
                "Don't move! Authorities are on their way.",
                "Security system activated. Please leave immediately."
            ])
            await self.send_command(f"speak:{second_message}")
            
            # Bark again after turning
            await self.bark_sequence("excited")
            
            # Pause before finishing alert
            await asyncio.sleep(3.0)
            
            self.is_alerting = False
            
            # Resume patrol if it was active before
            if resume_patrol:
                self.toggle_patrol_mode(True)
            
        except Exception as e:
            print(f"Alert sequence error: {e}")
            self.is_alerting = False
    
    def enable_watchdog(self):
        """Enable watchdog mode"""
        self.watchdog_enabled = True
        self.consecutive_detections = 0
        self.consecutive_person_detections = 0
        self.avg = None  # Reset background model
        print("Watchdog mode enabled")
        
    def disable_watchdog(self):
        """Disable watchdog mode"""
        self.watchdog_enabled = False
        self.toggle_patrol_mode(False)  # Also disable patrol mode
        print("Watchdog mode disabled")
        
    def toggle_alerts(self, enable):
        """Toggle alert system"""
        self.alerts_enabled = enable
        print(f"Alerts {'enabled' if enable else 'disabled'}")
    
    def toggle_patrol_mode(self, enable):
        """Toggle patrol mode on/off"""
        if enable and not self.patrol_mode:
            self.patrol_mode = True
            print("Patrol mode enabled")
            
            # Start patrol thread if watchdog is enabled
            if self.watchdog_enabled:
                self.patrol_thread = threading.Thread(target=lambda: asyncio.run(self.patrol_sequence_loop()))
                self.patrol_thread.daemon = True
                self.patrol_thread.start()
                
        elif not enable and self.patrol_mode:
            self.patrol_mode = False
            print("Patrol mode disabled")
            
            # Patrol thread will exit by itself due to the flag check
            
    async def patrol_sequence_loop(self):
        """Run the patrol sequence in a loop"""
        print("Starting patrol sequence loop")
        
        # Define a set of possible patrol movements
        patrol_movements = [
            {"movement": "forward", "duration": 1.5},
            {"movement": "left", "duration": 0.8},
            {"movement": "right", "duration": 0.8},
            {"movement": "lookLeft", "duration": 0.5},
            {"movement": "lookRight", "duration": 0.5}
        ]
        
        # Run patrol loop until patrol mode is disabled
        while self.running and self.patrol_mode and self.watchdog_enabled and not self.is_alerting:
            try:
                current_time = time.time()
                
                # Check if it's time for a patrol movement
                if current_time - self.last_patrol_time >= self.patrol_interval:
                    print("Performing patrol movement")
                    self.last_patrol_time = current_time
                    
                    # Announce patrol
                    await self.send_command("speak:Patrolling the area")
                    
                    # Choose movement pattern
                    if self.patrol_random:
                        # Random patrol pattern
                        # Pick 2-3 movements
                        num_movements = random.randint(2, 3)
                        for _ in range(num_movements):
                            # Check if patrol is still active before each movement
                            if not (self.patrol_mode and self.watchdog_enabled and not self.is_alerting):
                                break
                                
                            # Choose random movement
                            move = random.choice(patrol_movements)
                            
                            # Execute movement
                            await self.send_command(move["movement"])
                            await asyncio.sleep(move["duration"])
                            
                            # Stop movement
                            if move["movement"] in ["forward", "backward"]:
                                await self.send_command("DS")
                            elif move["movement"] in ["left", "right"]:
                                await self.send_command("TS")
                            elif move["movement"] in ["lookLeft", "lookRight"]:
                                await self.send_command("LRstop")
                                
                            await asyncio.sleep(0.5)  # Pause between movements
                    else:
                        # Sequential patrol pattern
                        if self.patrol_index >= len(self.patrol_sequence):
                            self.patrol_index = 0
                            
                        # Get next movement in sequence
                        movement = self.patrol_sequence[self.patrol_index]
                        self.patrol_index += 1
                        
                        # Perform the movement
                        await self.send_command(movement)
                        await asyncio.sleep(1.0)
                        
                        # Stop movement
                        if movement in ["forward", "backward"]:
                            await self.send_command("DS")
                        elif movement in ["left", "right"]:
                            await self.send_command("TS")
                    
                    # Look around after patrol movement
                    await self.send_command("lookLeft")
                    await asyncio.sleep(0.5)
                    await self.send_command("LRstop")
                    await asyncio.sleep(0.3)
                    await self.send_command("lookRight")
                    await asyncio.sleep(0.5)
                    await self.send_command("LRstop")
                    
                    # Occasionally bark during patrol
                    if random.random() < 0.3:  # 30% chance to bark
                        await self.bark_sequence("short")
                
                # Sleep for a bit to avoid busy waiting
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Patrol error: {e}")
                await asyncio.sleep(5)  # Sleep longer on error
        
        print("Patrol sequence loop ended")
        
    def process_frames(self):
        """Process frames in the queue"""
        print("Starting frame processing...")
        
        display_window = True  # Set to False to disable GUI
        
        if display_window:
            cv2.namedWindow("Watchdog Monitor", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Watchdog Monitor", 800, 600)
        
        while self.running:
            try:
                if not self.frame_queue.empty():
                    frame = self.frame_queue.get()
                    
                    # Skip processing if frame is None
                    if frame is None:
                        continue
                    
                    # Clone the frame for display
                    display_frame = frame.copy()
                    
                    # Detect intruders if watchdog is enabled
                    if self.watchdog_enabled:
                        if self.use_yolo:
                            # Use YOLO for person detection
                            person_detected = self.detect_persons_yolo(display_frame)
                            
                            # Draw bounding boxes for detected persons
                            if person_detected and self.person_boxes:
                                for box in self.person_boxes:
                                    x1, y1, x2, y2, conf = box
                                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                    label = f"Person: {conf:.2f}"
                                    cv2.putText(display_frame, label, (x1, y1 - 10), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        else:
                            # Use motion detection as fallback
                            motion_detected = self.detect_motion(display_frame)
                            
                            # Draw motion area if detected
                            if motion_detected and self.motion_area:
                                x, y, w, h = self.motion_area
                                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        
                        # Add status text
                        status_text = f"Watchdog: {'ENABLED' if self.watchdog_enabled else 'DISABLED'}"
                        cv2.putText(display_frame, status_text, (10, 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        alert_text = f"Alerts: {'ON' if self.alerts_enabled else 'OFF'}"
                        cv2.putText(display_frame, alert_text, (10, 60), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        ai_text = f"AI Vision: {'ON' if self.ai_enabled else 'OFF'}"
                        cv2.putText(display_frame, ai_text, (10, 90), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        detection_text = f"Detection: {'YOLO' if self.use_yolo else 'Motion'}"
                        cv2.putText(display_frame, detection_text, (10, 120), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        patrol_text = f"Patrol Mode: {'ON' if self.patrol_mode else 'OFF'}"
                        cv2.putText(display_frame, patrol_text, (10, 150), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        if self.use_yolo and self.person_detected:
                            person_text = f"Person Detected! Count: {self.person_count}, Consecutive: {self.consecutive_person_detections}"
                            cv2.putText(display_frame, person_text, (10, 180), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        elif not self.use_yolo and self.motion_detected:
                            motion_text = f"Motion Detected! Consecutive: {self.consecutive_detections}"
                            cv2.putText(display_frame, motion_text, (10, 180), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                                        
                        # Show intruder description if available
                        if self.intruder_description and "no people" not in self.intruder_description.lower():
                            # Split into multiple lines if too long
                            words = self.intruder_description.split()
                            lines = []
                            current_line = []
                            
                            for word in words:
                                current_line.append(word)
                                if len(' '.join(current_line)) > 60:  # Line length limit
                                    lines.append(' '.join(current_line[:-1]))
                                    current_line = [word]
                            
                            if current_line:
                                lines.append(' '.join(current_line))
                                
                            # Display description lines
                            cv2.putText(display_frame, "Description:", (10, 210), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                            for i, line in enumerate(lines):
                                cv2.putText(display_frame, line, (10, 240 + i*30), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                        
                        # Show generated warning if available
                        if self.generated_warning:
                            # Split into multiple lines if too long
                            words = self.generated_warning.split()
                            lines = []
                            current_line = []
                            
                            for word in words:
                                current_line.append(word)
                                if len(' '.join(current_line)) > 60:  # Line length limit
                                    lines.append(' '.join(current_line[:-1]))
                                    current_line = [word]
                            
                            if current_line:
                                lines.append(' '.join(current_line))
                                
                            # Display warning lines
                            y_offset = 240
                            if self.intruder_description:
                                # Adjust offset if description is shown
                                y_offset = 240 + 30 * (len(self.intruder_description.split('\n')) + 1)
                                
                            cv2.putText(display_frame, "Warning Message:", (10, y_offset), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                            for i, line in enumerate(lines):
                                cv2.putText(display_frame, line, (10, y_offset + 30 + i*30), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    else:
                        status_text = "Watchdog: DISABLED"
                        cv2.putText(display_frame, status_text, (10, 30), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    # Add help text at the bottom
                    help_text = "Controls: [e]nable/[d]isable watchdog, [a]lerts toggle, [p]atrol toggle, [q]uit"
                    cv2.putText(display_frame, help_text, (10, display_frame.shape[0] - 20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
                    # Display the frame
                    if display_window:
                        cv2.imshow("Watchdog Monitor", display_frame)
                        key = cv2.waitKey(1) & 0xFF
                        
                        # Handle key presses
                        if key == ord('q'):
                            self.running = False
                        elif key == ord('e'):
                            self.enable_watchdog()
                        elif key == ord('d'):
                            self.disable_watchdog()
                        elif key == ord('a'):
                            self.toggle_alerts(not self.alerts_enabled)
                        elif key == ord('p'):
                            self.toggle_patrol_mode(not self.patrol_mode)
                        elif key == ord('b'):
                            # Manual bark for testing
                            asyncio.run(self.bark_sequence("excited"))
                
                # Sleep briefly to avoid excessive CPU usage
                time.sleep(0.03)
                
            except Exception as e:
                print(f"Frame processing error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
        
        # Clean up
        if display_window:
            cv2.destroyAllWindows()
        print("Frame processing stopped")
    
    def run(self):
        """Main method to run the watchdog"""
        try:
            # Start video capture thread
            video_thread = threading.Thread(target=self.capture_video)
            video_thread.daemon = True
            video_thread.start()
            
            # Start with a greeting message
            asyncio.run(self.send_command("speak:Security watchdog initialized and ready!"))
            
            # Start frame processing
            print("\nStarting watchdog monitor...")
            print("Press 'e' to enable watchdog")
            print("Press 'd' to disable watchdog")
            print("Press 'a' to toggle alerts")
            print("Press 'p' to toggle patrol mode")
            print("Press 'b' to trigger bark (test)")
            print("Press 'q' to quit")
            
            # Process frames (this will block until quit)
            self.process_frames()
            
        except KeyboardInterrupt:
            print("\nStopping watchdog monitor...")
        finally:
            self.running = False
            
            # Close WebSocket connection
            if self.websocket:
                asyncio.run(self.websocket.close())
            
            print("Watchdog monitor stopped")

def main():
    load_dotenv()  
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Robot Watchdog with Prompt-Generated Warning Messages")
    parser.add_argument("--ip", type=str, default=None,
                        help="Robot IP address (default: from ROBOT_IP_ADDRESS env var)")
    parser.add_argument("--enable", action="store_true", 
                        help="Enable watchdog mode on startup")
    parser.add_argument("--patrol", action="store_true",
                        help="Enable patrol mode on startup")
    parser.add_argument("--claude-key", type=str, default=None,
                        help="Claude API key for vision analysis (default: from CLAUDE_API_KEY env var)")
    parser.add_argument("--no-yolo", action="store_true",
                        help="Disable YOLO and use motion detection instead")
    parser.add_argument("--nodisplay", action="store_true",
                        help="Run without display window (headless mode)")
    
    args = parser.parse_args()
    
    # Load Claude API key from environment if not provided
    claude_api_key = args.claude_key
    if claude_api_key is None:
        claude_api_key = os.environ.get("CLAUDE_API_KEY")
    
    # Load robot IP from environment if not provided
    robot_ip = args.ip
    if robot_ip is None:
        robot_ip = os.environ.get("ROBOT_IP_ADDRESS")
        if not robot_ip:
            robot_ip = input("Enter robot IP address: ")
    
    # Create and run watchdog
    watchdog = RobotWatchdogAI(robot_ip, claude_api_key)
    
    # Disable YOLO if requested
    if args.no_yolo:
        watchdog.use_yolo = False
    
    # Enable watchdog if requested
    if args.enable:
        watchdog.enable_watchdog()
        
    # Enable patrol mode if requested
    if args.patrol and args.enable:
        watchdog.toggle_patrol_mode(True)
    
    # Run the watchdog
    watchdog.run()

if __name__ == "__main__":
    main()