#!/usr/bin/env python3
# Intruder behavior analysis

import numpy as np
import time

class BehaviorAnalyzer:
    """Analyzes intruder behavior based on position and movement"""
    
    def __init__(self):
        """Initialize the behavior analyzer"""
        # Behavior tracking
        self.intruder_behavior = "unknown"  # unknown, approaching, retreating, stationary, moving_left, moving_right
        self.previous_positions = []  # Store previous positions to analyze movement
        self.max_positions = 10
        self.behavior_confidence = 0
        self.intruder_distance = "unknown"  # far, medium, close
        
        # Frame dimensions
        self.frame_width = 640  # Default frame width
        self.frame_height = 480  # Default frame height
    
    def update_frame_dimensions(self, width, height):
        """Update the frame dimensions"""
        self.frame_width = width
        self.frame_height = height
    
    def analyze(self, x1, y1, x2, y2):
        """Analyze intruder behavior based on position and dimensions"""
        # Calculate center and dimensions
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        width = x2 - x1
        height = y2 - y1
        
        # Calculate relative position in frame
        rel_x = cx / self.frame_width  # 0.0 to 1.0 (left to right)
        rel_y = cy / self.frame_height  # 0.0 to 1.0 (top to bottom)
        rel_size = (width * height) / (self.frame_width * self.frame_height)  # Relative size
        
        # Add to position history
        self.previous_positions.append((cx, cy, rel_size, time.time()))
        if len(self.previous_positions) > self.max_positions:
            self.previous_positions.pop(0)
        
        # Determine distance category based on relative size
        if rel_size > 0.15:
            self.intruder_distance = "close"
        elif rel_size > 0.05:
            self.intruder_distance = "medium"
        else:
            self.intruder_distance = "far"
        
        # Need at least 3 positions to analyze movement
        if len(self.previous_positions) < 3:
            return self.intruder_behavior, self.intruder_distance
        
        # Analyze movement direction and speed
        movement_x = 0
        movement_y = 0
        size_change = 0
        count = 0
        
        for i in range(1, len(self.previous_positions)):
            prev_x, prev_y, prev_size, prev_time = self.previous_positions[i-1]
            curr_x, curr_y, curr_size, curr_time = self.previous_positions[i]
            
            if curr_time - prev_time > 1.0:  # Skip if time gap is too large
                continue
                
            movement_x += curr_x - prev_x
            movement_y += curr_y - prev_y
            size_change += curr_size - prev_size
            count += 1
        
        if count > 0:
            avg_movement_x = movement_x / count
            avg_movement_y = movement_y / count
            avg_size_change = size_change / count
            
            # Determine behavior based on movement
            if abs(avg_movement_x) < 5 and abs(avg_movement_y) < 5 and abs(avg_size_change) < 0.01:
                self.intruder_behavior = "stationary"
            elif avg_size_change > 0.01:
                self.intruder_behavior = "approaching"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            elif avg_size_change < -0.01:
                self.intruder_behavior = "retreating"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            elif abs(avg_movement_x) > 10:
                if avg_movement_x > 0:
                    self.intruder_behavior = "moving_right"
                else:
                    self.intruder_behavior = "moving_left"
                self.behavior_confidence = min(self.behavior_confidence + 1, 10)
            else:
                # If not confident, maintain previous behavior
                self.behavior_confidence = max(self.behavior_confidence - 1, 0)
                if self.behavior_confidence < 3:
                    self.intruder_behavior = "unknown"
        
        return self.intruder_behavior, self.intruder_distance
    
    def reset(self):
        """Reset the behavior analyzer"""
        self.intruder_behavior = "unknown"
        self.previous_positions = []
        self.behavior_confidence = 0
        self.intruder_distance = "unknown"
