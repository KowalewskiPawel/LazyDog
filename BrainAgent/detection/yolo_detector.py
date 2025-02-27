#!/usr/bin/env python3
# YOLO-based person detection

import cv2
import numpy as np
import time
from ultralytics import YOLO

class YoloDetector:
    """Person detector using YOLO"""
    
    def __init__(self, model_path="yolov8n.pt"):
        """Initialize YOLO detector"""
        self.model = None
        self.available = False
        self.last_detection_time = 0
        self.detection_cooldown = 0.1  # Seconds between detections
        
        # Detection history
        self.person_detected = False
        self.person_count = 0
        self.person_boxes = []
        self.consecutive_detections = 0
        self.detection_threshold = 3  # Number of consecutive detections required
        self.frames_without_person = 0
        self.person_lost_threshold = 10  # Frames without detection before considering person lost
        
        # Target tracking
        self.target_person_box = None
        
        # Try to load YOLO model
        try:
            self.model = YOLO(model_path)
            print(f"YOLO model loaded successfully from {model_path}")
            self.available = True
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            print("YOLO detection will not be available")
    
    def detect_persons(self, frame):
        """Detect persons in the frame using YOLO"""
        if not self.available or self.model is None:
            return False, []
        
        current_time = time.time()
        if current_time - self.last_detection_time < self.detection_cooldown:
            return self.person_detected, self.person_boxes
        
        self.last_detection_time = current_time
        
        try:
            # Run YOLO detection with performance optimization
            results = self.model(frame, classes=[0], verbose=False)  # Class 0 is person in COCO dataset
            
            # Process results
            self.person_boxes = []
            self.person_count = 0
            
            # Check for people in results
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Extract box coordinates and convert to integers
                    box_coords = box.xyxy[0].tolist()
                    x1, y1, x2, y2 = [int(coord) for coord in box_coords]
                    conf = float(box.conf[0])
                    
                    # Only count high-confidence detections
                    if conf > 0.5:  # Confidence threshold
                        self.person_count += 1
                        self.person_boxes.append((x1, y1, x2, y2, conf))
            
            # Update person detection status
            previous_person_detected = self.person_detected
            self.person_detected = self.person_count > 0
            
            if self.person_detected:
                self.consecutive_detections += 1
                self.frames_without_person = 0
                
                # Select best person to track
                self.select_target_person()
            else:
                self.frames_without_person += 1
                
                # Reset consecutive detections after several frames of no person
                if self.frames_without_person > 5:
                    self.consecutive_detections = 0
                
                # Clear target if person lost for too long
                if self.frames_without_person > self.person_lost_threshold:
                    self.target_person_box = None
            
            return self.person_detected, self.person_boxes
            
        except Exception as e:
            print(f"YOLO detection error: {e}")
            return False, []
    
    def select_target_person(self):
        """Select the best person to track based on size and position"""
        if not self.person_boxes:
            return
        
        # If no target, pick the largest person
        if self.target_person_box is None:
            # Find the largest person (by area)
            largest_area = 0
            largest_box = None
            
            for box in self.person_boxes:
                x1, y1, x2, y2, conf = box
                area = (x2 - x1) * (y2 - y1)
                
                if area > largest_area:
                    largest_area = area
                    largest_box = box
            
            self.target_person_box = largest_box
        else:
            # We're already tracking, find the closest person to our current target
            # Get center of current target
            x1, y1, x2, y2, _ = self.target_person_box
            target_cx = (x1 + x2) // 2
            target_cy = (y1 + y2) // 2
            
            # Find closest person
            closest_dist = float('inf')
            closest_box = None
            
            for box in self.person_boxes:
                x1, y1, x2, y2, conf = box
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                
                # Calculate Euclidean distance
                dist = np.sqrt((cx - target_cx)**2 + (cy - target_cy)**2)
                
                if dist < closest_dist:
                    closest_dist = dist
                    closest_box = box
            
            self.target_person_box = closest_box
    
    def get_target_info(self):
        """Get information about the current target"""
        if self.target_person_box is None:
            return None
        
        x1, y1, x2, y2, conf = self.target_person_box
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        width = x2 - x1
        height = y2 - y1
        
        return {
            "center_x": center_x,
            "center_y": center_y,
            "width": width,
            "height": height,
            "confidence": conf,
            "box": (x1, y1, x2, y2)
        }
    
    def is_reliable_detection(self):
        """Check if we have enough consecutive detections to be reliable"""
        return self.consecutive_detections >= self.detection_threshold
    
    def annotate_frame(self, frame):
        """Add bounding boxes and labels to the frame"""
        if not self.person_detected or not self.person_boxes:
            return frame
        
        annotated_frame = frame.copy()
        
        for box in self.person_boxes:
            x1, y1, x2, y2, conf = box
            # Highlight target person in red, others in green
            is_target = (box == self.target_person_box)
            color = (0, 0, 255) if is_target else (0, 255, 0)
            
            # Draw rectangle
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            
            # Add label
            label = f"{'Target' if is_target else 'Person'}: {conf:.2f}"
            cv2.putText(annotated_frame, label, (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return annotated_frame
