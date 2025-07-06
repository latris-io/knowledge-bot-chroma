#!/usr/bin/env python3
"""
Centralized Logging Configuration
Provides file-based logging with rotation for all system components
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

class EnhancedLogger:
    """Enhanced logger with file and console output, rotation, and component separation"""
    
    def __init__(self, component_name: str, log_level: str = "INFO"):
        self.component_name = component_name
        self.log_level = getattr(logging, log_level.upper())
        self.logger = None
        self.setup_logger()
    
    def setup_logger(self):
        """Set up logger with both file and console handlers"""
        self.logger = logging.getLogger(self.component_name)
        self.logger.setLevel(self.log_level)
        
        # Clear any existing handlers to avoid duplicates
        if self.logger.handlers:
            self.logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Component-specific file handler with rotation
        component_log_file = LOGS_DIR / f"{self.component_name}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            component_log_file,
            maxBytes=10*1024*1024,  # 10MB per file
            backupCount=5,  # Keep 5 backup files
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        
        # Master log file (all components combined)
        master_log_file = LOGS_DIR / "system.log"
        master_handler = logging.handlers.RotatingFileHandler(
            master_log_file,
            maxBytes=50*1024*1024,  # 50MB per file
            backupCount=10,  # Keep 10 backup files
            encoding='utf-8'
        )
        master_handler.setLevel(self.log_level)
        master_handler.setFormatter(formatter)
        self.logger.addHandler(master_handler)
        
        # Log startup message
        self.logger.info(f"Logger initialized for {self.component_name}")
    
    def get_logger(self):
        """Get the configured logger instance"""
        return self.logger

def setup_logging(component_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging for a component with both file and console output
    
    Args:
        component_name: Name of the component (e.g., 'test_use_case_3', 'load_balancer')
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    enhanced_logger = EnhancedLogger(component_name, log_level)
    return enhanced_logger.get_logger()

def setup_test_logging(test_name: str) -> logging.Logger:
    """
    Set up logging specifically for test scripts
    Creates timestamped test logs for easy identification
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    component_name = f"test_{test_name}_{timestamp}"
    
    logger = setup_logging(component_name, "DEBUG")  # Tests use DEBUG level
    
    # Create additional timestamped test log
    test_log_file = LOGS_DIR / f"tests/{test_name}_{timestamp}.log"
    test_log_file.parent.mkdir(exist_ok=True)
    
    test_handler = logging.handlers.RotatingFileHandler(
        test_log_file,
        maxBytes=5*1024*1024,  # 5MB per test log
        backupCount=3,
        encoding='utf-8'
    )
    test_handler.setLevel(logging.DEBUG)
    test_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(test_handler)
    
    logger.info(f"Test logging started for {test_name}")
    logger.info(f"Test log file: {test_log_file}")
    
    return logger

def log_system_status(component_name: str, status_data: dict):
    """Log system status information to a dedicated status log"""
    status_logger = setup_logging(f"{component_name}_status", "INFO")
    status_logger.info(f"System Status: {status_data}")

def log_error_details(component_name: str, error: Exception, context: dict = None):
    """Log detailed error information for debugging"""
    error_logger = setup_logging(f"{component_name}_errors", "ERROR")
    error_logger.error(f"ERROR: {str(error)}")
    if context:
        error_logger.error(f"Context: {context}")
    error_logger.error(f"Exception type: {type(error).__name__}")

# Example usage:
if __name__ == "__main__":
    # Test the logging setup
    logger = setup_logging("logging_test")
    logger.info("Testing centralized logging system")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    # Test logging
    test_logger = setup_test_logging("sample_test")
    test_logger.debug("This is a debug message from test")
    test_logger.info("Test completed successfully")
    
    print("\nLogging test completed. Check the logs/ directory for output files:")
    print(f"- logs/logging_test.log")
    print(f"- logs/system.log") 
    print(f"- logs/tests/sample_test_*.log") 