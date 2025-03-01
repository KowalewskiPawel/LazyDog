# CLAUDE.md - BrainAgent Repository Guidelines

## Commands
- Run the test script: `python test.py`
- Activate the robot control: `python vision_controller.py`
- Check Python environment: `python -c "import torch; print(torch.__version__)"`

## Code Style Guidelines
- **Imports**: Group imports by standard library, third-party, and local modules
- **Environment Variables**: Use dotenv for configuration with .env files
- **Error Handling**: Use try/except with specific error types and helpful messages
- **Docstrings**: Use docstrings for all classes and functions explaining purpose
- **Naming**: Use snake_case for variables/functions, CamelCase for classes
- **Asyncio**: Use async/await consistently for I/O-bound operations
- **Comments**: Add comments for complex logic or non-obvious behavior
- **Design Pattern**: Use class-based architecture with clear responsibilities
- **AI Integration**: Use the Anthropic Claude API for vision and text processing