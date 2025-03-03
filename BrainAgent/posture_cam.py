import cv2
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import time
import threading
import queue

def draw_keypoints(frame, keypoints, confidence_threshold):
    """Draw keypoints and skeleton on the frame."""
    y, x, c = frame.shape
    shaped = np.squeeze(np.multiply(keypoints, [y, x, 1]))
    
    # COCO keypoint connections
    edges = [
        (0, 1), (0, 2), (1, 3), (2, 4),  # Face connections
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),  # Arms
        (5, 11), (6, 12), (11, 12),  # Body
        (11, 13), (13, 15), (12, 14), (14, 16)  # Legs
    ]
    
    # Draw the keypoints
    for kp in shaped:
        ky, kx, kp_conf = kp
        if kp_conf > confidence_threshold:
            cv2.circle(frame, (int(kx), int(ky)), 4, (0, 255, 0), -1)
    
    # Draw the skeleton
    for edge in edges:
        p1, p2 = edge
        y1, x1, c1 = shaped[p1]
        y2, x2, c2 = shaped[p2]
        
        if (c1 > confidence_threshold and c2 > confidence_threshold):
            cv2.line(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
    
    return frame

class RobotCameraStream:
    def __init__(self, robot_ip="192.168.4.1", port=5000):
        """Initialize the robot camera stream."""
        self.video_url = f"http://{robot_ip}:{port}/video_feed"
        self.running = True
        self.frame_queue = queue.Queue(maxsize=10)
        self.last_frame_time = 0
        self.frame_capture_success = False
        self.capture_thread = None
        
    def connect(self):
        """Start the video capture thread."""
        self.capture_thread = threading.Thread(target=self.capture_video)
        self.capture_thread.daemon = True
        self.capture_thread.start()
        
        # Wait for the first frame or timeout
        timeout = 1  # seconds
        start_time = time.time()
        while not self.frame_capture_success and time.time() - start_time < timeout:
            time.sleep(0.1)
            
        return self.frame_capture_success
            
    def capture_video(self):
        """Capture video frames in a separate thread"""
        print(f"Starting robot vision... Connecting to {self.video_url}")
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                cap = cv2.VideoCapture(self.video_url)
                if not cap.isOpened():
                    print(f"Failed to open video stream at {self.video_url}, retrying...")
                    retry_count += 1
                    time.sleep(2)
                    continue
                
                print("Video stream successfully opened!")
                self.frame_capture_success = True
                retry_count = 0  # Reset retry count on success
                
                while self.running:
                    ret, frame = cap.read()
                    if ret:
                        # Clear queue if full
                        if self.frame_queue.full():
                            try:
                                self.frame_queue.get_nowait()
                            except:
                                pass
                        self.frame_queue.put(frame)
                        self.last_frame_time = time.time()
                    else:
                        print("Failed to read frame, reconnecting...")
                        break
                        
                    # Throttle capture rate
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"Video capture error: {e}")
                retry_count += 1
                time.sleep(2)
            finally:
                try:
                    cap.release()
                except:
                    pass
                
        if retry_count >= max_retries:
            print("Maximum video capture retries reached. Vision may not be available.")
            self.frame_capture_success = False
    
    def read_frame(self):
        """Get the latest frame from the queue."""
        try:
            if not self.frame_queue.empty():
                frame = self.frame_queue.get(timeout=0.5)
                return True, frame
            else:
                # Check if capture is still working
                if time.time() - self.last_frame_time > 5 and self.last_frame_time > 0:
                    print("No frames received recently, stream may be disconnected")
                return False, None
        except queue.Empty:
            return False, None
        except Exception as e:
            print(f"Error reading frame: {e}")
            return False, None
    
    def close(self):
        """Stop the video capture thread."""
        self.running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=1.0)

def main():
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Robot Camera Posture Detection')
    parser.add_argument('--ip', type=str, default='192.168.4.1', help='Robot IP address')
    parser.add_argument('--port', type=int, default=5000, help='Robot video server port')
    parser.add_argument('--model', type=str, default='lightning', 
                        choices=['lightning', 'thunder'], 
                        help='MoveNet model type (lightning is faster, thunder is more accurate)')
    args = parser.parse_args()
    
    # Load the MoveNet model
    try:
        print("Loading MoveNet model...")
        if args.model == 'lightning':
            model_url = "https://tfhub.dev/google/movenet/singlepose/lightning/4"
        else:
            model_url = "https://tfhub.dev/google/movenet/singlepose/thunder/4"
            
        model = hub.load(model_url)
        movenet = model.signatures['serving_default']
        print(f"Model {args.model} loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        return
    
    # Initialize the robot camera
    robot_camera = RobotCameraStream(robot_ip=args.ip, port=args.port)
    print(f"Connecting to robot camera at {args.ip}:{args.port}...")
    if not robot_camera.connect():
        print("Failed to connect to robot camera. Check your connection and robot IP.")
        return
    
    print("Robot camera connected. Press 'q' to quit, 's' to save a screenshot.")
    
    # FPS calculation variables
    frame_count = 0
    start_time = time.time()
    fps = 0
    
    # Create output window
    cv2.namedWindow('Robot Posture Camera', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Robot Posture Camera', 800, 600)
    
    while True:
        # Capture frame from robot camera
        ret, frame = robot_camera.read_frame()
        
        if not ret or frame is None:
            print("Waiting for valid frame...")
            time.sleep(0.1)
            # Show waiting message
            blank_image = np.zeros((480, 640, 3), np.uint8)
            cv2.putText(blank_image, "Waiting for camera stream...", (150, 240), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow('Robot Posture Camera', blank_image)
            # Check for quit command
            key = cv2.waitKey(100) & 0xFF
            if key == ord('q'):
                break
            continue
        
        # Calculate FPS
        frame_count += 1
        if frame_count >= 10:
            end_time = time.time()
            fps = frame_count / (end_time - start_time)
            frame_count = 0
            start_time = time.time()
        
        try:
            # Convert the image to RGB for the model
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize and pad the image for the model
            input_size = 256 if args.model == 'thunder' else 192
            img = tf.image.resize_with_pad(tf.expand_dims(frame_rgb, axis=0), input_size, input_size)
            img = tf.cast(img, dtype=tf.int32)
            
            # Run inference
            results = movenet(img)
            keypoints = results['output_0'].numpy()
            
            # Draw the keypoints on the frame
            confidence_threshold = 0.3
            frame_with_keypoints = draw_keypoints(frame.copy(), keypoints[0, 0, :, :], confidence_threshold)
            
            # Add FPS and instructions
            cv2.putText(frame_with_keypoints, f"FPS: {fps:.1f}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame_with_keypoints, "Press 'q' to quit, 's' to save screenshot", (10, 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Display the resulting frame
            cv2.imshow('Robot Posture Camera', frame_with_keypoints)
        except Exception as e:
            print(f"Error processing frame: {e}")
            # Show error on frame
            cv2.putText(frame, f"Error: {str(e)}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.imshow('Robot Posture Camera', frame)
            
        # Check for key presses
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            # Save screenshot
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            filename = f"robot_posture_{timestamp}.jpg"
            cv2.imwrite(filename, frame_with_keypoints)
            print(f"Screenshot saved as {filename}")
    
    # Release resources
    robot_camera.close()
    cv2.destroyAllWindows()
    print("Application closed.")

if __name__ == "__main__":
    main()