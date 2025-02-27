#!/usr/bin/env python3
# Voice challenge system with improved error handling

import time
import random
import threading
import speech_recognition as sr
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VoiceChallenger")

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
            logger.info("Initializing speech recognition...")
            self.recognizer = sr.Recognizer()
            
            # Test if microphone is available
            with sr.Microphone() as source:
                logger.info("Testing microphone...")
                # Just a quick test to see if microphone works
                self.recognizer.adjust_for_ambient_noise(source, duration=0.1)
            
            self.available = True
            logger.info("Speech recognition initialized successfully!")
        except Exception as e:
            logger.error(f"Speech recognition initialization error: {e}")
            logger.warning("Voice challenge will not be available")
    
    def listen(self, timeout=10):
        """Listen for voice input with timeout"""
        if not self.available or not self.recognizer:
            logger.error("Speech recognition not available")
            return ""
            
        logger.info(f"Listening for response (timeout: {timeout}s)...")
        
        try:
            # Use with context for microphone to ensure proper resource cleanup
            with sr.Microphone() as source:
                try:
                    # Adjust for ambient noise
                    logger.info("Adjusting for ambient noise...")
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    # Listen for audio with timeout
                    logger.info("Listening...")
                    audio = self.recognizer.listen(source, timeout=timeout)
                    
                    # Convert speech to text
                    logger.info("Processing speech...")
                    response = self.recognizer.recognize_google(audio)
                    logger.info(f"Heard: '{response}'")
                    return response.lower()
                    
                except sr.WaitTimeoutError:
                    logger.warning("No audio detected within timeout")
                    return ""
                except sr.UnknownValueError:
                    logger.warning("Could not understand audio")
                    return ""
                except sr.RequestError as e:
                    logger.error(f"Could not request results from speech recognition service: {e}")
                    return ""
                except Exception as e:
                    logger.error(f"Audio processing error: {e}")
                    return ""
        except Exception as e:
            logger.error(f"Microphone error: {e}")
            self.available = False
            return ""
    
    def start_challenge(self, on_complete_callback=None):
        """Start a voice challenge in a separate thread"""
        if not self.available:
            logger.warning("Voice challenge not available")
            if on_complete_callback:
                on_complete_callback(False)
            return False
        
        if self.challenge_active:
            logger.warning("Challenge already in progress")
            return False
        
        logger.info("Starting voice challenge...")
        
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
        
        try:
            logger.info("Running voice challenge...")
            
            # Use robot's head movements to look at the person
            # Use simple non-blocking queue commands instead of asyncio
            self.robot.queue_command("lookLeft")
            time.sleep(0.3)
            self.robot.queue_command("LRstop")
            time.sleep(0.2)
            self.robot.queue_command("lookRight")
            time.sleep(0.3)
            self.robot.queue_command("LRstop")
            
            # Choose a random security question
            self.current_question = random.choice(self.security_questions)
            
            # Ask the security question (short version)
            question_text = f"{self.current_question['question']}"
            logger.info(f"Asking question: '{question_text}'")
            
            # Important: Make sure the speak command works properly
            self.robot.speak(question_text)
            
            # Log the expected answer for debugging
            logger.info(f"Expected answer: '{self.current_question['answer']}'")
            
            # Wait briefly to ensure speech completes
            time.sleep(2)
            
            # Listen for answer with timeout
            response = self.listen(timeout=self.voice_recognition_timeout)
            
            # Check if answer is correct (with some flexibility)
            if response and (response == self.current_question['answer'].lower() or 
                            self.current_question['answer'].lower() in response):
                logger.info("Answer is correct!")
                self.robot.speak("Access granted.")
                
                # Visual feedback with lights
                self.robot.queue_command("light green")
                self.challenge_passed = True
                challenge_result = True
                time.sleep(1)
                self.robot.queue_command("light off")
            else:
                # If microphone failed, just fail the challenge
                if not self.available:
                    logger.warning("Microphone failed, failing challenge")
                    challenge_result = False
                else:
                    # Give them one more chance with a shorter prompt
                    logger.info("First answer incorrect or not received, giving second chance")
                    time.sleep(1)
                    
                    # Second prompt
                    second_prompt = f"Repeat: {self.current_question['question']}"
                    logger.info(f"Asking again: '{second_prompt}'")
                    self.robot.speak(second_prompt)
                    
                    # Listen for second attempt
                    response = self.listen(timeout=self.voice_recognition_timeout)
                    
                    if response and (response == self.current_question['answer'].lower() or 
                                   self.current_question['answer'].lower() in response):
                        logger.info("Second answer is correct!")
                        self.robot.speak("Access granted.")
                        self.challenge_passed = True
                        challenge_result = True
                        
                        # Visual feedback with lights
                        self.robot.queue_command("light green")
                        time.sleep(1)
                        self.robot.queue_command("light off")
                    else:
                        # Failed challenge
                        logger.info("Challenge failed after two attempts")
                        self.robot.speak("Intruder detected.")
                        challenge_result = False
        except Exception as e:
            logger.error(f"Voice challenge error: {e}")
            challenge_result = False
        finally:
            self.challenge_active = False
            
            # Call the completion callback if provided
            logger.info(f"Challenge completed with result: {challenge_result}")
            if on_complete_callback:
                on_complete_callback(challenge_result)
    
    def check_timeout(self):
        """Check if the voice challenge has timed out"""
        if self.challenge_active:
            elapsed_time = time.time() - self.challenge_start_time
            if elapsed_time > self.challenge_timeout:
                logger.warning("Challenge response timeout")
                self.challenge_active = False
                return True
        return False
    
    def reset(self):
        """Reset the challenge state"""
        logger.info("Resetting voice challenge state")
        self.challenge_active = False
        self.challenge_passed = False
        self.current_question = None