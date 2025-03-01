import asyncio
import websockets
import cv2
import json
import base64
import threading
import random
from queue import Queue
import time
import speech_recognition as sr
import os
import anthropic
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
from collections import deque
os.environ["TOKENIZERS_PARALLELISM"] = "false"

class DogBrain:
    def __init__(self, robot_ip, claude_api_key):
        self.robot_ip = robot_ip
        self.ws_url = f"ws://{robot_ip}:8888"
        self.video_url = f"http://{robot_ip}:5000/video_feed"
        self.websocket = None
        self.running = True
        self.frame_queue = Queue(maxsize=5)  # Store more frames
        self.last_action = None
        self.action_count = 0
        self.recognizer = sr.Recognizer()
        self.voice_queue = Queue()
        self.last_voice_input = None
        self.image_base64 = ''
        self.last_frame_time = 0
        self.frame_capture_success = False
        
        # Variables for the modified voice input system
        self.command_mode = False  # Will be set based on keyboard availability
        self.start_listening = False  # Flag for command-based listening
        self.continuous_mode = False  # Will be set if neither keyboard nor command input is available
        
        # Posture detection variables
        self.posture_model = None
        self.keypoints_history = deque(maxlen=50)  # Store recent posture keypoints
        self.slouch_threshold = 0.25  # Configurable threshold for slouching
        self.last_posture_check_time = 0
        self.posture_check_interval = 30  # Check posture every 30 seconds
        self.slouch_duration = 0  # How long the user has been slouching
        self.slouch_warning_levels = {
            "mild": 60,     # 1 minute of slouching
            "moderate": 180, # 3 minutes of slouching
            "severe": 300    # 5 minutes of slouching
        }
        self.last_posture_warning = 0
        self.posture_warning_cooldown = 120  # 2 minutes between warnings
        self.focus_mode_active = False
        
        self.currently_speaking = False
        self.current_action_task = None
        self.interrupt_event = asyncio.Event()
        self.autonomous_mode = False 
        
        # Claude client initialization
        self.claude_api_key = claude_api_key
        self.client = anthropic.Anthropic(api_key=claude_api_key)
        
        # Use Claude 3.7 Sonnet model
        self.claude_model = "claude-3-7-sonnet-20250219"
        
        print(f"Dog brain initializing with Robot IP: {robot_ip}")
        print(f"Video URL set to: {self.video_url}")
        print(f"Using Claude model: {self.claude_model}")
        print("Dog brain ready to explore!")
        
        # Load posture detection model
        self._load_posture_model()

    def _load_posture_model(self):
        """Load the MoveNet posture detection model"""
        try:
            # Load MoveNet from TensorFlow Hub
            model_name = "movenet_singlepose_thunder"
            model_url = f"https://tfhub.dev/google/{model_name}/4"
            print(f"Loading posture detection model: {model_name}")
            self.posture_model = hub.load(model_url)
            print("Posture detection model loaded successfully")
        except Exception as e:
            print(f"Failed to load posture detection model: {e}")
            self.posture_model = None
    
    async def send_command_multiple(self, command, times=3, delay=0.1):
        """Send a command multiple times with delay to ensure it's received"""
        responses = []
        for _ in range(times):
            response = await self.send_command(command)
            responses.append(response)
            await asyncio.sleep(delay)
        return responses

    async def movement_sequence(self, command, duration=2.0, stop_command="DS"):
        """Execute a movement with proper start and stop sequence"""
        # Send movement command multiple times
        await self.send_command_multiple(command, times=3)
        
        # Random variation in movement duration
        actual_duration = duration + random.uniform(-0.5, 0.5)
        await asyncio.sleep(actual_duration)
        
        # Send stop command multiple times
        await self.send_command_multiple(stop_command, times=3)
        
        # Small pause after movement
        await asyncio.sleep(0.2)

    async def detect_posture(self, frame):
        """Detect body posture using MoveNet and analyze for slouching"""
        if self.posture_model is None:
            return False
            
        try:
            # Resize image for model
            img = tf.image.resize_with_pad(np.expand_dims(frame, axis=0), 256, 256)
            
            # Run model inference
            results = self.posture_model(img)
            keypoints = results['output_0'].numpy()
            
            # Extract relevant keypoints (0=nose, 5=left shoulder, 6=right shoulder, 11=left hip, 12=right hip)
            keypoints_with_scores = keypoints[0, 0, :, :3]
            
            # Store current keypoints with timestamp
            self.keypoints_history.append({
                'keypoints': keypoints_with_scores,
                'timestamp': time.time()
            })
            
            # Analyze posture for slouching
            is_slouching = self._analyze_slouching(keypoints_with_scores)
            
            # Update slouch duration
            current_time = time.time()
            if is_slouching:
                if self.slouch_duration == 0:
                    # Start of a slouch period
                    self.slouch_duration = current_time
                # Otherwise slouch_duration already contains the start time
            else:
                # Reset slouch duration if not slouching
                self.slouch_duration = 0
                
            # Check if we need to send a warning
            if self.slouch_duration > 0:
                slouch_time = current_time - self.slouch_duration
                
                # Check if we've been slouching longer than our warning thresholds
                # and if we're past the cooldown period for warnings
                if slouch_time >= self.slouch_warning_levels["severe"] and current_time - self.last_posture_warning >= self.posture_warning_cooldown:
                    await self.send_posture_alert("severe")
                    self.last_posture_warning = current_time
                elif slouch_time >= self.slouch_warning_levels["moderate"] and current_time - self.last_posture_warning >= self.posture_warning_cooldown:
                    await self.send_posture_alert("moderate")
                    self.last_posture_warning = current_time
                elif slouch_time >= self.slouch_warning_levels["mild"] and current_time - self.last_posture_warning >= self.posture_warning_cooldown:
                    await self.send_posture_alert("mild")
                    self.last_posture_warning = current_time
                    
            return is_slouching
            
        except Exception as e:
            print(f"Posture detection error: {e}")
            return False
            
    def _analyze_slouching(self, keypoints):
        """Analyze keypoints to determine if the user is slouching"""
        # Extract relevant keypoints
        nose = keypoints[0, :2]
        left_shoulder = keypoints[5, :2]
        right_shoulder = keypoints[6, :2]
        left_hip = keypoints[11, :2]
        right_hip = keypoints[12, :2]
        
        # Confidence scores
        nose_score = keypoints[0, 2]
        left_shoulder_score = keypoints[5, 2]
        right_shoulder_score = keypoints[6, 2]
        left_hip_score = keypoints[11, 2]
        right_hip_score = keypoints[12, 2]
        
        # Only proceed if we have reasonable confidence in the keypoints
        min_confidence = 0.3
        if (nose_score < min_confidence or 
            left_shoulder_score < min_confidence or 
            right_shoulder_score < min_confidence or
            left_hip_score < min_confidence or
            right_hip_score < min_confidence):
            return False
            
        # Calculate midpoints
        shoulder_midpoint = [(left_shoulder[0] + right_shoulder[0])/2, (left_shoulder[1] + right_shoulder[1])/2]
        hip_midpoint = [(left_hip[0] + right_hip[0])/2, (left_hip[1] + right_hip[1])/2]
        
        # Calculate vertical alignment (how much the shoulders are in front of the hips)
        # In image coordinates, y increases downward, so we need to check if shoulders are lower than expected
        
        # Calculate expected posture line from hip to nose
        expected_shoulder_y = hip_midpoint[1] - (hip_midpoint[1] - nose[1]) * 0.4  # Shoulders are about 40% of the way from hips to nose
        
        # If shoulders are lower (y is higher) than expected, it indicates slouching
        slouch_amount = (shoulder_midpoint[1] - expected_shoulder_y) / (hip_midpoint[1] - nose[1])
        
        # Debug info
        if random.random() < 0.05:  # Only print occasionally to avoid spam
            print(f"Slouch analysis - amount: {slouch_amount:.2f}, threshold: {self.slouch_threshold}")
        
        return slouch_amount > self.slouch_threshold
        
    async def send_posture_alert(self, severity="mild"):
        """Send an alert about poor posture based on severity"""
        alerts = {
            "mild": "I notice you're starting to slouch a bit. Maybe take a quick stretch?",
            "moderate": "You've been slouching for a while now. Time to sit up straight!",
            "severe": "Your posture doesn't look good! Please fix your posture and consider taking a short break to stretch."
        }
        
        alert = alerts.get(severity, alerts["mild"])
        print(f"🐕 Posture alert ({severity}): {alert}")
        await self.send_command(f"speak:{alert}")
        
        # Add a physical reaction for emphasis
        if severity == "severe":
            await self.bark_sequence("alert")
        elif severity == "moderate":
            await self.bark_sequence("normal")
        else:
            await self.send_command_multiple("bark", times=1)
            
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
            
    async def process_voice_command(self, text):
        """Process voice commands directly"""
        
        # Set the interrupt flag to stop any current actions
        self.interrupt_event.set()
        
        # If there's a current action running, cancel it
        if self.current_action_task and not self.current_action_task.done():
            self.current_action_task.cancel()
            try:
                await self.current_action_task
            except asyncio.CancelledError:
                print("Previous action cancelled due to new voice input")
                # Stop any movement or speaking immediately
                await self.send_command("DS")  # Stop forward/backward
                await self.send_command("TS")  # Stop turning
        
        # Reset the interrupt flag
        self.interrupt_event.clear()
        
        text = text.lower().strip()
        print(f"🎯 Processing: {text}")
        
        # Direct command mapping
        commands = {
            "forward": ["come", "forward", "go", "move"],
            "backward": ["back", "backward", "retreat"],
            "left": ["left", "turn left"],
            "right": ["right", "turn right"],
            "jump": ["jump", "hop", "up"],
            "handshake": ["shake", "paw", "hand"],
            "bark": ["bark", "woof"],
            "steady": ["steady", "balance", "stabilize"],
            "stop": ["stop", "halt", "freeze"],
            "focus": ["focus", "concentrate", "work mode", "no distractions"],
            "posture": ["posture", "straight", "back", "slouch", "sit up"]
        }
        
        
         # Special case for stop command
        if any(word in text for word in commands["stop"]):
            await self.send_command("DS")  # Stop forward/backward
            await self.send_command("TS")  # Stop turning
            await self.send_command("speak:Stopping!")
            return True
        
        # Check for movement commands
        for command, triggers in commands.items():
            if any(word in text for word in triggers):
                if command == "stop":
                    await self.send_command("DS")  # Stop forward/backward
                    await self.send_command("TS")  # Stop turning
                    return True
                if command == "steady":
                    await self.send_command("steady")
                    return True
                if command == "posture":
                    await self.send_command("speak:Let me check your posture")
                    if not self.frame_queue.empty():
                        frame = self.frame_queue.queue[0].copy()
                        is_slouching = await self.detect_posture(frame)
                        if is_slouching:
                            await self.send_posture_alert("mild")
                        else:
                            await self.send_command("speak:Your posture looks good! Keep it up!")
                    return True
                if command == "focus":
                    self.focus_mode_active = not self.focus_mode_active
                    if self.focus_mode_active:
                        await self.send_command("speak:Focus mode activated. I'll help you stay on task and check your posture regularly.")
                    else:
                        await self.send_command("speak:Focus mode deactivated. Feel free to relax.")
                    return True
                 # Execute the command in a new task so it can be interrupted
                self.current_action_task = asyncio.create_task(self.execute_command(command))
                return True
        
        # If not a command, generate a short response
        self.currently_speaking = True
        response = await self.generate_response(text)
        await self.send_command(f"speak:{response}")
        self.currently_speaking = False
        return True

    async def execute_command(self, command):
        """Execute commands with proper timing and interruption support"""
        try:
            if command == "forward":
                for _ in range(3):
                    if self.interrupt_event.is_set():
                        return
                    await self.send_command(command)
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 10.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("DS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("DS")
                
            elif command == "backward":
                for _ in range(3):
                    if self.interrupt_event.is_set():
                        return
                    await self.send_command(command)
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 8.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("DS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("DS")
                
            elif command == "left":
                for _ in range(2):
                    if self.interrupt_event.is_set():
                        return
                    await self.send_command(command)
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 5.5:
                    if self.interrupt_event.is_set():
                        await self.send_command("TS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("TS")
                
            elif command == "right":
                for _ in range(2):
                    if self.interrupt_event.is_set():
                        return
                    await self.send_command(command)
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 5.5:
                    if self.interrupt_event.is_set():
                        await self.send_command("TS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("TS")
                
            elif command == "little_left":
                if self.interrupt_event.is_set():
                    return
                await self.send_command("left")
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 2.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("TS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("TS")
                
            elif command == "little_right":
                if self.interrupt_event.is_set():
                    return
                await self.send_command("right")
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 2.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("TS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("TS")
                
            elif command == "tiny_forward":
                if self.interrupt_event.is_set():
                    return
                await self.send_command("forward")
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 3.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("DS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("DS")
                
            elif command == "tiny_backward":
                if self.interrupt_event.is_set():
                    return
                await self.send_command("backward")
                
                # Loop that can be interrupted
                start_time = time.time()
                while time.time() - start_time < 3.0:
                    if self.interrupt_event.is_set():
                        await self.send_command("DS")
                        return
                    await asyncio.sleep(0.1)
                
                await self.send_command("DS")
                
            elif command in ["jump", "handshake", "bark"]:
                for _ in range(2):
                    if self.interrupt_event.is_set():
                        return
                    await self.send_command(command)
                    
                    # Loop that can be interrupted
                    start_time = time.time()
                    while time.time() - start_time < 10.5:
                        if self.interrupt_event.is_set():
                            return
                        await asyncio.sleep(0.1)
                    
        except Exception as e:
            print(f"Command execution error: {e}")
            
    def listen_for_voice(self):
        """Listen for voice input when left shift key is pressed - macOS compatible"""
        # Try to import pynput first (works better on macOS)
        try:
            from pynput import keyboard
            
            # Flag to track if shift is pressed
            self.shift_pressed = False
            self.recording = False
            
            def on_press(key):
                # Check if key is shift
                if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    if not self.shift_pressed and not self.recording:
                        self.shift_pressed = True
                        # Start a new thread to handle recording
                        threading.Thread(target=self.record_audio_while_key_pressed).start()
            
            def on_release(key):
                # Check if key is shift
                if key == keyboard.Key.shift or key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    self.shift_pressed = False
            
            # Start keyboard listener
            print("Dog brain ready! Press and hold LEFT SHIFT key to speak to your robo-dog!")
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.start()
            
            # Keep the main thread running
            while self.running:
                time.sleep(0.1)
            
            # Stop listener when program exits
            listener.stop()
            return
            
        except ImportError:
            # If pynput fails, try the regular keyboard library
            try:
                import keyboard
                print("Using keyboard library. Press and hold LEFT SHIFT to speak.")
                
                while self.running:
                    try:
                        # Wait for shift key to be pressed (try multiple codes for macOS compatibility)
                        shift_codes = [160, 'shift', 'left shift']
                        shift_pressed = False
                        
                        for code in shift_codes:
                            try:
                                if keyboard.is_pressed(code):
                                    shift_pressed = True
                                    break
                            except:
                                continue
                        
                        if shift_pressed:
                            print("\n🎤 Listening... Speak now!")
                            time.sleep(0.2)  # Small delay to avoid key bounce
                            
                            with sr.Microphone() as source:
                                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                                
                                print("🔴 Recording... Release shift key when done.")
                                
                                # Start recording with a reasonably short phrase limit
                                audio = self.recognizer.listen(source, phrase_time_limit=10)
                                
                                print("Processing speech...")
                                
                                # Process the audio
                                try:
                                    text = self.recognizer.recognize_google(audio)
                                    if text:  # Only process non-empty results
                                        print(f"🎤 Transcribed: {text}")
                                        self.last_voice_input = text
                                        self.voice_queue.put(text)
                                        print("Sending to robot brain... wait for response.")
                                except sr.UnknownValueError:
                                    print("Couldn't understand audio")
                                except sr.RequestError as e:
                                    print(f"Speech recognition error: {e}")
                            
                            # Wait until key is released to avoid multiple triggers
                            released = False
                            while not released and self.running:
                                released = True
                                for code in shift_codes:
                                    try:
                                        if keyboard.is_pressed(code):
                                            released = False
                                            break
                                    except:
                                        continue
                                time.sleep(0.1)
                            
                            # Additional cool-down to avoid double-triggers
                            time.sleep(0.5)
                        else:
                            # Sleep when not checking key
                            time.sleep(0.1)
                            
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print(f"Listening error: {e}")
                        # Sleep on error to avoid CPU hogging
                        time.sleep(0.5)
                        continue
                
            except (ImportError, PermissionError, OSError) as e:
                print(f"Keyboard control not available ({e}).")
                print("Install pynput with: pip install pynput")
                print("Falling back to continuous listening mode with voice trigger...")
                return self._continuous_listen_fallback()
    
    def record_audio_while_key_pressed(self):
        """Record audio while shift key is pressed using pynput"""
        if self.recording:
            return
            
        self.recording = True
        print("\n🎤 Listening... Speak now!")
        
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print("🔴 Recording... Release shift key when done.")
                
                # Start recording with a timeout
                audio = self.recognizer.listen(source, phrase_time_limit=10)
                
                # Check if key is still pressed
                if not self.shift_pressed:
                    print("Processing speech...")
                    try:
                        text = self.recognizer.recognize_google(audio)
                        if text:
                            print(f"🎤 Transcribed: {text}")
                            self.last_voice_input = text
                            self.voice_queue.put(text)
                            print("Sending to robot brain... wait for response.")
                    except sr.UnknownValueError:
                        print("Couldn't understand audio")
                    except sr.RequestError as e:
                        print(f"Speech recognition error: {e}")
        except Exception as e:
            print(f"Recording error: {e}")
        
        # Reset recording flag with a small delay
        time.sleep(0.5)
        self.recording = False

    def _continuous_listen_fallback(self):
        """Fallback to listening with voice activation and manual input"""
        print("\n⚠️ Keyboard input not available. Using fallback modes:")
        print("1. Say one of these to activate me: 'hey dog', 'dog listen', 'wake up'")
        print("2. Type 'listen' in the terminal and press Enter")
        
        # Start a thread to handle console input
        input_thread = threading.Thread(target=self._console_input_loop)
        input_thread.daemon = True
        input_thread.start()
        
        # Variables for voice activation
        self.listen_mode = False
        self.listen_start_time = 0
        self.listen_timeout = 10  # seconds
        activation_phrases = ["hey dog", "dog listen", "wake up", "listen now"]
        deactivation_phrases = ["go to sleep", "stop listening"]
        
        while self.running:
            try:
                with sr.Microphone() as source:
                    # Adjust for ambient noise occasionally
                    if random.random() < 0.1:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    
                    # Short timeout to make it more responsive
                    audio = self.recognizer.listen(source, phrase_time_limit=3, timeout=1)
                    
                    try:
                        text = self.recognizer.recognize_google(audio).lower()
                        
                        # Check for activation phrases
                        is_activation = any(phrase in text for phrase in activation_phrases)
                        is_deactivation = any(phrase in text for phrase in deactivation_phrases)
                        
                        # Activation phrase detected
                        if is_activation and not self.listen_mode:
                            self.listen_mode = True
                            self.listen_start_time = time.time()
                            print("\n🔊 LISTENING MODE ACTIVATED - Say your command")
                            continue
                            
                        # Deactivation phrase detected
                        if is_deactivation and self.listen_mode:
                            self.listen_mode = False
                            print("\n🔇 Listening mode deactivated")
                            continue
                        
                        # Process command if in listening mode
                        if self.listen_mode:
                            # Reset timer
                            self.listen_start_time = time.time()
                            
                            print(f"🎤 Heard: {text}")
                            self.last_voice_input = text
                            self.voice_queue.put(text)
                        
                        # Check if listening mode timed out
                        current_time = time.time()
                        if self.listen_mode and (current_time - self.listen_start_time > self.listen_timeout):
                            self.listen_mode = False
                            print("\n🔇 Listening mode timed out")
                        
                    except sr.UnknownValueError:
                        # Silent fail for unrecognized speech
                        pass
                    except sr.RequestError as e:
                        print(f"Speech recognition error: {e}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                # Filter out timeouts which are expected
                if "timeout" not in str(e).lower():
                    print(f"Listening error: {e}")
                time.sleep(0.2)
    
    def _console_input_loop(self):
        """Thread for handling console input"""
        print("📝 Type 'listen' and press Enter to start listening for a command")
        
        while self.running:
            try:
                cmd = input()
                if cmd.lower().strip() == "listen":
                    print("🎤 Say your command now...")
                    
                    with sr.Microphone() as source:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                        print("🔴 Recording... (10 second limit)")
                        
                        # Record with timeout
                        audio = self.recognizer.listen(source, phrase_time_limit=10)
                        
                        print("Processing speech...")
                        try:
                            text = self.recognizer.recognize_google(audio)
                            if text:
                                print(f"🎤 Transcribed: {text}")
                                self.last_voice_input = text
                                self.voice_queue.put(text)
                                print("Sending to robot brain... wait for response.")
                        except sr.UnknownValueError:
                            print("Couldn't understand audio")
                        except sr.RequestError as e:
                            print(f"Speech recognition error: {e}")
                
                elif cmd.lower().strip() == "exit" or cmd.lower().strip() == "quit":
                    print("Exiting...")
                    self.running = False
                    break
                    
                elif cmd.lower().strip() == "help":
                    print("\nCommands:")
                    print("  listen - Start listening for voice command")
                    print("  exit/quit - Exit the program")
                    print("  help - Show this help message")
                    
                else:
                    print("Unknown command. Type 'help' for available commands.")
                    
            except Exception as e:
                print(f"Input error: {e}")
                time.sleep(0.5)
                
    def capture_video(self):
        """Capture video frames in a separate thread"""
        print(f"Starting dog vision... Connecting to {self.video_url}")
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                cap = cv2.VideoCapture(self.video_url)
                if not cap.isOpened():
                    print(f"Failed to open video stream at {self.video_url}, retrying...")
                    retry_count += 1
                    time.sleep(2)
                    continue
                
                print("Video stream successfully opened!")
                self.frame_capture_success = True
                retry_count = 0  # Reset retry count on success
                
                while self.running:
                    ret, frame = cap.read()
                    if ret:
                        # Clear queue if full
                        if self.frame_queue.full():
                            try:
                                self.frame_queue.get_nowait()
                            except:
                                pass
                        self.frame_queue.put(frame)
                        self.last_frame_time = time.time()
                    else:
                        print("Failed to read frame, reconnecting...")
                        break
                        
                    # Throttle capture rate
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"Video capture error: {e}")
                retry_count += 1
                time.sleep(2)
            finally:
                try:
                    cap.release()
                except:
                    pass
                
        if retry_count >= max_retries:
            print("Maximum video capture retries reached. Vision may not be available.")
            self.frame_capture_success = False

    def _continuous_listen_fallback(self):
        """Fallback to continuous listening mode (original behavior)"""
        print("Starting continuous listening mode... Speak any time.")
        
        while self.running:
            try:
                with sr.Microphone() as source:
                    # Only adjust for ambient noise occasionally
                    if random.random() < 0.1:  # 10% chance to readjust
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    # Listen without timeout for phrase start
                    audio = self.recognizer.listen(source, 
                                                phrase_time_limit=5,  # Max phrase length
                                                timeout=None)  # No timeout for start
                    
                    try:
                        text = self.recognizer.recognize_google(audio)
                        if text:  # Only process non-empty results
                            print(f"\n🎤 Human said: {text}")
                            self.last_voice_input = text
                            self.voice_queue.put(text)
                    except sr.UnknownValueError:
                        # Silent fail for unrecognized speech
                        pass
                    except sr.RequestError as e:
                        # Only print actual errors
                        print(f"Speech recognition error: {e}")
                        
            except KeyboardInterrupt:
                break
            except Exception as e:
                # Only print non-timeout errors
                if "timeout" not in str(e).lower():
                    print(f"Listening error: {e}")
                continue

    async def connect_websocket(self):
        """Connect to robot's body"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            await self.websocket.send("admin:123456")
            response = await self.websocket.recv()
            print(f"Connected! Response: {response}")
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            return False

    async def send_command(self, command):
        """Send command to robot's body, cancellable on interruption"""
        # If it's a speak command, mark as speaking
        if command.startswith("speak:"):
            self.currently_speaking = True
        
        tries = 3  # Number of connection retries
        for attempt in range(tries):
            try:
                # Check if we should interrupt
                if self.interrupt_event.is_set():
                    self.currently_speaking = False
                    return None
                    
                if self.websocket is None:
                    await self.connect_websocket()
                await self.websocket.send(command)
                response = await self.websocket.recv()
                
                # If command completed successfully, mark as not speaking
                if command.startswith("speak:"):
                    self.currently_speaking = False
                    
                return response
            except Exception as e:
                print(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                self.websocket = None
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
        
        # If we get here, command failed
        self.currently_speaking = False
        return None

    async def analyze_frame(self, frame):
        """Look at scene through dog's eyes using Claude API"""
        try:
            # Convert frame to base64
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            self.image_base64 = image_base64
            
            print("Sending image to Claude API for analysis...")
            
            try:
                # Create message with text and image content
                message = self.client.messages.create(
                    model=self.claude_model,
                    max_tokens=1024,
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world with curiosity and enthusiasm! You're playful, energetic, and always eager to interact with your environment. Respond in under 10 words!",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Looking at this image, respond with either:\n1. A movement command: forward, tiny_forward, backward, tiny_backward, left, little_left, right, little_right, bark, jump, or handshake\n2. An observation starting with \"speak:\"\n\nBe active and engaging! Mix different movements and share your excitement about what you see! Respond in under 10 words!"
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
                
                analysis = message.content[0].text.lower()
                print(f"Vision API response received!")
                print(f"Raw response: {analysis}")
                
            except Exception as e:
                print(f"Error with model {self.claude_model}: {e}")
                print("Attempting with alternative model claude-3-opus-20240229...")
                
                # Fallback to another model if available
                message = self.client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1024,
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world with curiosity and enthusiasm! You're playful, energetic, and always eager to interact with your environment. Respond in under 10 words!",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Looking at this image, respond with either:\n1. A movement command: forward, tiny_forward, backward, tiny_backward, left, little_left, right, little_right, bark, jump, or handshake\n2. An observation starting with \"speak:\"\n\nBe active and engaging! Mix different movements and share your excitement about what you see! Respond in under 10 words!"
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
                
                analysis = message.content[0].text.lower()
                print(f"Vision API response received from fallback model!")
                print(f"Raw response: {analysis}")
                
                # Update the model for future calls if successful
                self.claude_model = "claude-3-opus-20240229"
                print(f"Updated model to: {self.claude_model}")
            
            # Add randomness to encourage exploration
            if self.last_action == analysis.strip():
                self.action_count += 1
                if self.action_count >= 2:
                    print("🐕 Getting bored, trying something new!")
                    actions = ["forward", "backward", "left", "right", "bark", "jump", "handshake"]
                    analysis = random.choice(actions)
                    self.action_count = 0
            else:
                self.last_action = analysis.strip()
                self.action_count = 0
            
            # Random chance to get excited
            if random.random() < 0.15:
                actions = ["bark", "jump", "handshake", "left", "right"]
                surprise_action = random.choice(actions)
                print("🐕 Ooh! Something caught my attention!")
                return surprise_action
            
            print(f"🐕 I see: {analysis}")
            return analysis
                
        except Exception as e:
            print(f"Analysis error: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def generate_response(self, text, frame=None):
        """Generate a response using Claude API"""
        try:
            # Prepare content with or without image
            content = [
                {
                    "type": "text",
                    "text": f"Respond to this in under 50 words: {text}"
                }
            ]
            
            # Add image if available
            if self.image_base64:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": self.image_base64
                    }
                })
            
            try:
                # Create message with Claude client
                message = self.client.messages.create(
                    model=self.claude_model,
                    max_tokens=1024,
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world! Be concise, witty, and maintain your cheerful personality! Respond in under 10 words!",
                    messages=[
                        {
                            "role": "user",
                            "content": content
                        }
                    ]
                )
            except Exception as e:
                print(f"Error with model {self.claude_model}: {e}")
                print("Attempting with alternative model claude-3-opus-20240229...")
                
                # Fallback to another model
                message = self.client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1024,
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world! Be concise, witty, and maintain your cheerful personality! Respond in under 10 words!",
                    messages=[
                        {
                            "role": "user",
                            "content": content
                        }
                    ]
                )
                
                # Update model for future calls
                self.claude_model = "claude-3-opus-20240229"
                print(f"Updated model to: {self.claude_model}")
            
            return message.content[0].text.strip()

        except Exception as e:
            print(f"Response generation error: {e}")
            return "Woof! (Error processing response)"

    async def dog_reaction(self, perception):
        """React like a dog to what's seen"""
        if perception is None:
            return

        command = perception.strip().lower()
        print(f"🐕 Doing: {command}")

        # Extract command from text if it contains multiple words
        for cmd in ["forward", "tiny_forward", "backward", "tiny_backward", "left", "little_left", 
                   "right", "little_right", "jump", "handshake", "bark", "steady"]:
            if cmd in command:
                command = cmd
                break

        # Check if it's a speak command
        if "speak:" in command:
            text = command.split("speak:")[1].strip()
            print(f"*Speaking: {text}*")
            await self.send_command(f"speak:{text}")
            return

        # Add random chance for extra bark
        should_bark = random.random() < 0.2  # 20% chance to add bark

        # Basic movements
        if command == "forward":
            await self.send_command("forward")
            await self.send_command("forward")
            await asyncio.sleep(2.5)
            await self.send_command("DS")
            await self.send_command("DS")

        elif command == "tiny_forward":
            await self.send_command("forward")
            await asyncio.sleep(1.0)
            await self.send_command("DS")

        elif command == "backward":
            await self.send_command("backward")
            await self.send_command("backward")
            await asyncio.sleep(2.5)
            await self.send_command("DS")
            await self.send_command("DS")

        elif command == "tiny_backward":
            await self.send_command("backward")
            await asyncio.sleep(1.0)
            await self.send_command("DS")

        elif command == "left":
            await self.send_command(command)
            await self.send_command(command)
            await asyncio.sleep(2.3)
            await self.send_command("TS")
            await self.send_command("TS")

        elif command == "little_left":
            await self.send_command("left")
            await asyncio.sleep(1.0)
            await self.send_command("TS")

        elif command == "right":
            await self.send_command(command)
            await self.send_command(command)
            await asyncio.sleep(2.3)
            await self.send_command("TS")
            await self.send_command("TS")

        elif command == "little_right":
            await self.send_command("right")
            await asyncio.sleep(1.0)
            await self.send_command("TS")

        # Special actions
        elif command == "handshake":
            print("*Excited tail wagging* - A human!")
            await self.bark_sequence("excited")
            await self.send_command_multiple("handshake", times=4)

        elif command == "jump":
            print("*Super excited!*")
            await self.bark_sequence("excited")
            await self.send_command_multiple("jump", times=5)

        elif command == "steady":
            print("*Balancing carefully*")
            await self.send_command_multiple("steady", times=3)

        elif command == "bark":
            print("*Barking with personality!*")
            bark_type = random.choice(["short", "normal", "excited", "alert"])
            await self.bark_sequence(bark_type)

        # Random chance to look around after action
        if random.random() < 0.3:  # 30% chance
            look_dir = random.choice(["lookright", "lookleft"])
            await self.movement_sequence(look_dir, duration=1.0, stop_command="LRstop")
            
    async def run(self):
        """Main dog brain loop"""
        # Initialize thread variables before try/except to avoid UnboundLocalError
        video_thread = None
        voice_thread = None
        try:
            video_thread = threading.Thread(target=self.capture_video)
            voice_thread = threading.Thread(target=self.listen_for_voice)
            video_thread.start()
            voice_thread.start()
            
            print("Dog brain activated! Press Ctrl+C to stop.")

            # Wait for some initial frames to be captured
            wait_start = time.time()
            frame_received = False
            
            while time.time() - wait_start < 40 and not frame_received:
                if not self.frame_queue.empty():
                    frame_received = True
                    print("First video frame received!")
                    break
                print("Waiting for first video frame...")
                await asyncio.sleep(1)
            
            # Initial startup behavior
            print("🐕 Waking up and stretching!")
            await self.send_command("speak:Hello! I'm awake!")
            
            # if frame_received:
            #     frame = self.frame_queue.get()
            #     perception = await self.analyze_frame(frame)
            #     if perception:
            #         await self.dog_reaction(perception)
            # else:
            #     print("No video frames received during startup. Continuing without vision.")
                            
            last_visual_processing_time = 0
            visual_process_interval = 60  # Process visual input every 10 seconds
            last_posture_check_time = 0

            while self.running:
                # Process voice commands first
                current_time = time.time()
                
                while not self.voice_queue.empty():
                    command = self.voice_queue.get()
                    await self.process_voice_command(command)
                    await asyncio.sleep(0.1)
                
                 # Only perform autonomous actions if autonomous_mode is True
                if self.autonomous_mode:
                    # Process visual input (only if not currently responding to human)
                    if (not self.currently_speaking and 
                        current_time - last_visual_processing_time >= visual_process_interval):
                        if not self.frame_queue.empty():
                            print(f"Processing visual input (interval: {visual_process_interval}s)")
                            frame = self.frame_queue.get()
                            perception = await self.analyze_frame(frame)
                            if perception:
                                await self.dog_reaction(perception)
                            last_visual_processing_time = current_time
                    
                    # Check posture at regular intervals (only if not currently responding)
                    if (self.posture_model and not self.currently_speaking and 
                        current_time - last_posture_check_time >= self.posture_check_interval):
                        if not self.frame_queue.empty():
                            try:
                                # Use a copy of the frame to avoid removing it from the queue
                                frame_copy = self.frame_queue.queue[0].copy()
                                print("Checking posture...")
                                await self.detect_posture(frame_copy)
                                last_posture_check_time = current_time
                            except Exception as e:
                                print(f"Error during posture check: {e}")
                
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.running = False
            # Only join threads if they were successfully created and started
            if video_thread is not None:
                video_thread.join()
            if voice_thread is not None:
                voice_thread.join()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  
    
    ROBOT_IP = os.getenv('ROBOT_IP_ADDRESS')
    CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
    
    if not ROBOT_IP:
        ROBOT_IP = input("Enter your robot's IP address: ")
    if not CLAUDE_API_KEY:
        CLAUDE_API_KEY = input("Enter your Claude API key: ")
        
    print(f"Starting DogBrain with Robot IP: {ROBOT_IP}")
    brain = DogBrain(ROBOT_IP, CLAUDE_API_KEY)
    asyncio.run(brain.run())