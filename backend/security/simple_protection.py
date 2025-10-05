"""
Simple protection against extreme abuse (15+ requests per second)
Only blocks obvious automated attacks, doesn't interfere with normal gameplay
"""

import time
import logging
from typing import Dict
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class SimpleAntiSpam:
    """Simple protection against obvious spam (15+ requests/second)"""
    
    def __init__(self):
        # Track requests per user (only last 10 seconds)
        self.user_requests: Dict[str, deque] = defaultdict(deque)
        self.max_requests_per_10s = 150  # 15 requests/second = 150/10s
        self.window_seconds = 10
        
    def check_request(self, user_id: int, endpoint: str) -> bool:
        """
        Check if request should be allowed
        Returns True if allowed, False if blocked
        """
        current_time = time.time()
        user_key = str(user_id)
        
        # Clean old requests (older than 10 seconds)
        user_queue = self.user_requests[user_key]
        while user_queue and user_queue[0] < current_time - self.window_seconds:
            user_queue.popleft()
        
        # Check if user is making too many requests
        if len(user_queue) >= self.max_requests_per_10s:
            logger.warning(f"🚨 SPAM DETECTED: User {user_id} blocked ({len(user_queue)} requests in {self.window_seconds}s to {endpoint})")
            return False
        
        # Allow request and record it
        user_queue.append(current_time)
        return True
    
    def cleanup_old_data(self):
        """Remove old user data to prevent memory leaks"""
        current_time = time.time()
        users_to_remove = []
        
        for user_id, requests in self.user_requests.items():
            # Remove old requests
            while requests and requests[0] < current_time - self.window_seconds:
                requests.popleft()
            
            # If no recent requests, mark user for removal
            if not requests:
                users_to_remove.append(user_id)
        
        # Remove inactive users
        for user_id in users_to_remove:
            del self.user_requests[user_id]

# Global instance
anti_spam: SimpleAntiSpam = SimpleAntiSpam()

def check_anti_spam(user_id: int, endpoint: str = "unknown") -> bool:
    """Check if request should be allowed (simple spam protection)"""
    return anti_spam.check_request(user_id, endpoint)