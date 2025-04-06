"""Logging filter for Unraid integration to reduce log spam."""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict

_LOGGER = logging.getLogger(__name__)

class LoggingFilter(logging.Filter):
    """Logging filter to reduce repeated messages and control verbosity."""
    
    def __init__(
        self, 
        name: str = "",
        max_duplicates: int = 5,
        rate_limit_period: int = 300,
        suppress_common_messages: bool = True
    ) -> None:
        """Initialize the logging filter."""
        super().__init__(name)
        self.max_duplicates = max_duplicates
        self.rate_limit_period = rate_limit_period
        self.suppress_common_messages = suppress_common_messages
        
        # Track recent messages
        self._messages: Dict[str, Tuple[int, datetime]] = {}
        self._suppressed_count: Dict[str, int] = defaultdict(int)
        self._last_cleanup = datetime.now()
        
        # Known patterns to suppress
        self._suppress_patterns = [
            # Connection status messages (mostly debug)
            r"Connected to .* \(conn_id=.*\)",
            r"Reusing existing connection \(conn_id=.*\)",
            r"Created new connection \(conn_id=.*\)",
            
            # Common command success messages
            r"Command executed successfully: echo",
            
            # Command retry messages that are duplicative
            r"Retrying command .* after .* seconds",
            
            # Cache operation messages that are frequent
            r"Cache item .* expired",
        ]
        
        # Success/debug messages we should convert to DEBUG level
        self._debug_patterns = [
            r"Got system stats.*",
            r"Data update complete.*",
            r"Fetching system stats.*",
            r"Adding CPU info.*"
        ]
        
        # Compile patterns
        self._suppress_re = [re.compile(p) for p in self._suppress_patterns]
        self._debug_re = [re.compile(p) for p in self._debug_patterns]
        
        _LOGGER.debug(
            "LoggingFilter initialized with max_duplicates=%d, rate_limit_period=%d",
            max_duplicates,
            rate_limit_period
        )
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records to reduce spam."""
        # Check if we need to clean up message history
        self._check_cleanup()
        
        # First handle level conversion for success messages
        if record.levelno == logging.INFO:
            message = self._get_message(record)
            if any(pattern.search(message) for pattern in self._debug_re):
                record.levelno = logging.DEBUG
                record.levelname = "DEBUG"
        
        # Don't filter higher severity messages
        if record.levelno >= logging.WARNING:
            return True
            
        # Check message suppression for DEBUG level only
        if record.levelno == logging.DEBUG and self.suppress_common_messages:
            message = self._get_message(record)
            if any(pattern.search(message) for pattern in self._suppress_re):
                return False
        
        # Handle duplicate messages (all levels)
        message_key = f"{record.name}:{record.levelno}:{self._get_message(record)}"
        
        # Check if this is a duplicate
        now = datetime.now()
        if message_key in self._messages:
            count, first_time = self._messages[message_key]
            
            # Check rate limiting
            if (now - first_time).total_seconds() < self.rate_limit_period:
                # Update count
                count += 1
                self._messages[message_key] = (count, first_time)
                
                # If over threshold, suppress but track count
                if count > self.max_duplicates:
                    self._suppressed_count[message_key] += 1
                    return False
            else:
                # Reset counter if rate limit period expired
                self._messages[message_key] = (1, now)
                
                # If we suppressed any, emit a summary now
                if self._suppressed_count.get(message_key, 0) > 0:
                    suppressed = self._suppressed_count[message_key]
                    self._suppressed_count[message_key] = 0
                    
                    # Modify the message to include suppression count
                    record.msg = f"{record.msg} (suppressed {suppressed} similar messages in last {self.rate_limit_period}s)"
                    return True
        else:
            # First time seeing this message
            self._messages[message_key] = (1, now)
        
        return True
    
    def _get_message(self, record: logging.LogRecord) -> str:
        """Get the formatted message from a record."""
        try:
            return record.getMessage()
        except Exception:
            return str(record.msg)
    
    def _check_cleanup(self) -> None:
        """Clean up old message history periodically."""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() < 60:
            return
            
        # Clean up old message history
        cutoff = now - timedelta(seconds=self.rate_limit_period)
        self._messages = {
            k: (c, t) for k, (c, t) in self._messages.items()
            if t >= cutoff
        }
        
        # Also clean up suppression counts
        self._suppressed_count = defaultdict(
            int, 
            {k: v for k, v in self._suppressed_count.items() if k in self._messages}
        )
        
        self._last_cleanup = now


class LogManager:
    """Manages logging configuration and filters for the Unraid integration."""
    
    def __init__(self) -> None:
        """Initialize the log manager."""
        self._filters: Dict[str, LoggingFilter] = {}
        self._is_configured = False
    
    def configure(self) -> None:
        """Configure logging for the integration."""
        if self._is_configured:
            return
            
        self._is_configured = True
        
        # Create filters for different loggers
        root_filter = LoggingFilter(
            name="unraid_root",
            max_duplicates=3,
            rate_limit_period=120
        )
        
        connection_filter = LoggingFilter(
            name="unraid_connection",
            max_duplicates=5,
            rate_limit_period=300,
            suppress_common_messages=True
        )
        
        update_filter = LoggingFilter(
            name="unraid_update",
            max_duplicates=3,
            rate_limit_period=600
        )
        
        # Apply filters to relevant loggers
        unraid_logger = logging.getLogger("custom_components.unraid")
        unraid_logger.addFilter(root_filter)
        self._filters["root"] = root_filter
        
        conn_logger = logging.getLogger("custom_components.unraid.api.connection_manager")
        conn_logger.addFilter(connection_filter)
        self._filters["connection"] = connection_filter
        
        coord_logger = logging.getLogger("custom_components.unraid.coordinator")
        coord_logger.addFilter(update_filter)
        self._filters["coordinator"] = update_filter
        
        _LOGGER.debug("LogManager configured filters for Unraid integration")
    
    def reset(self) -> None:
        """Reset all filters."""
        for logger_name, filter_obj in self._filters.items():
            if logger_name == "root":
                logging.getLogger("custom_components.unraid").removeFilter(filter_obj)
            elif logger_name == "connection":
                logging.getLogger("custom_components.unraid.api.connection_manager").removeFilter(filter_obj)
            elif logger_name == "coordinator":
                logging.getLogger("custom_components.unraid.coordinator").removeFilter(filter_obj)
        
        self._filters = {}
        self._is_configured = False 