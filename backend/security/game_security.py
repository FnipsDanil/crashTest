"""
Game security module for validating critical game operations
Provides HMAC-based authentication and additional validation layers
"""

import hmac
import hashlib
import time
import json
import logging
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class GameAction:
    """Structure for game action validation"""
    user_id: int
    action: str  # 'join', 'cashout'
    timestamp: float
    params: Dict[str, Any]
    signature: str

class GameSecurityValidator:
    """Validates game operations with HMAC signatures"""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
        self.max_age = 30  # 30 seconds max age for requests
        
    def generate_action_signature(self, user_id: int, action: str, params: Dict[str, Any], timestamp: Optional[float] = None) -> Tuple[str, float]:
        """Generate HMAC signature for game action"""
        if timestamp is None:
            timestamp = time.time()
            
        # Create payload for signing
        payload = {
            'user_id': user_id,
            'action': action,
            'timestamp': timestamp,
            'params': params
        }
        
        # Convert to JSON string with sorted keys for consistency
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        # Generate HMAC signature
        signature = hmac.new(
            self.secret_key,
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature, timestamp
    
    def validate_action_signature(self, game_action: GameAction) -> Tuple[bool, str]:
        """Validate HMAC signature for game action"""
        try:
            # Check timestamp age
            current_time = time.time()
            if current_time - game_action.timestamp > self.max_age:
                return False, f"Request too old: {current_time - game_action.timestamp:.1f}s > {self.max_age}s"
            
            # Generate expected signature
            expected_signature, _ = self.generate_action_signature(
                game_action.user_id,
                game_action.action,
                game_action.params,
                game_action.timestamp
            )
            
            # Compare signatures
            if not hmac.compare_digest(expected_signature, game_action.signature):
                return False, "Invalid signature"
            
            return True, "Valid"
            
        except Exception as e:
            logger.error(f"Error validating action signature: {e}")
            return False, f"Validation error: {str(e)}"
    
    def validate_bet_amount(self, user_id: int, bet_amount: Decimal, user_balance: Decimal) -> Tuple[bool, str]:
        """Enhanced bet amount validation"""
        try:
            # Basic range check
            if bet_amount < Decimal('10'):
                return False, "Minimum bet is 10 stars"
            
            if bet_amount > Decimal('50000'):
                return False, "Maximum bet is 50,000 stars"
            
            # Balance check
            if bet_amount > user_balance:
                return False, f"Insufficient balance: {user_balance} < {bet_amount}"
            
            # Additional security checks
            # Check for suspicious betting patterns (e.g., exactly the maximum)
            if bet_amount == Decimal('50000'):
                logger.warning(f"🚨 Maximum bet detected for user {user_id}: {bet_amount}")
            
            # Check for unusual precision (potential manipulation)
            if bet_amount.as_tuple().exponent < -2:  # More than 2 decimal places
                return False, "Bet amount can have at most 2 decimal places"
            
            return True, "Valid bet amount"
            
        except Exception as e:
            logger.error(f"Error validating bet amount: {e}")
            return False, f"Validation error: {str(e)}"
    
    def validate_cashout_timing(self, user_id: int, game_coefficient: Decimal, game_status: str) -> Tuple[bool, str]:
        """Validate cashout timing to prevent timing attacks"""
        try:
            # Basic game state checks
            if game_status != "playing":
                return False, f"Cannot cashout when game is {game_status}"
            
            # Coefficient sanity check
            if game_coefficient < Decimal('1.0'):
                return False, "Invalid game coefficient"
            
            if game_coefficient > Decimal('1000'):  # Reasonable upper bound
                return False, "Game coefficient too high"
            
            # Log cashout attempt for monitoring
            
            return True, "Valid cashout timing"
            
        except Exception as e:
            logger.error(f"Error validating cashout timing: {e}")
            return False, f"Validation error: {str(e)}"

# Global instance (will be initialized in main.py)
game_security: Optional[GameSecurityValidator] = None

def get_game_security() -> GameSecurityValidator:
    """Get global game security validator instance"""
    if game_security is None:
        raise RuntimeError("Game security not initialized")
    return game_security

def init_game_security(secret_key: str) -> GameSecurityValidator:
    """Initialize global game security validator"""
    global game_security
    game_security = GameSecurityValidator(secret_key)
    logger.info("🔒 Game security validator initialized")
    return game_security