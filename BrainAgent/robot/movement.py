#!/usr/bin/env python3
# Robot movement control module

import asyncio
import time
import threading
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MovementController")

class MovementController:
    """Controls robot movements and sequences"""
    
    def __init__(self, robot_connection):
        """Initialize with robot connection"""
        self.robot = robot_connection
        self.last_movement_command = None
        self.last_movement_time = 0
        self.movement_cooldown = 1.0  # Seconds between movements
        
        logger.info("Movement controller initialized")
    
    def stop_all(self):
        """Stop all robot movement"""
        self.robot.queue_command("DS")  # Stop forward/backward
        self.robot.queue_command("TS")  # Stop left/right
        self.robot.queue_command("LRstop")  # Stop head left/right
        self.robot.queue_command("UDstop")  # Stop head up/down
        logger.info("Stopped all movement")
        return True
    
    def reset_position(self):
        """Reset robot to initial position"""
        logger.info("Resetting robot position...")
        
        # Stop any ongoing movements
        self.stop_all()
        
        # Reset to initial position
        self.robot.queue_command("InitPos")
        
        # Add a small delay to let the robot complete the movement
        time.sleep(2.0)
        
        logger.info("Robot position reset complete")
        return True
    
    def middle_position(self):
        """Move robot to middle position"""
        logger.info("Moving robot to middle position...")
        
        # Stop any ongoing movements
        self.stop_all()
        
        # Go to middle position
        self.robot.queue_command("MiddlePos")
        
        # Add a small delay to let the robot complete the movement
        time.sleep(2.0)
        
        logger.info("Robot moved to middle position")
        return True
    
    async def look_around(self, speed=0.5):
        """Make the robot look around - fixed with correct commands and proper stops"""
        # Look left with correct command
        await self.robot.send_command("lookleft")  # FIXED: lowercase "lookleft"
        await asyncio.sleep(speed)
        await self.robot.send_command("LRstop")
        
        await asyncio.sleep(0.2)  # Brief pause between movements
        
        # Look right with correct command
        await self.robot.send_command("lookright")  # FIXED: lowercase "lookright" 
        await asyncio.sleep(speed)
        await self.robot.send_command("LRstop")
    
    def track_person(self, center_x, center_y, width, height, frame_width, frame_height):
        """Track and follow a detected person - improved logic for better tracking"""
        current_time = time.time()
        if current_time - self.last_movement_time < self.movement_cooldown:
            return False  # Don't move too frequently
        
        # Calculate frame center
        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2
        
        # Calculate offsets from center
        offset_x = center_x - frame_center_x
        offset_y = center_y - frame_center_y
        
        # Determine movement commands
        commands_to_send = []
        
        # Calculate area percentage (person size relative to frame)
        area_percent = (width * height) / (frame_width * frame_height) * 100
        logger.info(f"Person area: {area_percent:.1f}%, offset_x: {offset_x}, offset_y: {offset_y}")
        
        # Check if the person is centered horizontally (within a tolerance)
        is_centered = abs(offset_x) < 60
        
        # If person is not in frame (called with invalid coordinates), turn to search
        if center_x <= 0 or center_y <= 0 or center_x >= frame_width or center_y >= frame_height:
            # No person detected, do search pattern
            # Alternate looking left and right with a short duration
            if self.last_movement_command != "search":
                # Choose a random direction for initial search
                search_direction = "left" if random.random() < 0.5 else "right"
                commands_to_send.append(search_direction)
                commands_to_send.append("search")  # Not a real command, just to track state
                self.last_movement_command = "search"
            return self._send_movement_commands(commands_to_send)
        
        # Check if we've reached the person (close enough to interact)
        person_reached = area_percent > 40  # Person takes up significant portion of frame
        
        if person_reached:
            # We've reached the person, stop and interact
            commands_to_send.append("DS")  # Stop forward/backward movement
            commands_to_send.append("TS")  # Stop turning
            self.last_movement_command = "reached"
            
            # Make the robot bark and trigger Claude to generate a message
            def interaction_sequence():
                # First bark to get attention
                self.robot.bark_sequence("excited")
                time.sleep(0.5)
                
                # Try to get Claude to generate a message if available
                try:
                    if hasattr(self.robot, 'claude_vision') and self.robot.claude_vision.available:
                        # If Claude is available, use it to generate a personalized message
                        description = self.robot.claude_vision.intruder_description
                        if not description or len(description) < 10:
                            # Use a generic greeting if no description
                            self.robot.speak("Hello there! I've found you.")
                        else:
                            # Try to generate a greeting based on the description
                            warning = self.robot.claude_vision.generated_warning
                            if warning and len(warning) > 10:
                                self.robot.speak(warning)
                            else:
                                self.robot.speak(f"Hello! I see you there. {description[:50]}")
                    else:
                        # Fall back to generic greeting
                        self.robot.speak("Hello! I've been looking for you.")
                except Exception as e:
                    logger.error(f"Error in interaction sequence: {e}")
                    # Fall back to generic greeting
                    self.robot.speak("Hello there!")
            
            # Run interaction in a separate thread to avoid blocking
            threading.Thread(target=interaction_sequence, daemon=True).start()
            
        elif is_centered:
            # Person is centered but not close enough - move forward
            if self.last_movement_command != "forward":
                commands_to_send.append("forward")
                self.last_movement_command = "forward"
        else:
            # Person is not centered - turn to center them
            if offset_x < -60:  # Person is to the left
                if self.last_movement_command != "left":
                    commands_to_send.append("left")
                    self.last_movement_command = "left"
            elif offset_x > 60:  # Person is to the right
                if self.last_movement_command != "right":
                    commands_to_send.append("right")
                    self.last_movement_command = "right"
        
        # Handle vertical tracking for head movement
        if offset_y < -40:  # Person is above center
            commands_to_send.append("lookUp")
        elif offset_y > 40:  # Person is below center
            commands_to_send.append("lookDown")
        else:
            commands_to_send.append("UDstop")  # Stop vertical head movement
        
        return self._send_movement_commands(commands_to_send)

    def _send_movement_commands(self, commands):
        """Helper method to send movement commands with small delays"""
        if not commands:
            return False
        
        # Queue commands with small delays
        def send_commands():
            for cmd in commands:
                # Skip "search" as it's just a state marker, not a real command
                if cmd != "search":
                    self.robot.queue_command(cmd)
                    time.sleep(0.05)  # Small delay between commands
        
        # Run in a separate thread to avoid blocking
        threading.Thread(target=send_commands, daemon=True).start()
        
        # Update last movement time
        self.last_movement_time = time.time()
        return True
        
    def perform_alert_movement(self, behavior="unknown", distance="unknown"):
        """Perform movement based on detected behavior during alert"""
        logger.info(f"Performing alert movement for behavior: {behavior}, distance: {distance}")
        
        if behavior == "approaching":
            # More aggressive response if intruder is approaching
            self.robot.queue_command("steady")  # Stand steady
            time.sleep(0.5)
            
            # Jump to appear more intimidating if they're close
            if distance == "close":
                self.robot.queue_command("jump")
                time.sleep(1.0)
            
        elif behavior == "retreating":
            # Follow if retreating
            self.robot.queue_command("forward")
            time.sleep(1.0)
            self.robot.queue_command("DS")
            
        else:
            # Standard response for other behaviors
            # Turn head to look for intruder
            self.look_around()
            
            # Turn body to face intruder
            direction = random.choice(["left", "right"])
            self.robot.queue_command(direction)
            time.sleep(0.8)
            self.robot.queue_command("TS")
        
        return True
    
    def run_async_safely(self, coro):
        """Run an async coroutine safely from any context"""
        async def wrapper():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return await coro
            finally:
                loop.close()
        
        return asyncio.run(wrapper())

    def track_in_background(self, center_x, center_y, width, height, frame_width, frame_height):
        """Run tracking in background thread with proper async handling"""
        def tracking_worker():
            asyncio.run(self.track_person(center_x, center_y, width, height, frame_width, frame_height))
        
        # Start a new thread with its own event loop
        tracking_thread = threading.Thread(target=tracking_worker)
        tracking_thread.daemon = True
        tracking_thread.start()
