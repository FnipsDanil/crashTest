"""
Secure logging configuration for crash game backend
Removes sensitive data from logs and provides structured logging
"""

import logging
import re
import json
from typing import Any, Dict, Optional
from datetime import datetime

# List of sensitive fields that should be masked in logs
SENSITIVE_FIELDS = {
    'password', 'token', 'secret', 'key', 'api_key', 'auth', 'authorization',
    'bearer', 'telegram_init_data', 'init_data', 'hash', 'payment_payload',
    'webhook_secret', 'bot_token', 'private_key', 'signature', 'hmac',
    'session_id', 'csrf_token', 'user_agent', 'ip_address'
}

# Regex patterns for sensitive data
SENSITIVE_PATTERNS = [
    (re.compile(r'(token|key|secret|password)\s*[:=]\s*["\']?([^"\'\s&]+)', re.IGNORECASE), r'\1=***MASKED***'),
    (re.compile(r'(Authorization|Bearer)\s+([^\s]+)', re.IGNORECASE), r'\1 ***MASKED***'),
    (re.compile(r'\b[A-Za-z0-9]{32,}\b'), '***MASKED_HASH***'),  # Long alphanumeric strings
    (re.compile(r'user_id["\']?\s*[:=]\s*["\']?(\d+)', re.IGNORECASE), r'user_id=***USER_ID***'),
    (re.compile(r'telegram_id["\']?\s*[:=]\s*["\']?(\d+)', re.IGNORECASE), r'telegram_id=***TELEGRAM_ID***'),
]

class SecureFormatter(logging.Formatter):
    """Custom formatter that masks sensitive data"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def format(self, record: logging.LogRecord) -> str:
        # Format the record normally first
        formatted = super().format(record)
        
        # Apply sensitive data masking
        return self.mask_sensitive_data(formatted)
    
    def mask_sensitive_data(self, text: str) -> str:
        """Remove or mask sensitive data from log text"""
        if not text:
            return text
        
        # Apply regex patterns
        for pattern, replacement in SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        
        return text

class StructuredLogFilter(logging.Filter):
    """Filter that adds structured information and masks sensitive data"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Add timestamp in ISO format
        record.timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Add service identifier
        record.service = 'crash-stars-backend'
        
        # Add security level for security-related logs
        if hasattr(record, 'security_event'):
            record.security_level = getattr(record, 'security_level', 'INFO')
        
        # Mask sensitive data in the message
        if hasattr(record, 'msg') and record.msg:
            record.msg = self._mask_sensitive_dict(record.msg)
        
        # Mask sensitive data in args
        if hasattr(record, 'args') and record.args:
            record.args = tuple(
                self._mask_sensitive_dict(arg) if isinstance(arg, (dict, str)) else arg 
                for arg in record.args
            )
        
        return True
    
    def _mask_sensitive_dict(self, data: Any) -> Any:
        """Recursively mask sensitive data in dictionaries and strings"""
        if isinstance(data, dict):
            masked_dict = {}
            for key, value in data.items():
                if isinstance(key, str) and key.lower() in SENSITIVE_FIELDS:
                    masked_dict[key] = '***MASKED***'
                else:
                    masked_dict[key] = self._mask_sensitive_dict(value)
            return masked_dict
        elif isinstance(data, str):
            return self._mask_sensitive_string(data)
        elif isinstance(data, (list, tuple)):
            return type(data)(self._mask_sensitive_dict(item) for item in data)
        else:
            return data
    
    def _mask_sensitive_string(self, text: str) -> str:
        """Mask sensitive patterns in strings"""
        for pattern, replacement in SENSITIVE_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

class SecurityLogger:
    """Security-focused logger for authentication and security events"""
    
    def __init__(self):
        self.logger = logging.getLogger("security")
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            # Console handler with secure formatting
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            
            # Use structured formatter
            formatter = SecureFormatter(
                '%(timestamp)s - %(service)s - %(levelname)s - %(name)s - %(message)s'
            )
            handler.setFormatter(formatter)
            handler.addFilter(StructuredLogFilter())
            
            self.logger.addHandler(handler)
    
    def auth_attempt(self, user_id: Optional[str], success: bool, ip: str, details: str = ""):
        """Log authentication attempt"""
        self.logger.info(
            f"Auth attempt: user={'***USER_ID***'}, success={success}, ip={'***IP***'}, details={details}",
            extra={
                'security_event': 'authentication',
                'security_level': 'INFO' if success else 'WARNING',
                'auth_success': success,
                'user_id_masked': True,
                'ip_masked': True
            }
        )
    
    def rate_limit_exceeded(self, endpoint: str, identifier: str, limit: int):
        """Log rate limit exceeded"""
        self.logger.warning(
            f"Rate limit exceeded: endpoint={endpoint}, identifier={'***MASKED***'}, limit={limit}",
            extra={
                'security_event': 'rate_limit',
                'security_level': 'WARNING',
                'endpoint': endpoint,
                'limit': limit
            }
        )
    
    def suspicious_activity(self, activity_type: str, details: str, severity: str = "WARNING"):
        """Log suspicious activity"""
        self.logger.warning(
            f"Suspicious activity detected: type={activity_type}, details={details}",
            extra={
                'security_event': 'suspicious_activity',
                'security_level': severity,
                'activity_type': activity_type
            }
        )
    
    def admin_action(self, action: str, user_id: Optional[str], details: str = ""):
        """Log admin actions"""
        self.logger.info(
            f"Admin action: action={action}, user={'***USER_ID***'}, details={details}",
            extra={
                'security_event': 'admin_action',
                'security_level': 'INFO',
                'action': action,
                'user_id_masked': True
            }
        )

def setup_secure_logging():
    """Setup secure logging configuration for the entire application"""
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to prevent duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler with secure formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Use secure formatter
    formatter = SecureFormatter(
        '%(timestamp)s - %(service)s - %(levelname)s - %(name)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    console_handler.addFilter(StructuredLogFilter())
    
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    loggers_config = {
        'uvicorn': logging.WARNING,  # Reduce uvicorn verbosity
        'uvicorn.access': logging.WARNING,
        'sqlalchemy.engine': logging.WARNING,
        'asyncio': logging.WARNING,
        'aiohttp': logging.WARNING,
        'httpx': logging.WARNING,  # Disable httpx request logging
    }
    
    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True  # Allow propagation to root logger
    
    # Create security logger instance
    return SecurityLogger()

# Global security logger instance
security_logger = None

def get_security_logger() -> SecurityLogger:
    """Get the global security logger instance"""
    global security_logger
    if security_logger is None:
        security_logger = SecurityLogger()
    return security_logger

def mask_sensitive_data(data: Any) -> Any:
    """Utility function to mask sensitive data in any object"""
    filter_instance = StructuredLogFilter()
    return filter_instance._mask_sensitive_dict(data)

# Example usage in application code:
# 
# from logging_config import get_security_logger, setup_secure_logging
# 
# # During app startup:
# setup_secure_logging()
# 
# # In your handlers:
