#!/usr/bin/env python3
# Main entry point for RobotWatchdog

import os
import argparse
from dotenv import load_dotenv

from robot.connection import RobotConnection
from detection.yolo_detector import YoloDetector
from security.voice_challenge import VoiceChallenger
from ui.display import WatchdogDisplay
from security.watchdog import RobotWatchdog

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Robot Watchdog with Security Features")
    
    parser.add_argument("--ip", type=str, default=None,
                        help="Robot IP address (default: from ROBOT_IP_ADDRESS env var)")
    parser.add_argument("--enable", action="store_true", 
                        help="Enable watchdog mode on startup")
    parser.add_argument("--track", action="store_true",
                        help="Enable tracking on startup")
    parser.add_argument("--patrol", action="store_true",
                        help="Enable patrol mode on startup")
    parser.add_argument("--no-voice", action="store_true",
                        help="Disable voice challenge feature")
    parser.add_argument("--claude-key", type=str, default=None,
                        help="Claude API key for vision analysis (default: from CLAUDE_API_KEY env var)")
    parser.add_argument("--no-yolo", action="store_true",
                        help="Disable YOLO and use motion detection instead")
    parser.add_argument("--nodisplay", action="store_true",
                        help="Run without display window (headless mode)")
    parser.add_argument("--frame-skip", type=int, default=2,
                        help="Process only every Nth frame (higher values = better performance)")
    parser.add_argument("--high-performance", action="store_true",
                        help="Enable high performance mode (reduces quality but increases speed)")
    
    return parser.parse_args()

def main():
    """Main entry point"""
    # Load environment variables from .env file
    load_dotenv()
    
    # Parse command line arguments
    args = parse_args()
    
    # Get Claude API key from args or environment
    claude_api_key = args.claude_key or os.environ.get("CLAUDE_API_KEY")
    
    # Get robot IP from args, environment, or prompt
    robot_ip = args.ip or os.environ.get("ROBOT_IP_ADDRESS")
    if not robot_ip:
        robot_ip = input("Enter robot IP address: ")
    
    # Initialize the main watchdog system
    watchdog = RobotWatchdog(
        robot_ip=robot_ip,
        claude_api_key=claude_api_key,
        use_yolo=not args.no_yolo,
        use_voice=not args.no_voice,
        use_display=not args.nodisplay,
        frame_skip=args.frame_skip,
        high_performance=args.high_performance
    )
    
    # Enable features based on command line arguments
    if args.enable:
        watchdog.enable()
    
    if args.track:
        watchdog.toggle_tracking(True)
    
    if args.patrol and args.enable:
        watchdog.toggle_patrol(True)
    
    # Run the watchdog
    try:
        watchdog.run()
    except KeyboardInterrupt:
        print("\nStopping watchdog monitor...")
    finally:
        watchdog.shutdown()
        print("Watchdog stopped")

if __name__ == "__main__":
    main()
