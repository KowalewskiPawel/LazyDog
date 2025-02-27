#!/usr/bin/env python3
# Image saving and annotation

import os
import cv2
import datetime
import threading

class ImageSaver:
    """Handles saving and annotating images"""
    
    def __init__(self, save_dir="intruder_images"):
        """Initialize image saver with save directory"""
        # Create base directory if it doesn't exist
        self.base_dir = os.path.dirname(os.path.realpath(__file__))
        self.save_dir = os.path.join(os.path.dirname(self.base_dir), save_dir)
        os.makedirs(self.save_dir, exist_ok=True)
        
        print(f"Images will be saved to: {self.save_dir}")
    
    def save_detection(self, frame, person_boxes=None, target_box=None, 
                     behavior=None, distance=None, description=None):
        """Save a detection image to disk (non-blocking)"""
        try:
            # Run in separate thread to avoid blocking main loop
            save_thread = threading.Thread(
                target=self._save_worker,
                args=(
                    frame.copy(),
                    person_boxes,
                    target_box,
                    behavior,
                    distance,
                    description
                )
            )
            save_thread.daemon = True
            save_thread.start()
            return True
        except Exception as e:
            print(f"Error starting save thread: {e}")
            return False
    
    def _save_worker(self, frame, person_boxes, target_box, behavior, distance, description):
        """Worker function to save image in separate thread"""
        try:
            # Generate timestamp and filename
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"intruder_{timestamp}.jpg"
            filepath = os.path.join(self.save_dir, filename)
            
            # Add timestamp to the image
            timestamp_text = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, timestamp_text, (10, frame.shape[0] - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
            
            # Draw bounding boxes for persons
            if person_boxes:
                for box in person_boxes:
                    x1, y1, x2, y2, conf = box
                    # Highlight target person in red, others in green
                    is_target = (box == target_box)
                    color = (0, 0, 255) if is_target else (0, 255, 0)
                    
                    # Draw rectangle
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    
                    # Add label
                    label = f"{'Target' if is_target else 'Person'}: {conf:.2f}"
                    cv2.putText(frame, label, (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # Add behavior and distance information
            if behavior and distance:
                info_text = f"Behavior: {behavior}, Distance: {distance}"
                cv2.putText(frame, info_text, (10, 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            
            # Add description if available
            if description:
                # Split description into lines for better readability
                desc_lines = description.split('\n')
                for i, line in enumerate(desc_lines[:3]):  # Limit to first 3 lines
                    cv2.putText(frame, line, (10, 60 + i*20), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
            
            # Save image with optimized quality (95%)
            cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            print(f"Saved detection image to {filepath}")
        except Exception as e:
            print(f"Error saving detection image: {e}")
