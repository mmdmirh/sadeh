"""
Conversation ID hashing utilities for secure URL parameters.

This module provides functions to encode/decode conversation IDs using
URL-safe hashing to prevent enumeration attacks and improve privacy.
"""

import hashlib
import hmac
import uuid
from typing import Optional
from flask import current_app


def _get_secret_key() -> str:
    """Get the secret key from Flask config."""
    return current_app.config.get('SECRET_KEY', 'fallback-secret-key')


def encode_conversation_id(conversation_id: int, user_id: int) -> str:
    """
    Encode a conversation ID into a UUID-style hash.
    
    Args:
        conversation_id: The database conversation ID
        user_id: The user ID for additional security
        
    Returns:
        UUID-style hash string (e.g., 6883fc97-3b74-832c-bb0b-e4f11a840387)
    """
    # Create a message that includes both conversation_id and user_id
    message = f"{conversation_id}:{user_id}".encode('utf-8')
    
    # Use HMAC with SHA256 for secure hashing
    secret_key = _get_secret_key().encode('utf-8')
    signature = hmac.new(secret_key, message, hashlib.sha256).digest()
    
    # Take first 16 bytes of the signature to create a UUID-style hash
    hash_bytes = signature[:16]
    
    # Format as UUID-style string (8-4-4-4-12 format)
    uuid_str = f"{hash_bytes[0:4].hex()}-{hash_bytes[4:6].hex()}-{hash_bytes[6:8].hex()}-{hash_bytes[8:10].hex()}-{hash_bytes[10:16].hex()}"
    
    return uuid_str


def decode_conversation_id(encoded_hash: str, user_id: int) -> Optional[int]:
    """
    Decode a UUID-style hashed conversation ID back to the original ID.
    
    Args:
        encoded_hash: The UUID-style hash (e.g., 6883fc97-3b74-832c-bb0b-e4f11a840387)
        user_id: The user ID for verification
        
    Returns:
        The original conversation ID if valid, None if invalid
    """
    from flask import current_app
    
    try:
        current_app.logger.info(f"HASH_DEBUG: Validating hash '{encoded_hash}' for user {user_id}")
        
        # Validate UUID format
        if len(encoded_hash) != 36 or encoded_hash.count('-') != 4:
            current_app.logger.warning(f"HASH_DEBUG: Invalid UUID format for hash '{encoded_hash}'")
            return None
        
        # Remove dashes and convert to bytes
        hex_string = encoded_hash.replace('-', '')
        if len(hex_string) != 32:
            current_app.logger.warning(f"HASH_DEBUG: Invalid hex string length: {len(hex_string)}")
            return None
            
        provided_hash_bytes = bytes.fromhex(hex_string)
        current_app.logger.info(f"HASH_DEBUG: Provided hash bytes: {provided_hash_bytes.hex()}")
        
        # We need to brute force check conversation IDs for this user
        # This is secure because we're only checking conversations owned by the user
        from backend.db.models import Conversation
        
        # Get all conversations for this user
        user_conversations = Conversation.query.filter_by(user_id=user_id).all()
        current_app.logger.info(f"HASH_DEBUG: Found {len(user_conversations)} conversations for user {user_id}")
        
        # Check each conversation to see if it generates this hash
        for conversation in user_conversations:
            # Generate the expected hash for this conversation
            message = f"{conversation.id}:{user_id}".encode('utf-8')
            secret_key = _get_secret_key().encode('utf-8')
            expected_signature = hmac.new(secret_key, message, hashlib.sha256).digest()
            expected_hash_bytes = expected_signature[:16]
            
            current_app.logger.info(f"HASH_DEBUG: Conversation {conversation.id} - Expected hash: {expected_hash_bytes.hex()}")
            
            # Use constant-time comparison to prevent timing attacks
            if hmac.compare_digest(provided_hash_bytes, expected_hash_bytes):
                current_app.logger.info(f"HASH_DEBUG: Hash match found for conversation {conversation.id}")
                return conversation.id
        
        # No matching conversation found
        current_app.logger.warning(f"HASH_DEBUG: No matching conversation found for hash '{encoded_hash}'")
        return None
        
    except (ValueError, TypeError, UnicodeDecodeError) as e:
        current_app.logger.error(f"HASH_DEBUG: Exception during hash validation: {e}")
        return None
    except Exception as e:
        current_app.logger.error(f"HASH_DEBUG: Unexpected exception: {e}", exc_info=True)
        return None


def get_conversation_hash_param(conversation_id: int, user_id: int) -> str:
    """
    Get the URL parameter string for a conversation hash.
    
    Args:
        conversation_id: The database conversation ID
        user_id: The user ID
        
    Returns:
        URL parameter string like "conversation_hash=6883fc97-3b74-832c-bb0b-e4f11a840387"
    """
    hash_value = encode_conversation_id(conversation_id, user_id)
    return f"conversation_hash={hash_value}"


def validate_conversation_access(encoded_hash: str, user_id: int) -> Optional[int]:
    """
    Validate that a user has access to a conversation and return the ID.
    
    This is a convenience function that combines decoding with database validation.
    
    Args:
        encoded_hash: The URL-safe base64 encoded hash
        user_id: The user ID for verification
        
    Returns:
        The conversation ID if valid and accessible, None otherwise
    """
    conversation_id = decode_conversation_id(encoded_hash, user_id)
    
    if conversation_id is None:
        return None
    
    # Import here to avoid circular imports
    from backend.db.models import Conversation
    
    # Verify the conversation exists and belongs to the user
    conversation = Conversation.query.filter_by(
        id=conversation_id, 
        user_id=user_id
    ).first()
    
    return conversation_id if conversation else None
