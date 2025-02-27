#!/usr/bin/env python3
# Configuration settings for the watchdog system

# Robot connection settings
ROBOT_DEFAULT_PORT = 8888
VIDEO_DEFAULT_PORT = 5000

# YOLO detection settings
YOLO_MODEL_PATH = "yolov8n.pt"  # Use smallest model for speed
YOLO_CONFIDENCE_THRESHOLD = 0.5  # Minimum confidence for detection
YOLO_DETECTION_THRESHOLD = 3  # Consecutive detections required

# Voice challenge settings
VOICE_CHALLENGE_ENABLED = False  # Disabled by default due to mic issues
VOICE_TIMEOUT = 10  # Seconds to wait for voice response
CHALLENGE_TIMEOUT = 60  # Seconds before challenge times out

# Security questions - customize these for your environment
SECURITY_QUESTIONS = [
    {"question": "What is the password?", "answer": "bluesky"},
    {"question": "Who are you?", "answer": "authorized"},
    {"question": "What is today's code word?", "answer": "sunshine"},
    {"question": "State your security clearance level.", "answer": "alpha"},
    {"question": "What department do you work for?", "answer": "engineering"}
]

# Alert system settings
DETECTION_COOLDOWN = 30  # Seconds between alerts

# Warning messages - customize these for your environment
GENERIC_WARNINGS = [
    "Intruder detected! The police has been notified.",
    "Warning! This area is under surveillance.",
    "Security alert! The homeowner has been notified.",
    "Unauthorized access detected! Security system activated.",
    "This is a security robot. Please identify yourself."
]

ANGRY_MESSAGES = [
    "I've already called the police! Get out now!",
    "This is your final warning! Leave immediately!",
    "Security measures activated. You need to leave right now!",
    "Stop what you're doing and exit the premises immediately!",
    "You are trespassing! Get out or there will be consequences!"
]

# Patrol settings
PATROL_INTERVAL = 60  # Seconds between patrol movements
PATROL_RANDOM = True  # Use random movement pattern

# Claude AI settings
CLAUDE_MODEL = "claude-3-7-sonnet-20250219"
CLAUDE_ANALYSIS_INTERVAL = 15  # Seconds between Claude analyses

# Image saving settings
IMAGE_SAVE_DIR = "intruder_images"
IMAGE_QUALITY = 95  # JPEG quality (0-100)

# Performance settings
DEFAULT_FRAME_SKIP = 2  # Process every Nth frame
HIGH_PERFORMANCE_FRAME_SKIP = 4  # Higher for better performance

# UI settings
DEFAULT_WINDOW_SIZE = (800, 600)
