#!/usr/bin/env python3
# Enhanced Robot Watchdog with YOLO person detection, Claude-generated warnings, and intruder tracking

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
        
        # NEW: Intruder tracking settings
        self.tracking_enabled = True
        self.track_duration = 60  # How long to track an intruder (seconds)
        self.tracking_started = 0
        self.is_tracking = False
        self.target_person_box = None
        self.frame_width = 640  # Default frame width
        self.frame_height = 480  # Default frame height
        self.tracking_distance_threshold = 100  # Pixel distance to consider person "close"
        self.person_lost_threshold = 10  # Frames without detection before considering person lost
        self.frames_without_person = 0
        self.last_movement_command = None
        self.last_movement_time = 0
        self.movement_cooldown = 1.0  # Seconds between movement commands
        
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
        
        # Patrol mode settings
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
        self.claude_model = "claude-3-7-sonnet-20250219"
        self.ai_enabled = claude_api_key is not None
        self.last_vision_analysis_time = 0
        self.vision_analysis_interval = 15  # Seconds between vision analysis
        self.intruder_description = ""
        self.generated_warning = ""
        
        # NEW: Intruder behavior analysis
        self.intruder_behavior = "unknown"  # unknown, approaching, retreating, stationary
        self.previous_positions = []  # Store previous positions to analyze movement
        self.max_positions = 10
        self.behavior_confidence = 0
        self.intruder_distance = "unknown"  # far, medium, close
        
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
        print(f"Intruder Tracking: {'Enabled' if self.tracking_enabled else 'Disabled'}")
        
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
            await self.send_command("bark")  # Using 'buzzer on' as bark
            await asyncio.sleep(duration)
            await self.send_command("bark")
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
                    
                    # Update frame dimensions
                    self.frame_width = frame.shape[1]
                    self.frame_height = frame.shape[0]
                    
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
                self.frames_without_person = 0
                
                # Update consecutive detections
                self.consecutive_person_detections += 1
                
                # If tracking is enabled, select the best person to track
                if self.tracking_enabled and self.consecutive_person_detections >= self.person_detection_threshold:
                    self.select_target_person()
                    
                # Analyze intruder behavior if we have a target
                if self.target_person_box:
                    self.analyze_intruder_behavior()
                
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
                # Increment frames without person
                self.frames_without_person += 1
                
                # Reset consecutive detections after 3 seconds of no person
                if time.time() - self.last_person_time > 3:
                    self.consecutive_person_detections = 0
                
                # If tracking and person lost for too long, stop tracking
                if self.is_tracking and self.frames_without_person > self.person_lost_threshold:
                    print("Person lost while tracking, stopping tracking.")
                    self.is_tracking = False
                    self.target_person_box = None
                    asyncio.run(self.send_command("DS"))  # Stop forward/backward
                    asyncio.run(self.send_command("TS"))  # Stop left/right
            
            return self.person_detected
            
        except Exception as e:
            print(f"YOLO detection error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def select_target_person(self):
        """Select the best person to track based on size and position"""
        if not self.person_boxes:
            return
        
        # If we're not tracking yet, start tracking the largest person
        if not self.is_tracking:
            # Find the largest person (by area)
            largest_area = 0
            largest_box = None
            
            for box in self.person_boxes:
                x1, y1, x2, y2, conf = box
                area = (x2 - x1) * (y2 - y1)
                
                if area > largest_area:
                    largest_area = area
                    largest_box = box
            
            if largest_box:
                self.target_person_box = largest_box
                self.is_tracking = True
                self.tracking_started = time.time()
                print(f"Started tracking person at {self.target_person_box}")
        else:
            # We're already tracking, find the closest person to our current target
            if self.target_person_box:
                # Get center of current target
                x1, y1, x2, y2, _ = self.target_person_box
                target_cx = (x1 + x2) // 2
                target_cy = (y1 + y2) // 2
                
                # Find closest person
                closest_dist = float('inf')
                closest_box = None
                
                for box in self.person_boxes:
                    x1, y1, x2, y2, conf = box
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    
                    # Calculate Euclidean distance
                    dist = np.sqrt((cx - target_cx)**2 + (cy - target_cy)**2)
                    
                    if dist < closest_dist:
                        closest_dist = dist
                        closest_box = box
                
                if closest_box:
                    self.target_person_box = closest_box
            
            # Check if we should stop tracking based on duration
            if time.time() - self.tracking_started > self.track_duration:
                print(f"Tracking duration exceeded, stopping tracking.")
                self.is_tracking = False
                self.target_person_box = None
    
    def analyze_intruder_behavior(self):
        """Analyze intruder behavior based on position and movement"""
        if not self.target_person_box:
            return
        
        # Get current position
        x1, y1, x2, y2, _ = self.target_person_box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        width = x2 - x1
        height = y2 - y1
        
        # Calculate relative position in frame
        rel_x = cx / self.frame_width  # 0.0 to 1.0 (left to right)
        rel_y = cy / self.frame_height  # 0.0 to 1.0 (top to bottom)
        rel_size = (width * height) / (self.frame_width * self.frame_height)  # Relative size
        
        # Add to position history
        self.previous_positions.append((cx, cy, rel_size, time.time()))
        if len(self.previous_positions) > self.max_positions:
            self.previous_positions.pop(0)
        
        # Determine distance category based on relative size
        if rel_size > 0.15:
            self.intruder_distance = "close"
        elif rel_size > 0.05:
            self.intruder_distance = "medium"
        else:
            self.intruder_distance = "far"
        
        # Need at least 3 positions to analyze movement
        if len(self.previous_positions) < 3:
            return
        
        # Analyze movement direction and speed
        movement_x = 0
        movement_y = 0
        size_change = 0
        count = 0
        
        for i in range(1, len(self.previous_positions)):
            prev_x, prev_y, prev_size, prev_time = self.previous_positions[i-1]
            curr_x, curr_y, curr_size, curr_time = self.previous_positions[i]
            
            if curr_time - prev_time > 1.0:  # Skip if time gap is too large
                continue
                
            movement_x += curr_x - prev_x
            movement_y += curr_y - prev_y
            size_change += curr_size - prev_size
            count += 1
        
        if count > 0:
            avg_movement_x = movement_x / count
            avg_movement_y = movement_y / count
            avg_size_change = size_change / count
            
            # Determine behavior based on movement
            if abs(avg_movement_x) < 5 and abs(avg_movement_y) < 5 and abs(avg_size_change) < 0.01:
                self.intruder_behavior = "stationary"
            elif avg_size_change > 0.01:
                self.intruder_behavior = "approaching"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            elif avg_size_change < -0.01:
                self.intruder_behavior = "retreating"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            elif abs(avg_movement_x) > 10:
                if avg_movement_x > 0:
                    self.intruder_behavior = "moving_right"
                else:
                    self.intruder_behavior = "moving_left"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            else:
                # If not confident, maintain previous behavior
                self.behavior_confidence = max(self.behavior_confidence - 1, 0)
                if self.behavior_confidence < 3:
                    self.intruder_behavior = "unknown"
    
    async def track_and_follow_person(self):
        """Track and follow the detected person"""
        if not self.is_tracking or not self.target_person_box:
            return
        
        current_time = time.time()
        if current_time - self.last_movement_time < self.movement_cooldown:
            return  # Don't move too frequently
        
        # Get target position
        x1, y1, x2, y2, _ = self.target_person_box
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        
        frame_center_x = self.frame_width // 2
        frame_center_y = self.frame_height // 2
        
        # Calculate offsets from center
        offset_x = center_x - frame_center_x
        offset_y = center_y - frame_center_y
        
        # Determine movement commands
        move_horizontal = None
        move_vertical = None
        
        # Horizontal tracking (turn left/right)
        if offset_x < -50:  # Person is to the left
            move_horizontal = "left"
        elif offset_x > 50:  # Person is to the right
            move_horizontal = "right"
        
        # Vertical tracking (look up/down)
        if offset_y < -30:  # Person is above center
            move_vertical = "lookUp"
        elif offset_y > 30:  # Person is below center
            move_vertical = "lookDown"
        
        # Execute movement commands
        commands_sent = False
        
        if move_horizontal and move_horizontal != self.last_movement_command:
            await self.send_command(move_horizontal)
            self.last_movement_command = move_horizontal
            commands_sent = True
        elif not move_horizontal and self.last_movement_command in ["left", "right"]:
            await self.send_command("TS")  # Stop turning
            self.last_movement_command = None
            commands_sent = True
        
        if move_vertical:
            await self.send_command(move_vertical)
            commands_sent = True
        elif self.last_movement_command in ["lookUp", "lookDown"]:
            await self.send_command("UDstop")  # Stop looking up/down
            commands_sent = True
        
        # Move forward/backward based on distance
        target_width = x2 - x1
        target_height = y2 - y1
        
        # Calculate area percentage
        area_percent = (target_width * target_height) / (self.frame_width * self.frame_height) * 100
        
        if area_percent < 10:  # Person is far, move forward
            if self.last_movement_command != "forward":
                await self.send_command("forward")
                self.last_movement_command = "forward"
                commands_sent = True
        elif area_percent > 40:  # Person is too close, move backward
            if self.last_movement_command != "backward":
                await self.send_command("backward")
                self.last_movement_command = "backward"
                commands_sent = True
        else:  # Good distance, stop moving
            if self.last_movement_command in ["forward", "backward"]:
                await self.send_command("DS")  # Stop forward/backward
                self.last_movement_command = None
                commands_sent = True
        
        if commands_sent:
            self.last_movement_time = current_time
    
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
                
                # Step 2: Generate warning message based on intruder description and behavior
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
        """Generate personalized warning message based on intruder description and behavior"""
        try:
            # Enhance the prompt with behavior information
            behavior_context = f"The person appears to be {self.intruder_behavior} and is {self.intruder_distance} from the camera."
            
            # Use Claude to generate a personalized warning message
            warning_message = self.claude_client.messages.create(
                model=self.claude_model,
                max_tokens=1024,
                system="You are a security robot confronting an intruder. You should generate a direct, authoritative warning message addressing the intruder based on their appearance and behavior. Be intimidating but not threatening. Your message should sound like it's being spoken by a security system.",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Based on this description of an intruder:

{intruder_description}

Additional context: {behavior_context}

Generate a security robot warning message that:
1. Directly references the person's appearance (clothing, location, etc.)
2. Responds appropriately to their behavior (approaching, retreating, stationary)
3. Sounds authoritative and firm
4. Warns them they are being monitored/recorded
5. Tells them to leave immediately or identify themselves
6. Mentions that authorities have been notified

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
            
            # Enhanced movement sequence - more dynamic based on intruder behavior
            if self.intruder_behavior == "approaching":
                # More aggressive response if intruder is approaching
                await self.send_command("steady")  # Stand steady
                await asyncio.sleep(0.5)
                
                # Quick head movements to look alert
                await self.send_command("lookLeft")
                await asyncio.sleep(0.3)
                await self.send_command("LRstop")
                await asyncio.sleep(0.2)
                await self.send_command("lookRight")
                await asyncio.sleep(0.3)
                await self.send_command("LRstop")
                
                # Jump to appear more intimidating if they're close
                if self.intruder_distance == "close":
                    await self.send_command("jump")
                    await asyncio.sleep(1.0)
                
            elif self.intruder_behavior == "retreating":
                # Follow if retreating
                await self.send_command("forward")
                await asyncio.sleep(1.0)
                await self.send_command("DS")
                
                second_message = "Stop! I'm recording you. Security has been alerted."
                await self.send_command(f"speak:{second_message}")
                
            else:
                # Standard response for other behaviors
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
            
            # Second personalized message based on intruder behavior
            second_messages = {
                "approaching": [
                    "Back away immediately! Security protocol activated.",
                    "Stop approaching! You are trespassing.",
                    "Halt! Do not come any closer.",
                    "Warning: Defensive measures engaged.",
                    "Security breach! Step back now."
                ],
                "retreating": [
                    "I've recorded your face. Don't return.",
                    "Keep moving. Exit this area now.",
                    "Your escape is being tracked.",
                    "Continue leaving. Police are on the way.",
                    "Your retreat has been logged. Don't come back."
                ],
                "stationary": [
                    "You are not authorized to be here.",
                    "Identify yourself immediately.",
                    "Remain where you are. Security en route.",
                    "This area is restricted. State your purpose.",
                    "Stand still. Awaiting security response."
                ],
                "moving_left": [
                    "Stop moving to your right. You're being tracked.",
                    "Movement detected. Remain still.",
                    "Lateral movement monitored and recorded.",
                    "Security tracking your sideways movement.",
                    "Stop moving sideways. Identify yourself."
                ],
                "moving_right": [
                    "Stop moving to your left. You're being tracked.",
                    "Movement detected. Remain still.",
                    "Lateral movement monitored and recorded.",
                    "Security tracking your sideways movement.",
                    "Stop moving sideways. Identify yourself."
                ]
            }
            
            # Select appropriate message based on behavior
            behavior_messages = second_messages.get(self.intruder_behavior, [
                "I've already called security.",
                "This area is off-limits. Leave now.",
                "Your face has been recorded.",
                "Don't move! Authorities are on their way.",
                "Security system activated. Please leave immediately."
            ])
            
            second_message = random.choice(behavior_messages)
            await self.send_command(f"speak:{second_message}")
            
            # Additional actions based on behavior
            if self.intruder_behavior == "stationary" and random.random() < 0.5:
                await self.send_command("handShake")
                await asyncio.sleep(2.0)
            
            # Bark again after interactions
            await self.bark_sequence("excited")
            
            # Start tracking if not already tracking
            if self.tracking_enabled and not self.is_tracking and self.target_person_box:
                self.is_tracking = True
                self.tracking_started = time.time()
                
                tracking_message = "Intruder tracking mode activated."
                await self.send_command(f"speak:{tracking_message}")
            
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
        self.is_tracking = False
        print("Watchdog mode disabled")
        
    def toggle_alerts(self, enable):
        """Toggle alert system"""
        self.alerts_enabled = enable
        print(f"Alerts {'enabled' if enable else 'disabled'}")
    
    def toggle_tracking(self, enable):
        """Toggle intruder tracking"""
        self.tracking_enabled = enable
        if not enable:
            self.is_tracking = False
            self.target_person_box = None
        print(f"Intruder tracking {'enabled' if enable else 'disabled'}")
    
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
    
    async def robot_reset_position(self):
        """Reset robot to initial position"""
        print("Resetting robot position...")
        
        # Stop any ongoing movements
        await self.send_command("DS")  # Stop forward/backward
        await self.send_command("TS")  # Stop left/right
        await self.send_command("LRstop")  # Stop head left/right
        await self.send_command("UDstop")  # Stop head up/down
        
        # Reset to initial position
        await self.send_command("InitPos")
        await asyncio.sleep(2.0)
        
        print("Robot position reset complete.")
    
    async def robot_middle_position(self):
        """Move robot to middle position"""
        print("Moving robot to middle position...")
        
        # Stop any ongoing movements
        await self.send_command("DS")  # Stop forward/backward
        await self.send_command("TS")  # Stop left/right
        await self.send_command("LRstop")  # Stop head left/right
        await self.send_command("UDstop")  # Stop head up/down
        
        # Go to middle position
        await self.send_command("MiddlePos")
        await asyncio.sleep(2.0)
        
        print("Robot moved to middle position.")
            
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
                    
                    # Occasionally reset position 
                    if random.random() < 0.2:  # 20% chance to reset
                        await self.robot_middle_position()
                    
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
                            
                            # If tracking enabled and have a target, follow person
                            if self.tracking_enabled and self.is_tracking and self.target_person_box:
                                asyncio.run(self.track_and_follow_person())
                            
                            # Draw bounding boxes for detected persons
                            if person_detected and self.person_boxes:
                                for box in self.person_boxes:
                                    x1, y1, x2, y2, conf = box
                                    # Highlight target person in red, others in green
                                    color = (0, 0, 255) if box == self.target_person_box else (0, 255, 0)
                                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                                    label = f"{'Target' if box == self.target_person_box else 'Person'}: {conf:.2f}"
                                    cv2.putText(display_frame, label, (x1, y1 - 10), 
                                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
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
                        
                        tracking_text = f"Tracking: {'ON' if self.is_tracking else 'OFF'}"
                        cv2.putText(display_frame, tracking_text, (10, 150), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        patrol_text = f"Patrol Mode: {'ON' if self.patrol_mode else 'OFF'}"
                        cv2.putText(display_frame, patrol_text, (10, 180), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        
                        if self.use_yolo and self.person_detected:
                            person_text = f"Person: Count={self.person_count}, Behavior={self.intruder_behavior}"
                            cv2.putText(display_frame, person_text, (10, 210), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                        elif not self.use_yolo and self.motion_detected:
                            motion_text = f"Motion Detected! Consecutive: {self.consecutive_detections}"
                            cv2.putText(display_frame, motion_text, (10, 210), 
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
                            cv2.putText(display_frame, "Description:", (10, 240), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                            for i, line in enumerate(lines):
                                cv2.putText(display_frame, line, (10, 270 + i*30), 
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
                                y_offset = 270 + 30 * len(self.intruder_description.split('\n'))
                                
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
                    help_text = "Controls: [e]nable/[d]isable watchdog, [a]lerts, [t]racking, [p]atrol, [r]eset, [m]iddle pos, [j]ump, [q]uit"
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
                        elif key == ord('t'):
                            self.toggle_tracking(not self.tracking_enabled)
                        elif key == ord('p'):
                            self.toggle_patrol_mode(not self.patrol_mode)
                        elif key == ord('r'):
                            asyncio.run(self.robot_reset_position())
                        elif key == ord('m'):
                            asyncio.run(self.robot_middle_position())
                        elif key == ord('j'):
                            asyncio.run(self.send_command("jump"))
                        elif key == ord('h'):
                            asyncio.run(self.send_command("handShake"))
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
            asyncio.run(self.send_command("speak:Enhanced security watchdog with intruder tracking initialized and ready!"))
            
            # Announce special features
            if self.ai_enabled:
                asyncio.run(self.send_command("speak:Claude AI integration active for personalized warnings."))
            
            if self.tracking_enabled:
                asyncio.run(self.send_command("speak:Intruder tracking system online."))
            
            # Start frame processing
            print("\nStarting watchdog monitor...")
            print("Press 'e' to enable watchdog")
            print("Press 'd' to disable watchdog")
            print("Press 'a' to toggle alerts")
            print("Press 't' to toggle tracking")
            print("Press 'p' to toggle patrol mode")
            print("Press 'r' to reset position (InitPos)")
            print("Press 'm' to go to middle position (MiddlePos)")
            print("Press 'j' to jump")
            print("Press 'h' to handshake")
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
    parser = argparse.ArgumentParser(description="Enhanced Robot Watchdog with Intruder Tracking")
    parser.add_argument("--ip", type=str, default=None,
                        help="Robot IP address (default: from ROBOT_IP_ADDRESS env var)")
    parser.add_argument("--enable", action="store_true", 
                        help="Enable watchdog mode on startup")
    parser.add_argument("--track", action="store_true",
                        help="Enable tracking on startup")
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
        
    # Enable tracking if requested
    if args.track:
        watchdog.toggle_tracking(True)
        
    # Enable patrol mode if requested
    if args.patrol and args.enable:
        watchdog.toggle_patrol_mode(True)
    
    # Run the watchdog
    watchdog.run()

if __name__ == "__main__":
    main()