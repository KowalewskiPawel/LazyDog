import asyncio
import websockets
import cv2
import json
import base64
import threading
import random
from queue import Queue
import requests
import time
import speech_recognition as sr
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

class DogBrain:
    def __init__(self, robot_ip, grok_api_key):
        self.robot_ip = robot_ip
        self.ws_url = f"ws://{robot_ip}:8888"
        self.video_url = f"http://{robot_ip}:5000/video_feed"
        self.websocket = None
        self.running = True
        self.frame_queue = Queue(maxsize=2)
        self.last_action = None
        self.action_count = 0
        self.recognizer = sr.Recognizer()
        self.voice_queue = Queue()
        self.last_voice_input = None
        self.image_base64 = ''
        
        # X.AI (Grok) API configuration
        self.grok_api_key = grok_api_key
        self.grok_api_url = "https://api.x.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {grok_api_key}",
            "Content-Type": "application/json"
        }
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
        """Process voice commands in Turkish"""
        text = text.lower().strip()
        print(f"🎯 İşleniyor: {text}")
        
        # Turkish command mapping
        commands = {
            "forward": ["ileri", "yürü", "git", "düz git"],
            "backward": ["geri", "geri git", "geriye"],
            "left": ["sol", "sola", "sola dön"],
            "right": ["sağ", "sağa", "sağa dön"],
            "jump": ["zıpla", "atla", "hopla"],
            "handshake": ["pati", "pati ver", "selamlaş"],
            "bark": ["havla", "ses ver", "konuş"],
            "steady": ["dengede dur", "sabit dur", "sakin"],
            "stop": ["dur", "durdu", "bekle"]
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
        
        # If not a command, generate a response
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
        """Listen for Turkish voice input"""
        print("Dinliyorum... Robo-köpeğinize bir şey söyleyin!")
        
        while self.running:
            try:
                with sr.Microphone() as source:
                    if random.random() < 0.1:
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    audio = self.recognizer.listen(source, 
                                                phrase_time_limit=5,
                                                timeout=None)
                    
                    try:
                        text = self.recognizer.recognize_google(audio, language="tr-TR")
                        if text:
                            print(f"\n🎤 İnsan dedi ki: {text}")
                            self.last_voice_input = text
                            self.voice_queue.put(text)
                    except sr.UnknownValueError:
                        pass
                    except sr.RequestError as e:
                        print(f"Ses tanıma hatası: {e}")
                        
            except KeyboardInterrupt:
                break
            except Exception as e:
                if "timeout" not in str(e).lower():
                    print(f"Dinleme hatası: {e}")
                continue

    def capture_video(self):
        """Capture video frames in a separate thread"""
        print("Starting dog vision... (Video preview disabled on macOS)")
        cap = cv2.VideoCapture(self.video_url)

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
                
                # No display attempt on macOS - just process frames

        cap.release()

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
        """Analyze scene using Polish prompts"""
        try:
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            self.image_base64 = image_base64
            
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": """Sen dünyayı keşfetmeyi seven neşeli ve meraklı bir robo-köpeksin! 
Enerjik ve çevrenle etkileşime girmeye her zaman heveslisin."""
                    },
                    {
                        "role": "user",
                        "content": """Bu görüntüye bakarak şunlardan birini yanıtla:
1. Hareket komutu: ileri, küçük_adım, geri, küçük_geri_adım, sol, hafif_sol, sağ, hafif_sağ, havla, zıpla, veya pati
2. "söyle:" ile başlayan bir gözlem

Aktif ve ilgili ol! Farklı hareketleri karıştır ve gördüklerinden duyduğun heyecanı paylaş!""",
                        "image": image_base64
                    }
                ],
                "model": "grok-2-latest",
                "stream": False,
                "temperature": 0.9
            }

            # Make API call
            response = requests.post(
                self.grok_api_url,
                headers=self.headers,
                json=payload,
                timeout=30  # Added timeout
            )
            
            if response.status_code == 200:
                analysis = response.json()['choices'][0]['message']['content'].lower()
                print(f"Raw API response: {response.json()}")  # Debug line
                
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
                
            else:
                print(f"API Error: {response.status_code} - {response.text}")  # Debug line
                return None
                
        except Exception as e:
            print(f"Analysis error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def generate_response_to_question(self, question):
        """Generate a response using X.AI API with vision support"""
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": """Sen dünyayı keşfetmeyi seven neşeli ve maceracı bir robo-köpeksin!"""
                },
                {
                    "role": "user",
                    "content": f"""Bu soru/cümleye yanıt ver: {question}

Kurallar:
- Kısa ve esprili ol
- Robotik ve heyecanlı bir dil karışımı kullan
- Eğer bir görüntü varsa, yanıtında ondan bahset
- Yanıtlar şöyle olabilir:
1. Heyecanlı bir gözlem ("söyle:" ile başlayan)
2. Doğrudan bir cevap
3. Oyuncu bir yorum

Yanıtları 50 kelimeden kısa tut ve neşeli karakterini koru!""",
                    "image": self.image_base64 if self.image_base64 else None
                }
            ],
            "model": "grok-2-latest",
            "stream": False,
            "temperature": 0.7
        }

        response = requests.post(
            self.grok_api_url,
            headers=self.headers,
            json=payload
        )

        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            return "Woof! (API Error)"

    async def dog_reaction(self, perception):
        """React like a dog to what's seen"""
        if perception is None:
            return

        command = perception.strip().lower()
        print(f"🐕 Doing: {command}")

        # Add random chance for extra bark
        should_bark = random.random() < 0.2  # 20% chance to add bark

        # Basic movements
        if command == "forward":
            await self.send_command("forward")
            await self.send_command("forward")
            await asyncio.sleep(2.5)
            await self.send_command("DS")
            await self.send_command("DS")
            await self.send_command("DS")

        elif command.startswith("speak:"):
            text = command.split("speak:")[1].strip()
            print(f"*Speaking: {text}*")
            await self.send_command_multiple("speak", times=2)
            await self.send_command(f"speak: {text}")

        elif command == "backward":
            await self.send_command("backward")
            await self.send_command("backward")
            await asyncio.sleep(2.5)
            await self.send_command("DS")
            await self.send_command("DS")
            await self.send_command("DS")

        elif command in ["left", "right"]:
            await self.send_command(command)
            await self.send_command(command)
            await asyncio.sleep(2.3)
            await self.send_command("TS")
            await self.send_command("TS")
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
            
    async def generate_response(self, text, frame=None):
        """Generate a response using X.AI API"""
        try:
            payload = {
                "messages": [
                    {
                        "role": "system",
                        "content": """Sen dünyayı keşfetmeyi seven neşeli ve maceracı bir robo-köpeksin!
Kısa, esprili ve neşeli karakterini koru!"""
                    },
                    {
                        "role": "user",
                        "content": f"Buna 50 kelimeden kısa yanıt ver: {text}",
                        "image": self.image_base64 if self.image_base64 else None
                    }
                ],
                "model": "grok-2-latest",
                "stream": False,
                "temperature": 0.7
            }

            response = requests.post(
                self.grok_api_url,
                headers=self.headers,
                json=payload,
                timeout=30  # Added timeout
            )

            if response.status_code == 200:
                print(f"Raw API response: {response.json()}")  # Debug line
                return response.json()['choices'][0]['message']['content'].strip()
            else:
                print(f"API Error: {response.status_code} - {response.text}")  # Debug line
                return "Woof! (API Error)"

        except Exception as e:
            print(f"Response generation error: {e}")
            return "Woof! (Error processing response)"

    async def run(self):
            """Main dog brain loop"""
            try:
                video_thread = threading.Thread(target=self.capture_video)
                voice_thread = threading.Thread(target=self.listen_for_voice)
                video_thread.start()
                voice_thread.start()
                
                print("Dog brain activated! Press Ctrl+C to stop.")
                print("Speak to your robo-dog!")

                # Initial startup behavior
                print("🐕 Waking up and stretching!")
                await self.send_command("speak:Merhaba! Uyandım!")
                frame = self.frame_queue.get()
                perception = await self.analyze_frame(frame)
                if perception:
                    await self.dog_reaction(perception)
                                
                last_visual_processing_time = 0
                process_interval = random.uniform(2.5, 3.5)  # Random interval

                while self.running:
                    # Process voice commands first
                    current_time = time.time()
                    
                    while not self.voice_queue.empty():
                        command = self.voice_queue.get()
                        await self.process_voice_command(command)
                        await asyncio.sleep(0.1)
                    
                    # Then process visual input
                    if current_time - last_visual_processing_time >= 30:
                        if not self.frame_queue.empty():
                            frame = self.frame_queue.get()
                            perception = await self.analyze_frame(frame)
                            if perception:
                                await self.dog_reaction(perception)
                            
                    # Update the last processing time
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

    ROBOT_IP = os.getenv('ROBOT_IP_ADDRESS')  # Your robot's IP
    GROK_API_KEY = os.getenv('GROK_API_KEY') # Your Grok API key
    brain = DogBrain(ROBOT_IP, GROK_API_KEY)
    asyncio.run(brain.run())