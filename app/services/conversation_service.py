"""Conversation management service."""

import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.conversation import Conversation, ConversationMessage
from app.core.redis_client import RedisClient

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversation context and history."""

    def __init__(self, db: Session, redis_client: RedisClient):
        """Initialize conversation service.

        Args:
            db: Database session
            redis_client: Redis client for caching
        """
        self.db = db
        self.redis = redis_client

    def get_or_create_conversation(
        self,
        tenant_id: int,
        user_id: str,
        channel_id: str,
        thread_ts: str
    ) -> Conversation:
        """Get existing conversation or create new one.

        Args:
            tenant_id: Tenant ID
            user_id: Slack user ID
            channel_id: Slack channel ID
            thread_ts: Slack thread timestamp

        Returns:
            Conversation instance
        """
        # Try to find existing conversation by thread_ts
        conversation = self.db.query(Conversation).filter_by(
            thread_ts=thread_ts
        ).first()

        if conversation:
            logger.debug(f"Found existing conversation: {conversation.id}")
            return conversation

        # Create new conversation
        conversation = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)

        logger.info(f"Created new conversation: {conversation.id}")
        return conversation

    def get_conversation_history(
        self,
        conversation_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """Get conversation message history.

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of messages to return

        Returns:
            List of message dicts with role and content
        """
        messages = self.db.query(ConversationMessage).filter_by(
            conversation_id=conversation_id
        ).order_by(
            ConversationMessage.created_at.desc()
        ).limit(limit).all()

        # Convert to chat format (reverse to chronological order)
        history = []
        for msg in reversed(messages):
            # Add user message
            history.append({
                "role": "user",
                "content": msg.message_text
            })
            # Add bot response if exists
            if msg.bot_response:
                history.append({
                    "role": "assistant",
                    "content": msg.bot_response
                })

        return history

    def save_message(
        self,
        conversation_id: int,
        user_id: str,
        message_text: str,
        intent_type: Optional[str] = None,
        entities: Optional[Dict] = None,
        bot_response: Optional[str] = None
    ) -> ConversationMessage:
        """Save a message to conversation history.

        Args:
            conversation_id: Conversation ID
            user_id: User ID who sent the message (or "bot")
            message_text: The message text
            intent_type: Parsed intent type (optional)
            entities: Extracted entities (optional)
            bot_response: Bot's response (optional)

        Returns:
            Created ConversationMessage instance
        """
        message = ConversationMessage(
            conversation_id=conversation_id,
            user_id=user_id,
            message_text=message_text,
            intent=intent_type,
            entities=entities,
            bot_response=bot_response
        )
        self.db.add(message)

        # Update conversation updated_at timestamp
        conversation = self.db.query(Conversation).filter_by(
            id=conversation_id
        ).first()
        if conversation:
            conversation.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(message)

        logger.debug(f"Saved message to conversation {conversation_id}")
        return message

    async def get_context_from_cache(self, thread_ts: str) -> Optional[Dict]:
        """Get conversation context from Redis cache.

        Args:
            thread_ts: Thread timestamp

        Returns:
            Cached context dict or None
        """
        import json

        cache_key = f"conversation_context:{thread_ts}"
        cached = await self.redis.get(cache_key)

        if cached:
            return json.loads(cached)
        return None

    async def save_context_to_cache(
        self,
        thread_ts: str,
        context: Dict,
        ttl: int = 3600
    ):
        """Save conversation context to Redis cache.

        Args:
            thread_ts: Thread timestamp
            context: Context dict to cache
            ttl: Time to live in seconds (default 1 hour)
        """
        import json

        cache_key = f"conversation_context:{thread_ts}"
        await self.redis.setex(
            cache_key,
            ttl,
            json.dumps(context)
        )
