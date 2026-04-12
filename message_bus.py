"""
LaunchMind GigGuard — Message Bus
Shared messaging system for agent-to-agent communication.
Uses a shared Python dictionary (Option A from assignment spec).
"""

import uuid
import json
from datetime import datetime, timezone


class MessageBus:
    """
    Central message bus for agent communication.
    Every message follows the required schema:
      message_id, from_agent, to_agent, message_type, payload, timestamp, parent_message_id
    """

    def __init__(self):
        # Mailboxes: agent_name -> list of messages
        self._mailboxes = {}
        # Full ordered history of every message sent
        self._history = []

    def send(self, from_agent: str, to_agent: str, message_type: str,
             payload: dict, parent_message_id: str = None) -> str:
        """
        Send a structured message from one agent to another.

        Args:
            from_agent:  Name of the sending agent (e.g. 'ceo', 'product')
            to_agent:    Name of the receiving agent
            message_type: One of: 'task', 'result', 'revision_request', 'confirmation'
            payload:     The actual content dict
            parent_message_id: Optional ID of the message this replies to

        Returns:
            The message_id of the sent message.
        """
        message_id = f"msg-{uuid.uuid4().hex[:8]}"
        message = {
            "message_id": message_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_type": message_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent_message_id": parent_message_id,
        }

        # Ensure mailbox exists
        if to_agent not in self._mailboxes:
            self._mailboxes[to_agent] = []

        self._mailboxes[to_agent].append(message)
        self._history.append(message)

        # Print to terminal as messages happen (required for demo)
        print(f"\n{'='*60}")
        print(f"📨 MESSAGE  [{from_agent}] ➜ [{to_agent}]  ({message_type})")
        print(f"   ID: {message_id}")
        if parent_message_id:
            print(f"   Reply to: {parent_message_id}")
        print(f"   Time: {message['timestamp']}")
        print(f"   Payload keys: {list(payload.keys())}")
        print(f"{'='*60}")

        return message_id

    def receive(self, agent_name: str) -> list:
        """
        Receive all pending messages for an agent and clear its mailbox.

        Args:
            agent_name: The agent whose messages to retrieve.

        Returns:
            List of message dicts.
        """
        messages = self._mailboxes.get(agent_name, [])
        self._mailboxes[agent_name] = []
        return messages

    def get_history(self, agent_name: str = None) -> list:
        """
        Get the full message history, optionally filtered by agent.

        Args:
            agent_name: If provided, return only messages sent or received by this agent.

        Returns:
            List of message dicts.
        """
        if agent_name is None:
            return list(self._history)
        return [
            m for m in self._history
            if m["from_agent"] == agent_name or m["to_agent"] == agent_name
        ]

    def print_full_history(self):
        """Print the complete message log (for demo/debugging)."""
        print(f"\n{'#'*60}")
        print(f"  FULL MESSAGE HISTORY — {len(self._history)} messages")
        print(f"{'#'*60}")
        for i, msg in enumerate(self._history, 1):
            print(f"\n--- Message {i} ---")
            print(json.dumps(msg, indent=2))
        print(f"\n{'#'*60}\n")
