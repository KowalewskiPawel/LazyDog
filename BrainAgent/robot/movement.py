#!/usr/bin/env python3
# Robot movement control module

import asyncio
import time
import threading
import random

class MovementController:
    """Controls robot movements and sequences"""
    
    def __init__(self, robot_connection):
        """Initialize with robot connection"""
        self.robot = robot_connection
        self.last_movement_command = None
        self.last_movement_time = 0
        self.movement_cooldown = 1.0  # Seconds between movements
    
    async def stop_all(self):
        """Stop all robot movement"""
        await self.robot.send_command("DS")  # Stop forward/backward
        await self.robot.send_command("TS")  # Stop left/right
        await self.robot.send_command("LRstop")  # Stop head left/right
        await self.robot.send_command("UDstop")  # Stop head up/down
    
    async def reset_position(self):
        """Reset robot to initial position"""
        print("Resetting robot position...")
        
        # Stop any ongoing movements
        await self.stop_all()
        
        # Reset to initial position
        await self.robot.send_command("InitPos")
        await asyncio.sleep(2.0)
        
        print("Robot position reset complete.")
    
    async def middle_position(self):
        """Move robot to middle position"""
        print("Moving robot to middle position...")
        
        # Stop any ongoing movements
        await self.stop_all()
        
        # Go to middle position
        await self.robot.send_command("MiddlePos")
        await asyncio.sleep(2.0)
        
        print("Robot moved to middle position.")
    
    async def look_around(self, speed=0.5):
        """Make the robot look around"""
        # Look left
        await self.robot.send_command("lookLeft")
        await asyncio.sleep(speed)
        await self.robot.send_command("LRstop")
        
        await asyncio.sleep(0.2)
        
        # Look right
        await self.robot.send_command("lookRight")
        await asyncio.sleep(speed)
        await self.robot.send_command("LRstop")
    
    async def track_person(self, center_x, center_y, width, height, frame_width, frame_height):
        """Track and follow a detected person"""
        current_time = time.time()
        if current_time - self.last_movement_time < self.movement_cooldown:
            return  # Don't move too frequently
        
        # Calculate frame center
        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2
        
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
        
        # Calculate area percentage with smoothing
        area_percent = (width * height) / (frame_width * frame_height) * 100
        
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
                await self.robot.send_command(cmd)
                # Small delay between commands to let robot process
                await asyncio.sleep(0.05)
            
            self.last_movement_time = current_time
    
    async def perform_alert_movement(self, behavior="unknown", distance="unknown"):
        """Perform movement based on detected behavior during alert"""
        if behavior == "approaching":
            # More aggressive response if intruder is approaching
            await self.robot.send_command("steady")  # Stand steady
            await asyncio.sleep(0.5)
            
            # Jump to appear more intimidating if they're close
            if distance == "close":
                await self.robot.send_command("jump")
                await asyncio.sleep(1.0)
            
        elif behavior == "retreating":
            # Follow if retreating
            await self.robot.send_command("forward")
            await asyncio.sleep(1.0)
            await self.robot.send_command("DS")
            
        else:
            # Standard response for other behaviors
            # Turn head to look for intruder
            await self.look_around()
            
            # Turn body to face intruder
            direction = random.choice(["left", "right"])
            await self.robot.send_command(direction)
            await asyncio.sleep(0.8)
            await self.robot.send_command("TS")
    
    def track_in_background(self, center_x, center_y, width, height, frame_width, frame_height):
        """Run tracking in background thread to avoid blocking"""
        tracking_thread = threading.Thread(
            target=lambda: asyncio.run(
                self.track_person(center_x, center_y, width, height, frame_width, frame_height)
            )
        )
        tracking_thread.daemon = True
        tracking_thread.start()
