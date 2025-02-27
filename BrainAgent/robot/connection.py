#!/usr/bin/env python3
# WebSocket connection and command handling for the robot

import asyncio
import websockets
import time
import threading
from queue import Queue

class RobotConnection:
    """Handles connection and commands to the robot via WebSocket"""
    
    def __init__(self, robot_ip):
        """Initialize connection with robot IP"""
        self.robot_ip = robot_ip
        self.ws_url = f"ws://{robot_ip}:8888"
        self.video_url = f"http://{robot_ip}:5000/video_feed"
        self.websocket = None
        self.connected = False
        self.running = True
        
        # Command queue for async execution
        self.command_queue = Queue()
        
        # Start command processor thread
        self.command_thread = threading.Thread(target=self._process_commands)
        self.command_thread.daemon = True
        self.command_thread.start()
    
    async def connect(self):
        """Connect to the robot WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            await self.websocket.send("admin:123456")
            response = await self.websocket.recv()
            print(f"Connected to robot! Response: {response}")
            self.connected = True
            return True
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.websocket = None
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from the robot WebSocket server"""
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                print(f"Error disconnecting: {e}")
            finally:
                self.websocket = None
                self.connected = False
    
    async def send_command(self, command):
        """Send a command to the robot via WebSocket"""
        tries = 3  # Number of connection retries
        
        for attempt in range(tries):
            try:
                if self.websocket is None or not self.connected:
                    await self.connect()
                    if self.websocket is None:
                        await asyncio.sleep(1)
                        continue
                
                await self.websocket.send(command)
                print(f"Sent command: {command}")
                return await self.websocket.recv()
            except Exception as e:
                print(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                self.websocket = None
                self.connected = False
                
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
        
        return None
    
    def queue_command(self, command):
        """Add a command to the queue for async execution"""
        self.command_queue.put(command)
    
    def _process_commands(self):
        """Process commands from the queue in a separate thread"""
        while self.running:
            if not self.command_queue.empty():
                command = self.command_queue.get()
                
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    # Execute the command
                    loop.run_until_complete(self.send_command(command))
                except Exception as e:
                    print(f"Error processing command: {e}")
                finally:
                    loop.close()
            
            # Small delay to prevent CPU hogging
            time.sleep(0.05)
    
    async def send_command_multiple(self, command, times=3, delay=0.1):
        """Send a command multiple times with delay to ensure it's received"""
        responses = []
        for _ in range(times):
            response = await self.send_command(command)
            responses.append(response)
            await asyncio.sleep(delay)
        return responses
    
    def speak(self, text):
        """Send a speak command to the robot"""
        self.queue_command(f"speak:{text}")
    
    def light(self, color):
        """Control robot lights"""
        self.queue_command(f"light {color}")
    
    def buzzer(self, state):
        """Control robot buzzer (0=off, 1=on)"""
        self.queue_command(f"buzzer {state}")
    
    async def bark_sequence(self, intensity="normal"):
        """Execute a bark sequence with variable patterns"""
        patterns = {
            "short": [(0.1, 0.1)],
            "normal": [(0.2, 0.1), (0.2, 0.1)],
            "excited": [(0.1, 0.05), (0.1, 0.05), (0.2, 0.1)],
            "alert": [(0.3, 0.1), (0.1, 0.05), (0.1, 0.05)]
        }
        
        pattern = patterns.get(intensity, patterns["normal"])
        for duration, pause in pattern:
            await self.send_command("buzzer 1")
            await asyncio.sleep(duration)
            await self.send_command("buzzer 0")
            await asyncio.sleep(pause)
    
    def shutdown(self):
        """Shutdown the connection manager"""
        self.running = False
        
        # Create a new event loop for final disconnect
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self.disconnect())
        finally:
            loop.close()
