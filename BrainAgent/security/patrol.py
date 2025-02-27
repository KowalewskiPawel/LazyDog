#!/usr/bin/env python3
# Patrol mode system

import asyncio
import time
import threading
import random

class PatrolSystem:
    """Handles patrol mode for the security system"""
    
    def __init__(self, robot_connection, movement_controller):
        """Initialize patrol system with robot connection and movement controller"""
        self.robot = robot_connection
        self.movement = movement_controller
        
        self.patrol_mode = False
        self.patrol_thread = None
        self.running = True
        
        # Patrol settings
        self.patrol_interval = 60  # Time between patrol movements in seconds
        self.last_patrol_time = 0
        self.patrol_sequence = ["forward", "left", "forward", "right", "forward"]
        self.patrol_index = 0
        self.patrol_random = True  # Use random movements for patrol
        self.patrol_counter = 0  # Counter to control announcement frequency
    
    def start(self):
        """Start patrol mode"""
        if self.patrol_mode:
            print("Patrol mode already active")
            return False
        
        self.patrol_mode = True
        print("Patrol mode enabled")
        
        # Start patrol thread
        self.patrol_thread = threading.Thread(target=self._patrol_worker)
        self.patrol_thread.daemon = True
        self.patrol_thread.start()
        
        return True
    
    def stop(self):
        """Stop patrol mode"""
        if not self.patrol_mode:
            return False
        
        self.patrol_mode = False
        print("Patrol mode disabled")
        
        # Thread will exit by itself due to the flag check
        return True
    
    def toggle(self):
        """Toggle patrol mode on/off"""
        if self.patrol_mode:
            return self.stop()
        else:
            return self.start()
    
    def _patrol_worker(self):
        """Worker function for patrol thread"""
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Run the patrol loop
            loop.run_until_complete(self._patrol_loop())
        finally:
            loop.close()
    
    async def _patrol_loop(self):
        """Run the patrol sequence in a loop"""
        print("Starting patrol sequence loop")
        
        # Define a set of possible patrol movements
        patrol_movements = [
            {"movement": "forward", "duration": 1.5},
            {"movement": "left", "duration": 0.8},
            {"movement": "right", "duration": 0.8},
            {"movement": "lookLeft", "duration": 0.5},
            {"movement": "lookRight", "duration": 0.5}
        ]
        
        # Run patrol loop until patrol mode is disabled
        while self.running and self.patrol_mode:
            try:
                current_time = time.time()
                
                # Check if it's time for a patrol movement
                if current_time - self.last_patrol_time >= self.patrol_interval:
                    print("Performing patrol movement")
                    self.last_patrol_time = current_time
                    
                    # Only announce patrol occasionally to reduce verbosity (every 3rd patrol)
                    self.patrol_counter += 1
                    if self.patrol_counter % 3 == 0:
                        await self.robot.send_command("speak:Patrolling")
                    
                    # Choose movement pattern
                    if self.patrol_random:
                        # Random patrol pattern
                        # Pick 2-3 movements
                        num_movements = random.randint(2, 3)
                        for _ in range(num_movements):
                            # Check if patrol is still active
                            if not self.patrol_mode:
                                break
                                
                            # Choose random movement
                            move = random.choice(patrol_movements)
                            
                            # Execute movement
                            await self.robot.send_command(move["movement"])
                            await asyncio.sleep(move["duration"])
                            
                            # Stop movement
                            if move["movement"] in ["forward", "backward"]:
                                await self.robot.send_command("DS")
                            elif move["movement"] in ["left", "right"]:
                                await self.robot.send_command("TS")
                            elif move["movement"] in ["lookLeft", "lookRight"]:
                                await self.robot.send_command("LRstop")
                                
                            await asyncio.sleep(0.5)  # Pause between movements
                    else:
                        # Sequential patrol pattern
                        if self.patrol_index >= len(self.patrol_sequence):
                            self.patrol_index = 0
                            
                        # Get next movement in sequence
                        movement = self.patrol_sequence[self.patrol_index]
                        self.patrol_index += 1
                        
                        # Perform the movement
                        await self.robot.send_command(movement)
                        await asyncio.sleep(1.0)
                        
                        # Stop movement
                        if movement in ["forward", "backward"]:
                            await self.robot.send_command("DS")
                        elif movement in ["left", "right"]:
                            await self.robot.send_command("TS")
                    
                    # Look around after patrol movement
                    await self.movement.look_around()
                    
                    # Occasionally reset position 
                    if random.random() < 0.2:  # 20% chance to reset
                        await self.movement.middle_position()
                    
                    # Occasionally bark during patrol
                    if random.random() < 0.3:  # 30% chance to bark
                        await self.robot.bark_sequence("short")
                
                # Sleep for a bit to avoid busy waiting
                await asyncio.sleep(5)
                
            except Exception as e:
                print(f"Patrol error: {e}")
                await asyncio.sleep(5)  # Sleep longer on error
        
        print("Patrol sequence loop ended")
    
    def shutdown(self):
        """Shutdown patrol system"""
        self.running = False
        self.patrol_mode = False