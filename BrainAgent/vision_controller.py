#!/usr/bin/env python3
# Enhanced Robot Watchdog with YOLO person detection, Claude-generated warnings, intruder tracking, and voice challenge

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
import speech_recognition as sr  # pip install SpeechRecognition
import pyttsx3  # pip install pyttsx3
import concurrent.futures

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
        
        # NEW: Voice challenge settings
        self.voice_challenge_enabled = False  # Disabled by default due to mic issues
        self.challenge_active = False
        self.challenge_passed = False
        self.challenge_timeout = 60  # 60 seconds to respond
        self.challenge_start_time = 0
        self.recognizer = None
        self.voice_engine = None
        try:
            self.recognizer = sr.Recognizer()
            self.voice_engine = pyttsx3.init()
            self.voice_engine.setProperty('rate', 150)  # Speed of speech
        except Exception as e:
            print(f"Speech recognition initialization error: {e}")
            print("Voice challenge will be disabled.")
            self.voice_challenge_enabled = False
        self.voice_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.voice_recognition_timeout = 10  # seconds to wait for response
        
        # Security questions and correct answers
        self.security_questions = [
            {"question": "What is the password?", "answer": "bluesky"},
            {"question": "Who are you?", "answer": "authorized"},
            {"question": "What is today's code word?", "answer": "sunshine"},
            {"question": "State your security clearance level.", "answer": "alpha"},
            {"question": "What department do you work for?", "answer": "engineering"}
        ]
        self.current_question = None
        
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
        
        # Frame processing - optimized
        self.frame_queue = Queue(maxsize=5)  # Reduced queue size to prevent memory build-up
        self.frame_skip = 2  # Process only every Nth frame to improve performance
        
        # Fallback generic warnings (used when Claude is not available)
        self.generic_warnings = [
            "Intruder detected! The police has been notified.",
            "Warning! This area is under surveillance.",
            "Security alert! The homeowner has been notified.",
            "Unauthorized access detected! Security system activated.",
            "This is a security robot. Please identify yourself."
        ]
        self.last_message_index = -1
        
        # NEW: Angry messages for failed challenge responses
        self.angry_messages = [
            "I've already called the police! Get out now!",
            "This is your final warning! Leave immediately!",
            "Security measures activated. You need to leave right now!",
            "Stop what you're doing and exit the premises immediately!",
            "You are trespassing! Get out or there will be consequences!"
        ]
        
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
        print(f"Voice Challenge: {'Enabled' if self.voice_challenge_enabled else 'Disabled'}")
        
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
            await self.send_command("buzzer 1")  # Using 'buzzer on' as bark
            await asyncio.sleep(duration)
            await self.send_command("buzzer 0")
            await asyncio.sleep(pause)
    
    def speak(self, text):
        """Text-to-speech function"""
        def _speak_worker():
            print(f"Robot says: {text}")
            # Convert speak command to match the robot's command format
            try:
                asyncio.run(self.send_command(f"speak:{text}"))
            except Exception as e:
                print(f"Speech command error: {e}")
            
        # Run speech in a separate thread to avoid blocking
        self.voice_executor.submit(_speak_worker)
    
    def listen(self, timeout=10):
        """Listen for voice input with timeout"""
        if not self.recognizer:
            print("Speech recognition not available")
            return ""
            
        try:
            # Use with context for microphone to ensure proper resource cleanup
            with sr.Microphone() as source:
                print("Listening for response...")
                try:
                    # Adjust for ambient noise
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    # Listen for audio with timeout
                    audio = self.recognizer.listen(source, timeout=timeout)
                    # Convert speech to text
                    response = self.recognizer.recognize_google(audio)
                    print(f"Heard: {response}")
                    return response.lower()
                except sr.WaitTimeoutError:
                    print("No audio detected within timeout")
                    return ""
                except sr.UnknownValueError:
                    print("Could not understand audio")
                    return ""
                except sr.RequestError as e:
                    print(f"Could not request results from speech recognition service: {e}")
                    return ""
                except Exception as e:
                    print(f"Audio processing error: {e}")
                    return ""
        except Exception as e:
            print(f"Microphone error: {e}")
            # Disable voice challenge due to microphone problems
            self.voice_challenge_enabled = False
            return ""
    
    def capture_video(self):
        """Capture video frames from robot's stream - optimized for performance"""
        print(f"Starting video capture from {self.video_url}")
        
        retry_count = 0
        max_retries = 10
        frame_count = 0
        
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
                    
                    # Update frame dimensions (only occasionally to save processing)
                    if frame_count % 30 == 0:
                        self.frame_width = frame.shape[1]
                        self.frame_height = frame.shape[0]
                    
                    frame_count += 1
                    
                    # Skip frames to improve performance
                    if frame_count % self.frame_skip != 0:
                        continue
                    
                    # Store frame in queue (with minimal copying)
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                    else:
                        try:
                            self.frame_queue.get_nowait()  # Remove old frame
                            self.frame_queue.put(frame)
                        except:
                            pass
                    
                    # Throttle capture rate slightly
                    time.sleep(0.03)
                    
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
        """Detect persons in the frame using YOLO - optimized for performance"""
        if not self.watchdog_enabled or not self.use_yolo:
            return False
            
        try:
            # Run YOLO detection with performance optimization
            results = self.model(frame, classes=[0], verbose=False)  # Class 0 is person in COCO dataset
            
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
                
                # Check if we should trigger challenge or alert
                if (self.consecutive_person_detections >= self.person_detection_threshold and 
                        self.alerts_enabled and not self.is_alerting):
                    
                    # If voice challenge is enabled, start the challenge
                    if self.voice_challenge_enabled and not self.challenge_active and not self.challenge_passed:
                        # Run challenge in separate thread to avoid blocking
                        challenge_thread = threading.Thread(
                            target=self._run_voice_challenge
                        )
                        challenge_thread.daemon = True
                        challenge_thread.start()
                    elif not self.voice_challenge_enabled or self.challenge_passed:
                        # If Claude is enabled, send frame for analysis WITHOUT blocking
                        if self.ai_enabled and time.time() - self.last_vision_analysis_time > self.vision_analysis_interval:
                            # Run vision analysis in separate thread to avoid blocking
                            analysis_thread = threading.Thread(
                                target=self._run_claude_analysis,
                                args=(frame.copy(),)
                            )
                            analysis_thread.daemon = True
                            analysis_thread.start()
                        else:
                            # Trigger alert without vision analysis and without blocking
                            alert_thread = threading.Thread(
                                target=self._trigger_alert_worker
                            )
                            alert_thread.daemon = True
                            alert_thread.start()
                
                # Save image on first detection (non-blocking)
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
                    
                    # Non-blocking stop commands
                    stop_thread = threading.Thread(
                        target=self._stop_movement_worker
                    )
                    stop_thread.daemon = True
                    stop_thread.start()
            
            return self.person_detected
            
        except Exception as e:
            print(f"YOLO detection error: {e}")
            # Simplified error handling (removed traceback for better performance)
            return False
    
    def _run_voice_challenge(self):
        """Run voice challenge in a separate thread"""
        self.challenge_active = True
        self.challenge_start_time = time.time()
        
        # Use threading event to create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Use robot's head movements to look at the person
            loop.run_until_complete(self.send_command("lookLeft"))
            time.sleep(0.3)
            loop.run_until_complete(self.send_command("LRstop"))
            time.sleep(0.2)
            loop.run_until_complete(self.send_command("lookRight"))
            time.sleep(0.3)
            loop.run_until_complete(self.send_command("LRstop"))
            
            # Choose a random security question
            self.current_question = random.choice(self.security_questions)
            
            # Ask the security question (short version)
            self.speak(f"{self.current_question['question']}")
            
            # Wait briefly to ensure speech completes
            time.sleep(2)
            
            # Listen for answer with timeout
            response = self.listen(timeout=self.voice_recognition_timeout)
            
            # Check if answer is correct (with some flexibility)
            if response and (response == self.current_question['answer'].lower() or 
                            self.current_question['answer'].lower() in response):
                self.speak("Access granted.")
                self.challenge_passed = True
                loop.run_until_complete(self.send_command("light green"))  # Green light for success
                time.sleep(1)
                loop.run_until_complete(self.send_command("light off"))
            else:
                # If microphone failed, just skip to alert
                if not self.voice_challenge_enabled:
                    self._trigger_alert_worker(failed_challenge=True)
                else:
                    # Give them one more chance with a shorter prompt
                    time.sleep(1)
                    self.speak(f"Repeat: {self.current_question['question']}")
                    
                    response = self.listen(timeout=self.voice_recognition_timeout)
                    
                    if response and (response == self.current_question['answer'].lower() or 
                                   self.current_question['answer'].lower() in response):
                        self.speak("Access granted.")
                        self.challenge_passed = True
                        loop.run_until_complete(self.send_command("light green"))
                        time.sleep(1)
                        loop.run_until_complete(self.send_command("light off"))
                    else:
                        # Failed challenge, trigger alert
                        self.speak("Intruder detected.")
                        self._trigger_alert_worker(failed_challenge=True)
        except Exception as e:
            print(f"Voice challenge error: {e}")
            # Fall back to default alert
            self._trigger_alert_worker()
        finally:
            self.challenge_active = False
            loop.close()
        
    def check_challenge_timeout(self):
        """Check if the voice challenge has timed out"""
        if self.challenge_active:
            elapsed_time = time.time() - self.challenge_start_time
            if elapsed_time > self.challenge_timeout:
                print("Challenge response timeout")
                self.challenge_active = False
                self._trigger_alert_worker(failed_challenge=True)

    def _run_claude_analysis(self, frame):
        """Run Claude analysis in a separate thread to avoid blocking"""
        asyncio.run(self.analyze_frame_with_claude(frame))
    
    def _trigger_alert_worker(self, failed_challenge=False):
        """Trigger alert in a non-blocking way"""
        asyncio.run(self.trigger_alert(failed_challenge=failed_challenge))
    
    def _stop_movement_worker(self):
        """Stop robot movement in a non-blocking way"""
        async def stop_robot():
            await self.send_command("DS")  # Stop forward/backward
            await self.send_command("TS")  # Stop left/right
        
        asyncio.run(stop_robot())

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
        """Track and follow the detected person - optimized for smoother movement"""
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
        
        # Determine movement commands with hysteresis to prevent jitter
        # (only change direction when offset is significant)
        move_horizontal = None
        move_vertical = None
        
        # Horizontal tracking with wider threshold (turn left/right)
        if offset_x < -70:  # Person is significantly to the left
            move_horizontal = "left"
        elif offset_x > 70:  # Person is significantly to the right
            move_horizontal = "right"
        elif -30 <= offset_x <= 30:  # Person is centered horizontally
            if self.last_movement_command in ["left", "right"]:
                move_horizontal = "stop"  # Stop turning when centered
        
        # Vertical tracking with wider threshold (look up/down)
        if offset_y < -50:  # Person is significantly above center
            move_vertical = "lookUp"
        elif offset_y > 50:  # Person is significantly below center
            move_vertical = "lookDown"
        elif -20 <= offset_y <= 20:  # Person is centered vertically
            if self.last_movement_command in ["lookUp", "lookDown"]:
                move_vertical = "stop"  # Stop looking when centered
        
        # Queue to batch commands to send (to reduce network traffic)
        commands_to_send = []
        
        # Handle horizontal movement
        if move_horizontal == "left" and self.last_movement_command != "left":
            commands_to_send.append("left")
            self.last_movement_command = "left"
        elif move_horizontal == "right" and self.last_movement_command != "right":
            commands_to_send.append("right")
            self.last_movement_command = "right"
        elif move_horizontal == "stop" and self.last_movement_command in ["left", "right"]:
            commands_to_send.append("TS")  # Stop turning
            self.last_movement_command = None
        
        # Handle vertical movement
        if move_vertical == "lookUp":
            commands_to_send.append("lookUp")
        elif move_vertical == "lookDown":
            commands_to_send.append("lookDown")
        elif move_vertical == "stop":
            commands_to_send.append("UDstop")  # Stop looking up/down
        
        # Move forward/backward based on distance
        target_width = x2 - x1
        target_height = y2 - y1
        
        # Calculate area percentage with smoothing
        area_percent = (target_width * target_height) / (self.frame_width * self.frame_height) * 100
        
        # Forward/backward movement with hysteresis
        if area_percent < 8:  # Person is definitely far, move forward
            if self.last_movement_command != "forward":
                commands_to_send.append("forward")
                self.last_movement_command = "forward"
        elif area_percent > 45:  # Person is definitely too close, move backward
            if self.last_movement_command != "backward":
                commands_to_send.append("backward")
                self.last_movement_command = "backward"
        elif 12 <= area_percent <= 35:  # Good distance, stop moving if we were moving
            if self.last_movement_command in ["forward", "backward"]:
                commands_to_send.append("DS")  # Stop forward/backward
                self.last_movement_command = None
        
        # Send commands efficiently
        if commands_to_send:
            for cmd in commands_to_send:
                await self.send_command(cmd)
                # Small delay between commands to let robot process
                await asyncio.sleep(0.05)
            
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
        """Save a detection image to disk (screenshots only, no video)"""
        try:
            # Run in separate thread to avoid blocking main loop
            save_thread = threading.Thread(
                target=self._save_image_worker,
                args=(frame.copy(),)  # Pass a copy to avoid memory issues
            )
            save_thread.daemon = True
            save_thread.start()
        except Exception as e:
            print(f"Error starting save thread: {e}")
            
    def _save_image_worker(self, frame):
        """Worker function to save image in separate thread"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"intruder_{timestamp}.jpg"
            filepath = os.path.join(self.save_dir, filename)
            
            # Add timestamp to the image
            timestamp_text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, timestamp_text, (10, frame.shape[0] - 10), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
            
            # Draw bounding boxes for persons if using YOLO
            if self.use_yolo and self.person_boxes:
                for box in self.person_boxes:
                    x1, y1, x2, y2, conf = box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Person: {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # Add behavior and description if available
            info_text = f"Behavior: {self.intruder_behavior}, Distance: {self.intruder_distance}"
            cv2.putText(frame, info_text, (10, 30), 
                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            if self.intruder_description:
                desc_lines = self.intruder_description.split('\n')
                for i, line in enumerate(desc_lines[:3]):  # Limit to first 3 lines
                    cv2.putText(frame, line, (10, 60 + i*20), 
                              cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Save image with optimized quality (95%)
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            print(f"Saved detection image to {filepath}")
                
        except Exception as e:
            print(f"Error saving detection image: {e}")
    
    async def trigger_alert(self, warning_message=None, failed_challenge=False):
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
            target=lambda: asyncio.run(self.alert_sequence(warning_message, was_patrolling, failed_challenge))
        )
        alert_thread.daemon = True
        alert_thread.start()
    
    async def alert_sequence(self, warning_message=None, resume_patrol=False, failed_challenge=False):
        """Run the alert sequence"""
        try:
            print("⚠️ ALERT! Intruder detected!")
            
            # First, make the robot bark
            await self.bark_sequence("alert")
            
            # Use provided warning message, generic fallback, or failure message for challenge
            if failed_challenge:
                # Use more aggressive message for failed challenge
                warning_message = random.choice(self.angry_messages)
            elif not warning_message:
                # Use generic warning message
                warning_message = random.choice(self.generic_warnings)
            
            # Speak the warning message directly addressing the intruder
            print(f"Speaking: {warning_message}")
            await self.send_command(f"speak:{warning_message}")
            
            # Flash red lights
            for _ in range(3):  # Reduced from 5 to be less verbose
                await self.send_command("light red")
                await asyncio.sleep(0.3)
                await self.send_command("light off")
                await asyncio.sleep(0.2)
            
            # Enhanced movement sequence - more dynamic based on intruder behavior
            if self.intruder_behavior == "approaching":
                # More aggressive response if intruder is approaching
                await self.send_command("steady")  # Stand steady
                await asyncio.sleep(0.5)
                
                # Jump to appear more intimidating if they're close
                if self.intruder_distance == "close":
                    await self.send_command("jump")
                    await asyncio.sleep(1.0)
                
            elif self.intruder_behavior == "retreating":
                # Follow if retreating
                await self.send_command("forward")
                await asyncio.sleep(1.0)
                await self.send_command("DS")
                
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
            
            # Only say a second message if the challenge failed (reduce verbosity)
            if failed_challenge:
                # Select appropriate message based on behavior
                second_messages = {
                    "approaching": [
                        "Back off now! Police coming!",
                        "Get back! Final warning!",
                        "Stop right there!",
                        "Get out now!"
                    ],
                    "retreating": [
                        "Get out! Don't come back!",
                        "Run! Police on their way!",
                        "Your face is in the system!",
                        "Keep moving!"
                    ],
                    "stationary": [
                        "Why are you still here?!",
                        "Get out now!",
                        "10 seconds before lockdown!",
                        "Leave immediately!"
                    ]
                }
                
                # Get messages for the current behavior, or use default messages
                behavior_messages = second_messages.get(self.intruder_behavior, [
                    "Police notified!",
                    "Leave now!",
                    "Face recorded!",
                    "Get out!"
                ])
                
                second_message = random.choice(behavior_messages)
                await self.send_command(f"speak:{second_message}")
                
                # Additional actions based on behavior
                if self.intruder_behavior == "stationary":
                    await self.send_command("handShake")
                    await asyncio.sleep(2.0)
            
            # Bark again after interactions
            await self.bark_sequence("excited")
            
            # Start tracking if not already tracking (without announcement)
            if self.tracking_enabled and not self.is_tracking and self.target_person_box:
                self.is_tracking = True
                self.tracking_started = time.time()
            
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
    
    def toggle_voice_challenge(self, enable):
        """Toggle voice challenge feature"""
        # Only enable if speech recognition is available
        if enable and not self.recognizer:
            print("Cannot enable voice challenge - speech recognition not available")
            return
            
        self.voice_challenge_enabled = enable
        if not enable:
            self.challenge_active = False
            self.challenge_passed = False
        print(f"Voice challenge {'enabled' if enable else 'disabled'}")
    
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
        patrol_counter = 0  # Counter to control announcement frequency
        
        while self.running and self.patrol_mode and self.watchdog_enabled and not self.is_alerting:
            try:
                current_time = time.time()
                
                # Check if it's time for a patrol movement
                if current_time - self.last_patrol_time >= self.patrol_interval:
                    print("Performing patrol movement")
                    self.last_patrol_time = current_time
                    
                    # Only announce patrol occasionally to reduce verbosity (every 3rd patrol)
                    patrol_counter += 1
                    if patrol_counter % 3 == 0:
                        await self.send_command("speak:Patrolling")
                    
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
        """Process frames in the queue - optimized for performance"""
        print("Starting frame processing...")
        
        display_window = True  # Set to False to disable GUI
        
        # For tracking performance
        frame_count = 0
        last_fps_time = time.time()
        fps = 0
        
        # For tracking movement
        movement_thread = None
        
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
                    
                    # Update FPS counter
                    frame_count += 1
                    current_time = time.time()
                    if current_time - last_fps_time >= 1.0:
                        fps = frame_count
                        frame_count = 0
                        last_fps_time = current_time
                    
                    # Optimize frame copy (only copy if we need to display)
                    if display_window:
                        display_frame = frame.copy()
                    else:
                        display_frame = frame  # Just use reference if not displaying
                    
                    # Check for voice challenge timeout
                    self.check_challenge_timeout()
                    
                    # Detect intruders if watchdog is enabled
                    if self.watchdog_enabled:
                        if self.use_yolo:
                            # Use YOLO for person detection
                            person_detected = self.detect_persons_yolo(display_frame)
                            
                            # If tracking enabled and have a target, follow person (non-blocking)
                            if (self.tracking_enabled and self.is_tracking and self.target_person_box and 
                                (movement_thread is None or not movement_thread.is_alive())):
                                
                                movement_thread = threading.Thread(
                                    target=lambda: asyncio.run(self.track_and_follow_person())
                                )
                                movement_thread.daemon = True
                                movement_thread.start()
                            
                            # Draw bounding boxes for detected persons
                            if display_window and person_detected and self.person_boxes:
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
                            if display_window and motion_detected and self.motion_area:
                                x, y, w, h = self.motion_area
                                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        
                        # Only add status text if displaying
                        if display_window:
                            # Add status text (simplified)
                            status_text = f"FPS: {fps} | Watchdog: ON | Voice Challenge: {'ON' if self.voice_challenge_enabled else 'OFF'} | Tracking: {'ON' if self.is_tracking else 'OFF'} | Patrol: {'ON' if self.patrol_mode else 'OFF'}"
                            cv2.putText(display_frame, status_text, (10, 30), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                            
                            # Add challenge status if active
                            if self.voice_challenge_enabled:
                                if self.challenge_active:
                                    challenge_text = "Challenge: ACTIVE"
                                    color = (0, 255, 255)  # Yellow
                                elif self.challenge_passed:
                                    challenge_text = "Challenge: PASSED"
                                    color = (0, 255, 0)  # Green
                                else:
                                    challenge_text = "Challenge: WAITING"
                                    color = (255, 255, 255)  # White
                                
                                cv2.putText(display_frame, challenge_text, (10, 60), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                            
                            if self.use_yolo and self.person_detected:
                                person_text = f"Person: Count={self.person_count}, Behavior={self.intruder_behavior}, Dist={self.intruder_distance}"
                                cv2.putText(display_frame, person_text, (10, 90), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                            
                            # Show compact intruder info
                            if self.intruder_description and "no people" not in self.intruder_description.lower():
                                if len(self.intruder_description) > 60:
                                    desc_text = self.intruder_description[:57] + "..."
                                else:
                                    desc_text = self.intruder_description
                                
                                cv2.putText(display_frame, f"Description: {desc_text}", (10, 120), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                            
                            # Show compact warning message
                            if self.generated_warning:
                                if len(self.generated_warning) > 60:
                                    warning_text = self.generated_warning[:57] + "..."
                                else:
                                    warning_text = self.generated_warning
                                
                                cv2.putText(display_frame, f"Warning: {warning_text}", (10, 150), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                    else:
                        if display_window:
                            status_text = "Watchdog: DISABLED"
                            cv2.putText(display_frame, status_text, (10, 30), 
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    
                    # Add help text at the bottom if displaying
                    if display_window:
                        help_text = "Controls: [e]nable/[d]isable, [a]lerts, [t]rack, [v]oice challenge, [p]atrol, [r]eset, [m]iddle, [j]ump, [h]andshake, [q]uit"
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
                        elif key == ord('v'):
                            self.toggle_voice_challenge(not self.voice_challenge_enabled)
                        elif key == ord('p'):
                            self.toggle_patrol_mode(not self.patrol_mode)
                        elif key == ord('r'):
                            # Non-blocking reset
                            reset_thread = threading.Thread(
                                target=lambda: asyncio.run(self.robot_reset_position())
                            )
                            reset_thread.daemon = True
                            reset_thread.start()
                        elif key == ord('m'):
                            # Non-blocking middle position
                            middle_thread = threading.Thread(
                                target=lambda: asyncio.run(self.robot_middle_position())
                            )
                            middle_thread.daemon = True
                            middle_thread.start()
                        elif key == ord('j'):
                            # Non-blocking jump
                            jump_thread = threading.Thread(
                                target=lambda: asyncio.run(self.send_command("jump"))
                            )
                            jump_thread.daemon = True
                            jump_thread.start()
                        elif key == ord('h'):
                            # Non-blocking handshake
                            handshake_thread = threading.Thread(
                                target=lambda: asyncio.run(self.send_command("handShake"))
                            )
                            handshake_thread.daemon = True
                            handshake_thread.start()
                        elif key == ord('b'):
                            # Non-blocking bark test
                            bark_thread = threading.Thread(
                                target=lambda: asyncio.run(self.bark_sequence("excited"))
                            )
                            bark_thread.daemon = True
                            bark_thread.start()
                
                # Very short sleep to allow task switching
                time.sleep(0.01)
                
            except Exception as e:
                print(f"Frame processing error: {e}")
                # No traceback for performance
                time.sleep(0.5)
        
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
            
            # Start with a minimal greeting message (no verbose announcements)
            asyncio.run(self.send_command("speak:Security system activated."))
            
            # Start frame processing
            print("\nStarting watchdog monitor...")
            print("Press 'e' to enable watchdog")
            print("Press 'd' to disable watchdog")
            print("Press 'a' to toggle alerts")
            print("Press 't' to toggle tracking")
            print("Press 'v' to toggle voice challenge")
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
    parser = argparse.ArgumentParser(description="Enhanced Robot Watchdog with Voice Challenge")
    parser.add_argument("--ip", type=str, default=None,
                        help="Robot IP address (default: from ROBOT_IP_ADDRESS env var)")
    parser.add_argument("--enable", action="store_true", 
                        help="Enable watchdog mode on startup")
    parser.add_argument("--track", action="store_true",
                        help="Enable tracking on startup")
    parser.add_argument("--patrol", action="store_true",
                        help="Enable patrol mode on startup")
    parser.add_argument("--no-voice", action="store_true",
                        help="Disable voice challenge feature")
    parser.add_argument("--claude-key", type=str, default=None,
                        help="Claude API key for vision analysis (default: from CLAUDE_API_KEY env var)")
    parser.add_argument("--no-yolo", action="store_true",
                        help="Disable YOLO and use motion detection instead")
    parser.add_argument("--nodisplay", action="store_true",
                        help="Run without display window (headless mode)")
    parser.add_argument("--frame-skip", type=int, default=2,
                        help="Process only every Nth frame (higher values = better performance)")
    parser.add_argument("--high-performance", action="store_true",
                        help="Enable high performance mode (reduces quality but increases speed)")
    
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
    
    # Performance tuning options
    if args.frame_skip:
        watchdog.frame_skip = args.frame_skip
        print(f"Setting frame skip to {args.frame_skip} (processing 1/{args.frame_skip} frames)")
    
    if args.high_performance:
        # Increase performance mode settings
        watchdog.frame_skip = max(3, watchdog.frame_skip)  # Skip more frames
        watchdog.movement_cooldown = 1.5  # Longer delay between movements
        watchdog.vision_analysis_interval = 30  # Less frequent Claude analysis
        watchdog.person_detection_threshold = 5  # Require more detections before alerting
        print("High performance mode enabled - prioritizing speed over responsiveness")
    
    # Disable YOLO if requested
    if args.no_yolo:
        watchdog.use_yolo = False
    
    # Disable voice challenge if requested
    if args.no_voice:
        watchdog.voice_challenge_enabled = False
    
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