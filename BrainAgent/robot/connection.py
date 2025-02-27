#!/usr/bin/env python3
# WebSocket connection and command handling for the robot

import asyncio
import websockets
import time
import threading
import queue
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RobotConnection")

class RobotConnection:
    """Handles connection and commands to the robot via WebSocket"""
    
    def __init__(self, robot_ip):
        """Initialize connection with robot IP"""
        self.robot_ip = robot_ip
        self.ws_url = f"ws://{robot_ip}:8888"
        self.video_url = f"http://{robot_ip}:5000/video_feed"
        
        # WebSocket state
        self.websocket = None
        self.connected = False
        self.running = True
        self.connection_lock = threading.Lock()
        
        # Command queue for processing
        self.command_queue = queue.Queue()
        
        # Create a dedicated event loop for the command processor
        self._command_loop = None
        
        # Start command processor thread
        self.command_thread = threading.Thread(target=self._command_processor_thread)
        self.command_thread.daemon = True
        self.command_thread.start()
        
        logger.info(f"Robot connection initialized for {robot_ip}")
    
    def _command_processor_thread(self):
        """Thread that processes commands from the queue using its own event loop"""
        # Create a new event loop for this thread
        self._command_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._command_loop)
        
        logger.info("Command processor thread started")
        
        try:
            # Run the command processor coroutine
            self._command_loop.run_until_complete(self._process_commands())
        except Exception as e:
            logger.error(f"Command processor error: {e}")
        finally:
            # Clean up
            self._command_loop.close()
            logger.info("Command processor thread stopped")
    
    async def _process_commands(self):
        """Process commands from the queue"""
        while self.running:
            try:
                # Non-blocking check for commands
                if not self.command_queue.empty():
                    command = self.command_queue.get_nowait()
                    
                    # Process the command
                    try:
                        response = await self._send_command_internal(command)
                        # If command has a callback, call it with the response
                        if isinstance(command, tuple) and len(command) > 1 and callable(command[1]):
                            command[1](response)
                    except Exception as e:
                        logger.error(f"Error processing command '{command}': {e}")
                    finally:
                        # Mark the command as done
                        if isinstance(command, tuple) and len(command) > 1:
                            self.command_queue.task_done()
                        else:
                            self.command_queue.task_done()
                
                # Sleep briefly to avoid spinning
                await asyncio.sleep(0.01)
            except queue.Empty:
                # Queue is empty, sleep a bit longer
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Command processing error: {e}")
                await asyncio.sleep(0.1)
    
    async def _send_command_internal(self, command):
        """Send a command to the robot (internal implementation)"""
        if isinstance(command, tuple):
            cmd = command[0]
        else:
            cmd = command
            
        tries = 3  # Number of connection retries
        last_error = None
        
        for attempt in range(tries):
            try:
                # Ensure we have a connection
                if not self.connected or self.websocket is None:
                    await self._connect_internal()
                    if not self.connected:
                        await asyncio.sleep(1)
                        continue
                
                # Send the command
                await self.websocket.send(cmd)
                logger.info(f"Sent command: {cmd}")
                
                # Wait for response
                response = await self.websocket.recv()
                return response
                
            except Exception as e:
                logger.error(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                last_error = e
                self.connected = False
                self.websocket = None
                
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
        
        # If we get here, all attempts failed
        if last_error:
            logger.error(f"All command attempts failed: {last_error}")
        return None
    
    async def _connect_internal(self):
        """Connect to the robot's WebSocket server (internal implementation)"""
        try:
            # Create a new connection
            self.websocket = await websockets.connect(self.ws_url)
            
            # Authenticate
            await self.websocket.send("admin:123456")
            response = await self.websocket.recv()
            
            if "Connected" in response:
                logger.info(f"Connected to robot! Response: {response}")
                self.connected = True
                return True
            else:
                logger.error(f"Authentication failed: {response}")
                self.connected = False
                return False
                
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.websocket = None
            self.connected = False
            return False
    
    def queue_command(self, command, callback=None):
        """Add a command to the queue for asynchronous execution"""
        if callback:
            self.command_queue.put((command, callback))
        else:
            self.command_queue.put(command)
        return True
    
    async def send_command(self, command):
        """Send command to robot via WebSocket"""
        tries = 3  # Number of connection retries
        
        for attempt in range(tries):
            try:
                if self.websocket is None:
                    # Check if the connect method is 'connect' or 'connect_websocket'
                    if hasattr(self, 'connect'):
                        await self.connect()  # Use your existing connect method
                    else:
                        # If neither method exists, implement basic connection here
                        self.websocket = await websockets.connect(self.ws_url)
                        await self.websocket.send("admin:123456")
                        response = await self.websocket.recv()
                        print(f"Connected to robot! Response: {response}")
                    
                    if self.websocket is None:
                        time.sleep(1)
                        continue
                
                # Ensure command has correct format
                if command.startswith("speak:") and " " in command and command[6] != " ":
                    # Fix speak command format - some robots require no space after colon
                    command = command.replace("speak: ", "speak:")
                
                # Send command
                await self.websocket.send(command)
                print(f"Sent command: {command}")
                
                # Wait for response with timeout to prevent hanging
                response = await asyncio.wait_for(self.websocket.recv(), timeout=2.0)
                return response
                
            except asyncio.TimeoutError:
                print(f"Command timed out: {command}")
                self.websocket = None
                
            except Exception as e:
                print(f"Command error (attempt {attempt + 1}/{tries}): {e}")
                self.websocket = None
                
                if attempt < tries - 1:
                    await asyncio.sleep(1)  # Wait before retry
        
        return None
        
    # Public API methods
    def speak(self, text):
        """Queue a speak command with correct format"""
        # Format should be: speak:Text with no space after colon
        command = f"speak:{text}"
        async def send_speak():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                await self.send_command(command)
            finally:
                loop.close()
        
        # Run in a separate thread to avoid blocking
        threading.Thread(target=lambda: asyncio.run(send_speak()), daemon=True).start()
        return True

    def light(self, color):
        """Control robot lights"""
        return self.queue_command(f"light {color}")
    
    def buzzer(self, state):
        """Control robot buzzer (0=off, 1=on)"""
        return self.queue_command(f"buzzer {state}")
    
    def move(self, direction):
        """Move the robot in a direction (forward, backward, left, right)"""
        return self.queue_command(direction)
    
    def stop(self):
        """Stop the robot's movement"""
        self.queue_command("DS")  # Stop forward/backward
        self.queue_command("TS")  # Stop left/right
        return True
    
    def bark(self):
        """Make the robot bark"""
        async def send_bark():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                await self.send_command("bark")
            finally:
                loop.close()
    
    def bark_sequence(self, intensity="normal"):
        """Execute a bark sequence with a specific pattern"""
        patterns = {
            "short": [(0.1, 0.1)],
            "normal": [(0.2, 0.1), (0.2, 0.1)],
            "excited": [(0.1, 0.05), (0.1, 0.05), (0.2, 0.1)],
            "alert": [(0.3, 0.1), (0.1, 0.05), (0.1, 0.05)]
        }
        
        pattern = patterns.get(intensity, patterns["normal"])
        
        # Run the bark sequence in a separate thread to avoid blocking
        def run_sequence():
            for duration, pause in pattern:
                self.queue_command("buzzer 1")
                time.sleep(duration)
                self.queue_command("buzzer 0")
                time.sleep(pause)
        
        threading.Thread(target=run_sequence, daemon=True).start()
        return True
    
    def shutdown(self):
        """Shutdown the connection manager"""
        logger.info("Shutting down robot connection")
        self.running = False
        
        # Wait for the command queue to empty
        try:
            self.command_queue.join(timeout=2.0)
        except:
            pass
            
        # Close the WebSocket if it's open
        if self.websocket and self._command_loop:
            async def close_ws():
                try:
                    await self.websocket.close()
                except:
                    pass
                
            future = asyncio.run_coroutine_threadsafe(close_ws(), self._command_loop)
            try:
                future.result(timeout=2.0)
            except:
                pass
        
        logger.info("Robot connection shut down")
