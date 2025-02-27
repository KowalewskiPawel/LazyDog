#!/usr/bin/env python3
# Robot movement control module

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
    
    def look_around(self, speed=0.5):
        """Make the robot look around"""
        # Look left
        self.robot.queue_command("lookLeft")
        time.sleep(speed)
        self.robot.queue_command("LRstop")
        
        time.sleep(0.2)
        
        # Look right
        self.robot.queue_command("lookRight")
        time.sleep(speed)
        self.robot.queue_command("LRstop")
        
        return True
    
    def track_person(self, center_x, center_y, width, height, frame_width, frame_height):
        """Track and follow a detected person - non-blocking version that uses the command queue"""
        current_time = time.time()
        if current_time - self.last_movement_time < self.movement_cooldown:
            return False  # Don't move too frequently
        
        # Calculate frame center
        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2
        
        # Calculate offsets from center
        offset_x = center_x - frame_center_x
        offset_y = center_y - frame_center_y
        
        # Determine movement commands with hysteresis to prevent jitter
        commands_to_send = []
        
        # Horizontal tracking with wider threshold (turn left/right)
        if offset_x < -70:  # Person is significantly to the left
            if self.last_movement_command != "left":
                commands_to_send.append("left")
                self.last_movement_command = "left"
        elif offset_x > 70:  # Person is significantly to the right
            if self.last_movement_command != "right":
                commands_to_send.append("right")
                self.last_movement_command = "right"
        elif -30 <= offset_x <= 30:  # Person is centered horizontally
            if self.last_movement_command in ["left", "right"]:
                commands_to_send.append("TS")  # Stop turning
                self.last_movement_command = None
        
        # Vertical tracking with wider threshold (look up/down)
        if offset_y < -50:  # Person is significantly above center
            commands_to_send.append("lookUp")
        elif offset_y > 50:  # Person is significantly below center
            commands_to_send.append("lookDown")
        elif -20 <= offset_y <= 20:  # Person is centered vertically
            commands_to_send.append("UDstop")  # Stop looking up/down
        
        # Calculate area percentage with smoothing
        area_percent = (width * height) / (frame_width * frame_height) * 100
        
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
        
        # Send commands with small delays between them
        if commands_to_send:
            # Queue commands with small delays
            def send_commands():
                for cmd in commands_to_send:
                    self.robot.queue_command(cmd)
                    time.sleep(0.05)  # Small delay between commands
            
            # Run in a separate thread to avoid blocking
            threading.Thread(target=send_commands, daemon=True).start()
            
            # Update last movement time
            self.last_movement_time = current_time
            return True
        
        return False
    
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
    
    def track_in_background(self, center_x, center_y, width, height, frame_width, frame_height):
        """Run tracking in background thread to avoid blocking"""
        tracking_thread = threading.Thread(
            target=self.track_person,
            args=(center_x, center_y, width, height, frame_width, frame_height)
        )
        tracking_thread.daemon = True
        tracking_thread.start()
        return True
