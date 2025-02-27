#!/usr/bin/env python3
# Camera feed processor module

import cv2
import time
import threading
from queue import Queue

class CameraFeed:
    """Handles video capture and frame processing"""
    
    def __init__(self, video_url, frame_skip=2):
        """Initialize camera feed with video URL"""
        self.video_url = video_url
        self.running = True
        self.frame_skip = frame_skip  # Process only every Nth frame
        
        # Frame processing - optimized
        self.frame_queue = Queue(maxsize=5)  # Reduced queue size to prevent memory build-up
        self.current_frame = None
        
        # Frame dimensions
        self.frame_width = 640  # Default frame width
        self.frame_height = 480  # Default frame height
        
        # Performance tracking
        self.fps = 0
        self.frame_count = 0
        self.last_fps_time = time.time()
        
    def start_capture(self):
        """Start video capture in a separate thread"""
        capture_thread = threading.Thread(target=self.capture_video)
        capture_thread.daemon = True
        capture_thread.start()
        
    def capture_video(self):
        """Capture video frames from robot's stream"""
        print(f"Starting video capture from {self.video_url}")
        
        retry_count = 0
        max_retries = 10
        frame_count = 0
        
        while self.running and retry_count < max_retries:
            try:
                # Open video stream
                cap = cv2.VideoCapture(self.video_url)
                if not cap.isOpened():
                    print(f"Failed to open video stream, retrying ({retry_count+1}/{max_retries})...")
                    retry_count += 1
                    time.sleep(2)
                    continue
                
                print("Video stream successfully opened!")
                retry_count = 0  # Reset on success
                
                # Process frames
                while self.running:
                    ret, frame = cap.read()
                    if not ret:
                        print("Failed to read frame, reconnecting...")
                        break
                    
                    # Update frame dimensions (only occasionally to save processing)
                    if frame_count % 30 == 0:
                        self.frame_width = frame.shape[1]
                        self.frame_height = frame.shape[0]
                    
                    frame_count += 1
                    
                    # Skip frames to improve performance
                    if frame_count % self.frame_skip != 0:
                        continue
                    
                    # Store frame in queue (with minimal copying)
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                        self.current_frame = frame  # Keep a reference to current frame
                    else:
                        try:
                            self.frame_queue.get_nowait()  # Remove old frame
                            self.frame_queue.put(frame)
                            self.current_frame = frame
                        except:
                            pass
                    
                    # Update FPS counter
                    self.frame_count += 1
                    current_time = time.time()
                    if current_time - self.last_fps_time >= 1.0:
                        self.fps = self.frame_count
                        self.frame_count = 0
                        self.last_fps_time = current_time
                    
                    # Throttle capture rate slightly
                    time.sleep(0.03)
                    
            except Exception as e:
                print(f"Video capture error: {e}")
                retry_count += 1
                time.sleep(2)
            finally:
                try:
                    cap.release()
                except:
                    pass
                    
        print("Video capture stopped")
    
    def get_next_frame(self):
        """Get the next frame from the queue"""
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        return None
    
    def get_current_frame(self):
        """Get the current frame (non-blocking)"""
        return self.current_frame
    
    def get_frame_dimensions(self):
        """Get the current frame dimensions"""
        return self.frame_width, self.frame_height
    
    def get_fps(self):
        """Get the current FPS"""
        return self.fps
    
    def stop(self):
        """Stop video capture"""
        self.running = False
