#!/usr/bin/env python3
# Main watchdog controller

import time
import threading

from robot.connection import RobotConnection
from robot.movement import MovementController
from detection.yolo_detector import YoloDetector
from detection.behavior_analyzer import BehaviorAnalyzer
from security.voice_challenge import VoiceChallenger
from security.alert_system import AlertSystem
from security.patrol import PatrolSystem
from vision.claude_api import ClaudeVision
from vision.image_saver import ImageSaver
from ui.display import WatchdogDisplay
from ui.camera_feed import CameraFeed

class RobotWatchdog:
    """Main watchdog controller that ties all components together"""
    
    def __init__(self, robot_ip, claude_api_key=None, use_yolo=True, 
                use_voice=True, use_display=True, frame_skip=2, 
                high_performance=False):
        """Initialize watchdog with required components"""
        # Core settings
        self.running = True
        self.enabled = False
        self.last_status_time = 0
        
        # Create robot connection
        self.robot = RobotConnection(robot_ip)
        
        # Create movement controller
        self.movement = MovementController(self.robot)
        
        # Create camera feed
        video_url = f"http://{robot_ip}:5000/video_feed"
        self.camera = CameraFeed(video_url, frame_skip=frame_skip)
        
        # Create YOLO detector
        self.detector = YoloDetector()
        self.use_yolo = use_yolo and self.detector.available
        
        # Create behavior analyzer
        self.behavior_analyzer = BehaviorAnalyzer()
        
        # Create voice challenger
        self.voice_challenger = VoiceChallenger(self.robot)
        self.use_voice = use_voice and self.voice_challenger.available
        
        # Create alert system
        self.alert_system = AlertSystem(self.robot, self.movement)
        
        # Create patrol system
        self.patrol_system = PatrolSystem(self.robot, self.movement)
        
        # Create Claude vision if API key provided
        self.claude_vision = ClaudeVision(claude_api_key)
        
        # Create image saver
        self.image_saver = ImageSaver()
        
        # Create display
        self.display = WatchdogDisplay(self, use_display)
        
        # Performance settings
        if high_performance:
            # Increase performance settings
            self.camera.frame_skip = max(3, self.camera.frame_skip)  # Skip more frames
            self.movement.movement_cooldown = 1.5  # Longer delay between movements
            self.claude_vision.analysis_interval = 30  # Less frequent Claude analysis
            self.detector.detection_threshold = 5  # Require more detections before alerting
            print("High performance mode enabled - prioritizing speed over responsiveness")
        
        # First person detection
        self.first_detection = True
        
        # Tracking settings
        self.tracking_enabled = True
        
        print("Watchdog system initialized with components:")
        print(f"- YOLO Detection: {'Enabled' if self.use_yolo else 'Disabled'}")
        print(f"- Voice Challenge: {'Enabled' if self.use_voice else 'Disabled'}")
        print(f"- Claude Vision: {'Enabled' if self.claude_vision.available else 'Disabled'}")
        print(f"- Display: {'Enabled' if use_display else 'Disabled'}")
    
    def run(self):
        """Run the watchdog system"""
        # Start camera capture
        self.camera.start_capture()
        
        # Minimal startup announcement
        self.robot.speak("Security system activated.")
        
        # Main loop
        try:
            while self.running:
                # Get a frame from the camera
                frame = self.camera.get_current_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                
                # Update frame dimensions in behavior analyzer
                width, height = self.camera.get_frame_dimensions()
                self.behavior_analyzer.update_frame_dimensions(width, height)
                
                # Check for voice challenge timeout
                if self.use_voice:
                    self.voice_challenger.check_timeout()
                
                # Create display frame
                display_frame = frame.copy()
                
                # Person detection
                person_detected = False
                person_boxes = []
                
                if self.enabled:
                    if self.use_yolo:
                        # Use YOLO for person detection
                        person_detected, person_boxes = self.detector.detect_persons(frame)
                        
                        # Get target information
                        target_info = self.detector.get_target_info()
                        
                        # Analyze behavior if target detected
                        behavior = "unknown"
                        distance = "unknown"
                        
                        if target_info:
                            x1, y1, x2, y2 = target_info["box"]
                            behavior, distance = self.behavior_analyzer.analyze(x1, y1, x2, y2)
                            
                            # Track person if tracking enabled
                            if self.tracking_enabled and self.detector.is_reliable_detection():
                                self.movement.track_in_background(
                                    target_info["center_x"],
                                    target_info["center_y"],
                                    target_info["width"],
                                    target_info["height"],
                                    width,
                                    height
                                )
                        
                        # Save image on first detection
                        if person_detected and self.first_detection:
                            self.first_detection = False
                            
                            # Save detection image
                            self.image_saver.save_detection(
                                frame,
                                person_boxes,
                                self.detector.target_person_box,
                                behavior,
                                distance
                            )
                            
                            # Trigger voice challenge or Claude analysis
                            if self.detector.is_reliable_detection():
                                if self.use_voice and not self.voice_challenger.challenge_passed:
                                    # Start voice challenge
                                    self.voice_challenger.start_challenge(
                                        on_complete_callback=self._handle_challenge_result
                                    )
                                elif self.claude_vision.available:
                                    # Analyze image with Claude
                                    self.claude_vision.analyze_image(
                                        frame,
                                        on_complete_callback=self._handle_claude_result
                                    )
                        
                        # Annotate frame with detection results
                        display_frame = self.detector.annotate_frame(display_frame)
                
                # Get status information for display
                status = self._get_status()
                
                # Update display
                if not self.display.show_frame(display_frame, status):
                    self.running = False
                
                # Small delay to prevent CPU hogging
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            print("\nKeyboard interrupt received, shutting down...")
        finally:
            self.shutdown()
    
    def _handle_challenge_result(self, challenge_passed):
        """Handle voice challenge result"""
        if challenge_passed:
            print("Voice challenge passed")
        else:
            print("Voice challenge failed, triggering alert")
            self.alert_system.trigger_alert(
                failed_challenge=True,
                behavior=self.behavior_analyzer.intruder_behavior,
                distance=self.behavior_analyzer.intruder_distance,
                resume_patrol_callback=self._resume_patrol_if_active
            )
    
    def _handle_claude_result(self, description, warning):
        """Handle Claude analysis result"""
        if warning:
            self.alert_system.trigger_alert(
                warning_message=warning,
                behavior=self.behavior_analyzer.intruder_behavior,
                distance=self.behavior_analyzer.intruder_distance,
                resume_patrol_callback=self._resume_patrol_if_active
            )
    
    def _resume_patrol_if_active(self):
        """Resume patrol if it was active before"""
        if self.patrol_system.patrol_mode:
            self.patrol_system.start()
    
    def _get_status(self):
        """Get current status for display"""
        current_time = time.time()
        if current_time - self.last_status_time < 0.2:  # Limit status updates
            return None
        
        self.last_status_time = current_time
        
        # Build status dictionary
        status = {
            "fps": self.camera.get_fps(),
            "enabled": self.enabled,
            "voice_enabled": self.use_voice,
            "tracking": self.tracking_enabled,
            "patrol": self.patrol_system.patrol_mode
        }
        
        # Add voice challenge status if enabled
        if self.use_voice:
            status.update({
                "challenge_active": self.voice_challenger.challenge_active,
                "challenge_passed": self.voice_challenger.challenge_passed
            })
        
        # Add person detection status
        if self.enabled and self.use_yolo:
            status.update({
                "person_detected": self.detector.person_detected,
                "person_count": self.detector.person_count,
                "behavior": self.behavior_analyzer.intruder_behavior,
                "distance": self.behavior_analyzer.intruder_distance
            })
        
        # Add Claude results if available
        if self.claude_vision.available:
            claude_results = self.claude_vision.get_last_results()
            status.update({
                "description": claude_results["description"],
                "warning": claude_results["warning"]
            })
        
        return status
    
    def enable(self):
        """Enable watchdog mode"""
        self.enabled = True
        self.first_detection = True
        if self.use_yolo:
            self.detector.consecutive_detections = 0
        self.behavior_analyzer.reset()
        print("Watchdog mode enabled")
    
    def disable(self):
        """Disable watchdog mode"""
        self.enabled = False
        self.patrol_system.stop()
        self.tracking_enabled = False
        print("Watchdog mode disabled")
    
    def toggle_alerts(self):
        """Toggle alert system"""
        enabled = self.alert_system.toggle_alerts(not self.alert_system.alerts_enabled)
        return enabled
    
    def toggle_tracking(self, enable=None):
        """Toggle tracking on/off"""
        if enable is not None:
            self.tracking_enabled = enable
        else:
            self.tracking_enabled = not self.tracking_enabled
        
        print(f"Tracking {'enabled' if self.tracking_enabled else 'disabled'}")
        return self.tracking_enabled
    
    def toggle_voice_challenge(self, enable=None):
        """Toggle voice challenge on/off"""
        if not self.voice_challenger.available:
            print("Voice challenge not available")
            self.use_voice = False
            return False
        
        if enable is not None:
            self.use_voice = enable
        else:
            self.use_voice = not self.use_voice
        
        if not self.use_voice:
            self.voice_challenger.reset()
        
        print(f"Voice challenge {'enabled' if self.use_voice else 'disabled'}")
        return self.use_voice
    
    def toggle_patrol(self, enable=None):
        """Toggle patrol mode on/off"""
        if enable is not None:
            if enable:
                return self.patrol_system.start()
            else:
                return self.patrol_system.stop()
        else:
            return self.patrol_system.toggle()
    
    def reset_position(self):
        """Reset robot position (non-blocking)"""
        reset_thread = threading.Thread(
            target=lambda: self.movement.reset_position()
        )
        reset_thread.daemon = True
        reset_thread.start()
    
    def middle_position(self):
        """Move to middle position (non-blocking)"""
        middle_thread = threading.Thread(
            target=lambda: self.movement.middle_position()
        )
        middle_thread.daemon = True
        middle_thread.start()
    
    def jump(self):
        """Make robot jump (non-blocking)"""
        jump_thread = threading.Thread(
            target=lambda: self.robot.send_command("jump")
        )
        jump_thread.daemon = True
        jump_thread.start()
    
    def handshake(self):
        """Make robot do handshake (non-blocking)"""
        handshake_thread = threading.Thread(
            target=lambda: self.robot.send_command("handShake")
        )
        handshake_thread.daemon = True
        handshake_thread.start()
    
    def bark(self):
        """Make robot bark (non-blocking)"""
        bark_thread = threading.Thread(
            target=lambda: self.robot.bark_sequence("excited")
        )
        bark_thread.daemon = True
        bark_thread.start()
    
    def shutdown(self):
        """Shutdown the watchdog system"""
        print("Shutting down watchdog system...")
        
        # Stop all components
        self.running = False
        self.camera.stop()
        self.patrol_system.shutdown()
        self.robot.shutdown()
        self.display.stop()
        
        print("Watchdog system shutdown complete")
