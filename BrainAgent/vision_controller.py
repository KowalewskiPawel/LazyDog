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
        
        # Claude client initialization
        self.claude_api_key = claude_api_key
        self.client = anthropic.Anthropic(api_key=claude_api_key)
        
        # Use Claude 3.7 Sonnet model
        self.claude_model = "claude-3-7-sonnet-20250219"
        
        print(f"Dog brain initializing with Robot IP: {robot_ip}")
        print(f"Video URL set to: {self.video_url}")
        print(f"Using Claude model: {self.claude_model}")
        print("Dog brain ready to explore!")

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
            "stop": ["stop", "halt", "freeze"]
        }
        
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
                await self.execute_command(command)
                return True
        
        # If not a command, generate a short response
        response = await self.generate_response(text)
        await self.send_command(f"speak:{response}")
        return True

    async def execute_command(self, command):
        """Execute commands with proper timing and repetition"""
        try:
            if command == "forward":
                for _ in range(3):
                    await self.send_command(command)
                await asyncio.sleep(10.0)
                await self.send_command("DS")
                
            elif command == "backward":
                for _ in range(3):
                    await self.send_command(command)
                await asyncio.sleep(8.0)
                await self.send_command("DS")
                
            elif command == "left":
                for _ in range(2):
                    await self.send_command(command)
                await asyncio.sleep(5.5)
                await self.send_command("TS")
                
            elif command == "right":
                for _ in range(2):
                    await self.send_command(command)
                await asyncio.sleep(5.5)
                await self.send_command("TS")
                
            elif command == "little_left":
                await self.send_command("left")
                await asyncio.sleep(2.0)
                await self.send_command("TS")
                
            elif command == "little_right":
                await self.send_command("right")
                await asyncio.sleep(2.0)
                await self.send_command("TS")
                
            elif command == "tiny_forward":
                await self.send_command("forward")
                await asyncio.sleep(3.0)
                await self.send_command("DS")
                
            elif command == "tiny_backward":
                await self.send_command("backward")
                await asyncio.sleep(3.0)
                await self.send_command("DS")
                
            elif command in ["jump", "handshake", "bark"]:
                for _ in range(2):
                    await self.send_command(command)
                    await asyncio.sleep(10.5)
                    
        except Exception as e:
            print(f"Command execution error: {e}")
            
    def listen_for_voice(self):
        """Listen for voice input in a separate thread"""
        print("Starting to listen... Speak to your robo-dog!")
        
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
        """Send command to robot's body"""
        tries = 3  # Number of connection retries
        for attempt in range(tries):
            try:
                if self.websocket is None:
                    await self.connect_websocket()
                await self.websocket.send(command)
                return await self.websocket.recv()
            except Exception as e:
                print(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                self.websocket = None
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
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
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world with curiosity and enthusiasm! You're playful, energetic, and always eager to interact with your environment.",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Looking at this image, respond with either:\n1. A movement command: forward, tiny_forward, backward, tiny_backward, left, little_left, right, little_right, bark, jump, or handshake\n2. An observation starting with \"speak:\"\n\nBe active and engaging! Mix different movements and share your excitement about what you see!"
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
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world with curiosity and enthusiasm! You're playful, energetic, and always eager to interact with your environment.",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Looking at this image, respond with either:\n1. A movement command: forward, tiny_forward, backward, tiny_backward, left, little_left, right, little_right, bark, jump, or handshake\n2. An observation starting with \"speak:\"\n\nBe active and engaging! Mix different movements and share your excitement about what you see!"
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
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world! Be concise, witty, and maintain your cheerful personality!",
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
                    system="You are a cheerful and adventurous robo-dog who loves exploring the world! Be concise, witty, and maintain your cheerful personality!",
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
        try:
            video_thread = threading.Thread(target=self.capture_video)
            voice_thread = threading.Thread(target=self.listen_for_voice)
            video_thread.start()
            voice_thread.start()
            
            print("Dog brain activated! Press Ctrl+C to stop.")
            print("Speak to your robo-dog!")

            # Wait for some initial frames to be captured
            wait_start = time.time()
            frame_received = False
            
            while time.time() - wait_start < 10 and not frame_received:
                if not self.frame_queue.empty():
                    frame_received = True
                    print("First video frame received!")
                    break
                print("Waiting for first video frame...")
                await asyncio.sleep(1)
            
            # Initial startup behavior
            print("🐕 Waking up and stretching!")
            await self.send_command("speak:Hello! I'm awake!")
            
            if frame_received:
                frame = self.frame_queue.get()
                perception = await self.analyze_frame(frame)
                if perception:
                    await self.dog_reaction(perception)
            else:
                print("No video frames received during startup. Continuing without vision.")
                            
            last_visual_processing_time = 0
            visual_process_interval = 10  # Process visual input every 10 seconds

            while self.running:
                # Process voice commands first
                current_time = time.time()
                
                while not self.voice_queue.empty():
                    command = self.voice_queue.get()
                    await self.process_voice_command(command)
                    await asyncio.sleep(0.1)
                
                # Then process visual input every 10 seconds
                if current_time - last_visual_processing_time >= visual_process_interval:
                    if not self.frame_queue.empty():
                        print(f"Processing visual input (interval: {visual_process_interval}s)")
                        frame = self.frame_queue.get()
                        perception = await self.analyze_frame(frame)
                        if perception:
                            await self.dog_reaction(perception)
                        last_visual_processing_time = current_time
                
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            print("\nPutting the dog to sleep...")
        finally:
            self.running = False
            video_thread.join()
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