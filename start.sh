#!/bin/bash
# This script activates the Python virtual environment,
# runs an update script, and then starts the main bot application.

# Activate Python virtual environment
source .venv/bin/activate

# Run update script
python3 update.py

# Start the main bot application
python3 -m bot