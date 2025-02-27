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
    
    async def alert_sequence(self, warning_message=None, failed_challenge=False, 
                           behavior="unknown", distance="unknown", resume_patrol_callback=None):
        """Run the alert sequence"""
        try:
            print("⚠️ ALERT! Intruder detected!")
            
            # First, make the robot bark
            await self.robot.bark_sequence("alert")
            
            # Use provided warning message, generic fallback, or failure message for challenge
            if failed_challenge:
                # Use more aggressive message for failed challenge
                warning_message = random.choice(self.angry_messages)
            elif not warning_message:
                # Use generic warning message
                warning_message = random.choice(self.generic_warnings)
            
            # Speak the warning message directly addressing the intruder
            print(f"Speaking: {warning_message}")
            await self.robot.send_command(f"speak:{warning_message}")
            
            # Flash red lights
            for _ in range(3):  # Reduced from 5 to be less verbose
                await self.robot.send_command("light red")
                await asyncio.sleep(0.3)
                await self.robot.send_command("light off")
                await asyncio.sleep(0.2)
            
            # Perform movement based on detected behavior
            await self.movement.perform_alert_movement(behavior, distance)
            
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
                behavior_messages = second_messages.get(behavior, [
                    "Police notified!",
                    "Leave now!",
                    "Face recorded!",
                    "Get out!"
                ])
                
                second_message = random.choice(behavior_messages)
                await self.robot.send_command(f"speak:{second_message}")
                
                # Additional actions based on behavior
                if behavior == "stationary":
                    await self.robot.send_command("handShake")
                    await asyncio.sleep(2.0)
            
            # Bark again after interactions
            await self.robot.bark_sequence("excited")
            
            # Pause before finishing alert
            await asyncio.sleep(3.0)
            
            self.is_alerting = False
            
            # Resume patrol if callback provided
            if resume_patrol_callback:
                resume_patrol_callback()
            
        except Exception as e:
            print(f"Alert sequence error: {e}")
            self.is_alerting = False
    
    def toggle_alerts(self, enable):
        """Toggle the alert system on/off"""
        self.alerts_enabled = enable
        print(f"Alerts {'enabled' if enable else 'disabled'}")
        return self.alerts_enabled
