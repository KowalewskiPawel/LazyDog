#!/usr/bin/env python3
# Voice challenge system

import time
import random
import threading
import asyncio
import speech_recognition as sr
import concurrent.futures

class VoiceChallenger:
    """Handles voice-based security challenges"""
    
    def __init__(self, robot_connection):
        """Initialize voice challenger with robot connection"""
        self.robot = robot_connection
        self.challenge_active = False
        self.challenge_passed = False
        self.challenge_timeout = 60  # 60 seconds to respond
        self.challenge_start_time = 0
        self.current_question = None
        self.voice_recognition_timeout = 10  # seconds to wait for response
        
        # Initialize speech recognition if possible
        self.available = False
        self.recognizer = None
        self.voice_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        
        # Security questions and correct answers
        self.security_questions = [
            {"question": "What is the password?", "answer": "bluesky"},
            {"question": "Who are you?", "answer": "authorized"},
            {"question": "What is today's code word?", "answer": "sunshine"},
            {"question": "State your security clearance level.", "answer": "alpha"},
            {"question": "What department do you work for?", "answer": "engineering"}
        ]
        
        # Try to initialize speech recognition
        try:
            self.recognizer = sr.Recognizer()
            self.available = True
            print("Voice challenge system initialized")
        except Exception as e:
            print(f"Speech recognition initialization error: {e}")
            print("Voice challenge will not be available")
    
    def listen(self, timeout=10):
        """Listen for voice input with timeout"""
        if not self.available or not self.recognizer:
            print("Speech recognition not available")
            return ""
            
        try:
            # Use with context for microphone to ensure proper resource cleanup
            with sr.Microphone() as source:
                print("Listening for response...")
                try:
                    # Adjust for ambient noise
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    # Listen for audio with timeout
                    audio = self.recognizer.listen(source, timeout=timeout)
                    # Convert speech to text
                    response = self.recognizer.recognize_google(audio)
                    print(f"Heard: {response}")
                    return response.lower()
                except sr.WaitTimeoutError:
                    print("No audio detected within timeout")
                    return ""
                except sr.UnknownValueError:
                    print("Could not understand audio")
                    return ""
                except sr.RequestError as e:
                    print(f"Could not request results from speech recognition service: {e}")
                    return ""
                except Exception as e:
                    print(f"Audio processing error: {e}")
                    return ""
        except Exception as e:
            print(f"Microphone error: {e}")
            self.available = False
            return ""
    
    def start_challenge(self, on_complete_callback=None):
        """Start a voice challenge in a separate thread"""
        if not self.available:
            print("Voice challenge not available")
            if on_complete_callback:
                on_complete_callback(False)
            return False
        
        if self.challenge_active:
            print("Challenge already in progress")
            return False
        
        # Start challenge in a separate thread
        challenge_thread = threading.Thread(
            target=self._run_challenge,
            args=(on_complete_callback,)
        )
        challenge_thread.daemon = True
        challenge_thread.start()
        
        return True
    
    def _run_challenge(self, on_complete_callback=None):
        """Run the challenge process in a separate thread"""
        self.challenge_active = True
        self.challenge_start_time = time.time()
        challenge_result = False
        
        # Use threading event to create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Use robot's head movements to look at the person
            loop.run_until_complete(self.robot.send_command("lookLeft"))
            time.sleep(0.3)
            loop.run_until_complete(self.robot.send_command("LRstop"))
            time.sleep(0.2)
            loop.run_until_complete(self.robot.send_command("lookRight"))
            time.sleep(0.3)
            loop.run_until_complete(self.robot.send_command("LRstop"))
            
            # Choose a random security question
            self.current_question = random.choice(self.security_questions)
            
            # Ask the security question (short version)
            self.robot.speak(f"{self.current_question['question']}")
            
            # Wait briefly to ensure speech completes
            time.sleep(2)
            
            # Listen for answer with timeout
            response = self.listen(timeout=self.voice_recognition_timeout)
            
            # Check if answer is correct (with some flexibility)
            if response and (response == self.current_question['answer'].lower() or 
                            self.current_question['answer'].lower() in response):
                self.robot.speak("Access granted.")
                self.challenge_passed = True
                challenge_result = True
                loop.run_until_complete(self.robot.send_command("light green"))  # Green light for success
                time.sleep(1)
                loop.run_until_complete(self.robot.send_command("light off"))
            else:
                # If microphone failed, just fail the challenge
                if not self.available:
                    challenge_result = False
                else:
                    # Give them one more chance with a shorter prompt
                    time.sleep(1)
                    self.robot.speak(f"Repeat: {self.current_question['question']}")
                    
                    response = self.listen(timeout=self.voice_recognition_timeout)
                    
                    if response and (response == self.current_question['answer'].lower() or 
                                   self.current_question['answer'].lower() in response):
                        self.robot.speak("Access granted.")
                        self.challenge_passed = True
                        challenge_result = True
                        loop.run_until_complete(self.robot.send_command("light green"))
                        time.sleep(1)
                        loop.run_until_complete(self.robot.send_command("light off"))
                    else:
                        # Failed challenge
                        self.robot.speak("Intruder detected.")
                        challenge_result = False
        except Exception as e:
            print(f"Voice challenge error: {e}")
            challenge_result = False
        finally:
            self.challenge_active = False
            loop.close()
            
            # Call the completion callback if provided
            if on_complete_callback:
                on_complete_callback(challenge_result)
    
    def check_timeout(self):
        """Check if the voice challenge has timed out"""
        if self.challenge_active:
            elapsed_time = time.time() - self.challenge_start_time
            if elapsed_time > self.challenge_timeout:
                print("Challenge response timeout")
                self.challenge_active = False
                return True
        return False
    
    def reset(self):
        """Reset the challenge state"""
        self.challenge_active = False
        self.challenge_passed = False
        self.current_question = None
