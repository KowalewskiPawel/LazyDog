#!/usr/bin/env python3
# Security alert system

import asyncio
import time
import threading
import random

class AlertSystem:
    """Handles security alerts and responses"""
    
    def __init__(self, robot_connection, movement_controller):
        """Initialize alert system with robot connection and movement controller"""
        self.robot = robot_connection
        self.movement = movement_controller
        
        self.alerts_enabled = True
        self.is_alerting = False
        self.detection_cooldown = 30  # Seconds between alerts
        self.last_alert_time = 0
        
        # Generic warnings (used when Claude is not available)
        self.generic_warnings = [
            "Intruder detected! The police has been notified.",
            "Warning! This area is under surveillance.",
            "Security alert! The homeowner has been notified.",
            "Unauthorized access detected! Security system activated.",
            "This is a security robot. Please identify yourself."
        ]
        
        # Angry messages for failed challenge responses
        self.angry_messages = [
            "I've already called the police! Get out now!",
            "This is your final warning! Leave immediately!",
            "Security measures activated. You need to leave right now!",
            "Stop what you're doing and exit the premises immediately!",
            "You are trespassing! Get out or there will be consequences!"
        ]
    
    def trigger_alert(self, warning_message=None, failed_challenge=False, behavior="unknown", 
                     distance="unknown", resume_patrol_callback=None):
        """Trigger a security alert"""
        current_time = time.time()
        
        # Only alert if cooldown period has passed
        if current_time - self.last_alert_time < self.detection_cooldown:
            return False
        
        # Mark as alerting and update last alert time
        self.is_alerting = True
        self.last_alert_time = current_time
        
        # Start alert sequence in a separate thread
        alert_thread = threading.Thread(
            target=lambda: asyncio.run(
                self.alert_sequence(
                    warning_message, 
                    failed_challenge, 
                    behavior, 
                    distance,
                    resume_patrol_callback
                )
            )
        )
        alert_thread.daemon = True
        alert_thread.start()
        
        return True
    
    
    async def alert_sequence(self, warning_message=None, resume_patrol=False, failed_challenge=False):
        """Run the alert sequence with fixed commands and better timing"""
        try:
            print("⚠️ ALERT! Intruder detected!")
            
            # First, make the robot bark (with correct command)
            for _ in range(3):
                await self.robot.send_command("bark")  # FIXED: Direct "bark" command
                await asyncio.sleep(0.3)
            
            # Use provided warning message, generic fallback, or failure message for challenge
            if failed_challenge:
                # Use more aggressive message for failed challenge
                warning_message = random.choice(self.angry_messages)
            elif not warning_message:
                # Use generic warning message
                warning_message = random.choice(self.generic_warnings)
            
            # Speak the warning message directly addressing the intruder
            print(f"Speaking: {warning_message}")
            await self.robot.send_command(f"speak:{warning_message}")  # FIXED: No space after colon
            
            # Flash red lights
            for _ in range(3):
                await self.robot.send_command("light red")
                await asyncio.sleep(0.3)
                await self.robot.send_command("light off")
                await asyncio.sleep(0.2)
            
            # Enhanced movement sequence - more dynamic based on intruder behavior
            if self.intruder_behavior == "approaching":
                # More aggressive response if intruder is approaching
                await self.robot.send_command("steady")  # Stand steady
                await asyncio.sleep(0.5)
                
                # Jump to appear more intimidating if they're close
                if self.intruder_distance == "close":
                    await self.robot.send_command("jump")
                    await asyncio.sleep(1.5)  # Give more time for jump to complete
                
            elif self.intruder_behavior == "retreating":
                # Follow if retreating
                await self.robot.send_command("forward")
                await asyncio.sleep(1.0)
                await self.robot.send_command("DS")  # IMPORTANT: Stop movement
                
            else:
                # Standard response for other behaviors
                # Turn head to look for intruder with correct commands
                await self.robot.send_command("lookleft")  # FIXED: lowercase
                await asyncio.sleep(0.5)
                await self.robot.send_command("LRstop")
                await asyncio.sleep(0.5)
                await self.robot.send_command("lookright")  # FIXED: lowercase
                await asyncio.sleep(0.5)
                await self.robot.send_command("LRstop")
                
                # Turn body to face intruder
                direction = random.choice(["left", "right"])
                await self.robot.send_command(direction)
                await asyncio.sleep(0.8)
                await self.robot.send_command("TS")  # IMPORTANT: Stop turning
            
            # Only say a second message if the challenge failed (reduce verbosity)
            if failed_challenge:
                second_message = random.choice([
                    "Get out now!",
                    "Police notified!",
                    "Leave immediately!",
                    "Security activated!"
                ])
                
                await asyncio.sleep(1.0)  # Wait for first message to complete
                await self.robot.send_command(f"speak:{second_message}")  # FIXED: No space after colon
                
                # Additional actions based on behavior
                if self.intruder_behavior == "stationary":
                    await self.robot.send_command("handShake")
                    await asyncio.sleep(2.0)
            
            # Bark again after interactions (with correct command)
            for _ in range(2):
                await self.robot.send_command("bark")  # FIXED: Direct "bark" command
                await asyncio.sleep(0.3)
            
            # Pause before finishing alert
            await asyncio.sleep(1.0)
            
            self.is_alerting = False
            
            # Resume patrol if it was active before
            if resume_patrol:
                self.patrol_system.start()
            
        except Exception as e:
            print(f"Alert sequence error: {e}")
            self.is_alerting = False
            
            # Make sure we stop all movement in case of error
            try:
                await self.robot.send_command("DS")  # Stop forward/backward
                await self.robot.send_command("TS")  # Stop left/right
            except:
                pass
        
    def toggle_alerts(self, enable):
        """Toggle the alert system on/off"""
        self.alerts_enabled = enable
        print(f"Alerts {'enabled' if enable else 'disabled'}")
        return self.alerts_enabled
