#!/usr/bin/env python3
# Display and UI module for watchdog

import cv2
import time
import threading

class WatchdogDisplay:
    """Handles UI display and keyboard input"""
    
    def __init__(self, watchdog_controller, use_display=True):
        """Initialize display with watchdog controller"""
        self.watchdog = watchdog_controller
        self.use_display = use_display
        self.running = True
        
        # Create window if display is enabled
        if self.use_display:
            cv2.namedWindow("Watchdog Monitor", cv2.WINDOW_NORMAL)
            cv2.resizeWindow("Watchdog Monitor", 800, 600)
    
    def process_keyboard(self, key):
        """Process keyboard input"""
        # Handle key presses
        if key == ord('q'):
            self.running = False
            return False
        elif key == ord('e'):
            self.watchdog.enable()
        elif key == ord('d'):
            self.watchdog.disable()
        elif key == ord('a'):
            self.watchdog.toggle_alerts()
        elif key == ord('t'):
            self.watchdog.toggle_tracking()
        elif key == ord('v'):
            self.watchdog.toggle_voice_challenge()
        elif key == ord('p'):
            self.watchdog.toggle_patrol()
        elif key == ord('r'):
            self.watchdog.reset_position()
        elif key == ord('m'):
            self.watchdog.middle_position()
        elif key == ord('j'):
            self.watchdog.jump()
        elif key == ord('h'):
            self.watchdog.handshake()
        elif key == ord('b'):
            self.watchdog.bark()
        
        return True
    
    def show_frame(self, frame, watchdog_status=None):
        """Display a frame with status information"""
        if not self.use_display or frame is None:
            return
        
        # Create a copy of the frame for display
        display_frame = frame.copy()
        
        # Add status information if provided
        if watchdog_status:
            # Basic status information
            status_text = f"FPS: {watchdog_status.get('fps', 0)} | Watchdog: {'ON' if watchdog_status.get('enabled', False) else 'OFF'}"
            
            if watchdog_status.get('enabled', False):
                status_text += f" | Voice: {'ON' if watchdog_status.get('voice_enabled', False) else 'OFF'}"
                status_text += f" | Tracking: {'ON' if watchdog_status.get('tracking', False) else 'OFF'}"
                status_text += f" | Patrol: {'ON' if watchdog_status.get('patrol', False) else 'OFF'}"
            
            cv2.putText(display_frame, status_text, (10, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # Add challenge status if voice challenge is enabled
            if watchdog_status.get('voice_enabled', False):
                if watchdog_status.get('challenge_active', False):
                    challenge_text = "Challenge: ACTIVE"
                    color = (0, 255, 255)  # Yellow
                elif watchdog_status.get('challenge_passed', False):
                    challenge_text = "Challenge: PASSED"
                    color = (0, 255, 0)  # Green
                else:
                    challenge_text = "Challenge: WAITING"
                    color = (255, 255, 255)  # White
                
                cv2.putText(display_frame, challenge_text, (10, 60), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            
            # Person information
            if watchdog_status.get('person_detected', False):
                person_text = f"Person: Count={watchdog_status.get('person_count', 0)}"
                
                # Add behavior and distance if available
                behavior = watchdog_status.get('behavior', None)
                distance = watchdog_status.get('distance', None)
                
                if behavior and distance:
                    person_text += f", Behavior={behavior}, Dist={distance}"
                
                cv2.putText(display_frame, person_text, (10, 90), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            # Intruder description
            description = watchdog_status.get('description', '')
            if description:
                if len(description) > 60:
                    desc_text = description[:57] + "..."
                else:
                    desc_text = description
                
                cv2.putText(display_frame, f"Description: {desc_text}", (10, 120), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
            
            # Warning message
            warning = watchdog_status.get('warning', '')
            if warning:
                if len(warning) > 60:
                    warning_text = warning[:57] + "..."
                else:
                    warning_text = warning
                
                cv2.putText(display_frame, f"Warning: {warning_text}", (10, 150), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # Add help text at the bottom
        help_text = "Controls: [e]nable/[d]isable, [a]lerts, [t]rack, [v]oice, [p]atrol, [r]eset, [m]iddle, [j]ump, [h]andshake, [q]uit"
        cv2.putText(display_frame, help_text, (10, display_frame.shape[0] - 20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Display the frame
        cv2.imshow("Watchdog Monitor", display_frame)
        
        # Process keyboard input (with 1ms wait)
        key = cv2.waitKey(1) & 0xFF
        return self.process_keyboard(key)
    
    def stop(self):
        """Stop the display"""
        self.running = False
        if self.use_display:
            cv2.destroyAllWindows()
