#!/usr/bin/env python3
# Motion detection fallback when YOLO is not available

import cv2
import numpy as np
import time
import imutils

class MotionDetector:
    """Fallback motion detector when YOLO is not available"""
    
    def __init__(self):
        """Initialize motion detector"""
        self.avg = None  # Background model
        self.motion_detected = False
        self.motion_area = None  # (x, y, w, h) of motion area
        self.last_motion_time = 0
        
        # Detection settings
        self.consecutive_detections = 0
        self.detection_threshold_count = 3  # Consecutive detections required
        self.detection_threshold = 2000  # Minimum contour area to trigger
        self.frames_without_motion = 0
        self.motion_lost_threshold = 10  # Frames without motion before considering lost
    
    def detect_motion(self, frame):
        """Detect motion in frame"""
        try:
            # Get current timestamp
            timestamp = time.time()
            
            # Convert to grayscale and blur
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (21, 21), 0)
            
            # Initialize background model if none
            if self.avg is None:
                print("[INFO] Starting background model...")
                self.avg = gray.copy().astype("float")
                return False, None
            
            # Accumulate weighted average for background model
            cv2.accumulateWeighted(gray, self.avg, 0.5)
            
            # Calculate absolute difference between current frame and background
            frameDelta = cv2.absdiff(gray, cv2.convertScaleAbs(self.avg))
            
            # Threshold the delta image
            thresh = cv2.threshold(frameDelta, 5, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            
            # Find contours
            contours = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = imutils.grab_contours(contours)
            
            # Check for motion
            motion_detected = False
            for contour in contours:
                # Ignore small contours
                if cv2.contourArea(contour) < self.detection_threshold:
                    continue
                
                # Get bounding box
                (x, y, w, h) = cv2.boundingRect(contour)
                self.motion_area = (x, y, w, h)
                motion_detected = True
                self.last_motion_time = timestamp
                self.consecutive_detections += 1
                self.frames_without_motion = 0
                break
            
            # Update motion_detected status
            if not motion_detected:
                # Reset motion_detected if enough time has passed
                if timestamp - self.last_motion_time >= 0.5:
                    self.motion_detected = False
                
                # Increment frames without motion
                self.frames_without_motion += 1
                
                # Reset consecutive detections after several frames of no motion
                if self.frames_without_motion > 5:
                    self.consecutive_detections = 0
            else:
                self.motion_detected = True
            
            # Check if we have enough consecutive detections
            is_reliable = self.consecutive_detections >= self.detection_threshold_count
            
            return self.motion_detected, self.motion_area, is_reliable
            
        except Exception as e:
            print(f"Motion detection error: {e}")
            return False, None, False
    
    def annotate_frame(self, frame):
        """Add motion detection annotations to frame"""
        if not self.motion_detected or not self.motion_area:
            return frame
        
        annotated_frame = frame.copy()
        x, y, w, h = self.motion_area
        
        # Draw rectangle around motion area
        cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        # Add label
        cv2.putText(annotated_frame, "Motion", (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return annotated_frame
    
    def reset(self):
        """Reset the motion detector"""
        self.avg = None
        self.motion_detected = False
        self.motion_area = None
        self.consecutive_detections = 0
        self.frames_without_motion = 0
