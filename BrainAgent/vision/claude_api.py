#!/usr/bin/env python3
# Claude AI integration for image analysis

import base64
import time
import cv2
import asyncio
import threading
import anthropic

class ClaudeVision:
    """Handles integration with Claude AI for image analysis"""
    
    def __init__(self, api_key=None):
        """Initialize Claude Vision with API key"""
        self.api_key = api_key
        self.available = api_key is not None
        self.client = None
        self.model = "claude-3-7-sonnet-20250219"  # Using latest Claude model
        self.last_analysis_time = 0
        self.analysis_interval = 15  # Seconds between analyses
        
        # Results from last analysis
        self.intruder_description = ""
        self.generated_warning = ""
        
        # Initialize Claude client if API key provided
        if self.available:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                print(f"Claude API initialized with model: {self.model}")
            except Exception as e:
                print(f"Error initializing Claude API: {e}")
                self.available = False
    
    def analyze_image(self, frame, on_complete_callback=None):
        """Analyze an image with Claude (non-blocking)"""
        if not self.available or self.client is None:
            print("Claude API not available")
            if on_complete_callback:
                on_complete_callback(None, None)
            return False
        
        current_time = time.time()
        if current_time - self.last_analysis_time < self.analysis_interval:
            print("Claude analysis skipped due to rate limiting")
            return False
        
        self.last_analysis_time = current_time
        
        # Start analysis in a separate thread
        analysis_thread = threading.Thread(
            target=self._run_analysis,
            args=(frame.copy(), on_complete_callback)
        )
        analysis_thread.daemon = True
        analysis_thread.start()
        
        return True
    
    def _run_analysis(self, frame, on_complete_callback=None):
        """Run Claude analysis in a separate thread"""
        description = None
        warning = None
        
        try:
            # Convert frame to base64 for Claude API
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Step 1: First get intruder description
            description = self._get_description(image_base64)
            self.intruder_description = description
            
            # Step 2: Generate warning message based on description
            if description and "no people" not in description.lower() and len(description) > 10:
                warning = self._generate_warning(description)
                self.generated_warning = warning
        except Exception as e:
            print(f"Claude analysis error: {e}")
        
        # Call the completion callback if provided
        if on_complete_callback:
            on_complete_callback(description, warning)
    
    def _get_description(self, image_base64):
        """Get description of people in the image"""
        try:
            description_message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system="You are a security system that identifies potential intruders. Focus on providing a detailed description of any people you see, especially their clothing, physical appearance, what they're doing, and where they are in the image. This will be used to directly address the intruder.",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Analyze this security camera image of an intruder.
                                
Please describe the person in detail, focusing on:
1. Their clothing (colors, style)
2. Physical appearance (height, build, hair, etc.)
3. What they appear to be doing
4. Where they are in the frame (near the door, in the hallway, etc.)

Keep your response under 50 words and focus only on describing the person."""
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            }
                        ]
                    }
                ]
            )
            
            description = description_message.content[0].text
            print(f"Claude description: {description}")
            return description
        except Exception as e:
            print(f"Error with Claude description API: {e}")
            return None
    
    def _generate_warning(self, description, behavior="unknown", distance="unknown"):
        """Generate a personalized warning message"""
        try:
            # Enhance the prompt with behavior information
            behavior_context = f"The person appears to be {behavior} and is {distance} from the camera."
            
            # Use Claude to generate a personalized warning message
            warning_message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system="You are a security robot confronting an intruder. Generate a direct, authoritative warning message addressing the intruder based on their appearance and behavior. Be intimidating but not threatening.",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""Based on this description of an intruder:

{description}

Additional context: {behavior_context}

Generate a security robot warning message that:
1. Directly references the person's appearance (clothing, location, etc.)
2. Responds appropriately to their behavior (approaching, retreating, stationary)
3. Sounds authoritative and firm
4. Warns them they are being monitored/recorded
5. Tells them to leave immediately or identify themselves

Keep the message under 100 characters and make it sound like a direct verbal warning from a security robot.
Do NOT use any placeholder expressions like [clothing]. Replace such placeholders with actual details from the description."""
                            }
                        ]
                    }
                ]
            )
            
            generated_warning = warning_message.content[0].text
            print(f"Generated warning: {generated_warning}")
            return generated_warning
        except Exception as e:
            print(f"Warning generation error: {e}")
            return None
    
    def get_last_results(self):
        """Get the results from the last analysis"""
        return {
            "description": self.intruder_description,
            "warning": self.generated_warning
        }
