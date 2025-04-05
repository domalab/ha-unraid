"""Utilities for managing logging verbosity."""
import logging
from typing import Dict, Set, Optional, Any, Callable

_LOGGER = logging.getLogger(__name__)

class ImportWarningFilter(logging.Filter):
    """Filter to suppress warnings about blocking import_module calls."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter out specific import_module warnings."""
        if record.levelno == logging.WARNING and "Detected blocking call to import_module" in record.getMessage():
            return False
        return True

class LoggingFilter:
    """Filter to suppress verbose logs from specific loggers."""
    
    def __init__(self) -> None:
        """Initialize the filter."""
        self.filtered_loggers: Dict[str, Dict[str, Any]] = {}
        self.is_active = False
        self.import_filter = ImportWarningFilter()
    
    def setup(self) -> None:
        """Set up logging filters for known verbose loggers."""
        if self.is_active:
            return
            
        # Set asyncssh logging to WARNING level to reduce verbosity
        asyncssh_logger = logging.getLogger('asyncssh')
        original_level = asyncssh_logger.level
        asyncssh_logger.setLevel(logging.WARNING)
        
        # Remember the original level
        self.filtered_loggers['asyncssh'] = {
            'original_level': original_level
        }
        
        # Filter out blocking import warnings
        loop_logger = logging.getLogger('homeassistant.util.loop')
        loop_logger.addFilter(self.import_filter)
        self.filtered_loggers['homeassistant.util.loop'] = {
            'filter': self.import_filter
        }
        
        _LOGGER.debug("Suppressed verbose logging for asyncssh and filtered import warnings")
        self.is_active = True
    
    def restore(self) -> None:
        """Restore original logging levels."""
        if not self.is_active:
            return
            
        for logger_name, settings in self.filtered_loggers.items():
            logger = logging.getLogger(logger_name)
            
            # Restore original level if it was set
            original_level = settings.get('original_level')
            if original_level is not None:
                logger.setLevel(original_level)
                
            # Remove any filters that were added
            filter_obj = settings.get('filter')
            if filter_obj is not None:
                logger.removeFilter(filter_obj)
                
        self.filtered_loggers = {}
        self.is_active = False
        _LOGGER.debug("Restored original logging levels and removed filters")


# Global instance
logging_filter = LoggingFilter()

def setup_logging_filters() -> None:
    """Set up logging filters to suppress verbose output."""
    logging_filter.setup()

def restore_logging_levels() -> None:
    """Restore original logging levels."""
    logging_filter.restore() 