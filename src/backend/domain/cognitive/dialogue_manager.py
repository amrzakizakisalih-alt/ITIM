"""
DialogueManager – Dialogue manager.

Maintains the history of the tutor/learner conversation and
builds the context needed to generate coherent responses.
"""

from typing import List, Dict, Any


class DialogueManager:
    """
    Manages the history and context of exchanges.
    """

    def __init__(self, max_history: int = 50):
        self.history: List[Dict[str, Any]] = []
        self.max_history = max_history

    def add_message(self, role: str, text: str, metadata: dict = None):
        """Adds a message to the history."""
        self.history.append({
            "role": role,          # "user" | "assistant" | "system"
            "text": text,
            "metadata": metadata or {},
        })
        # Truncate if necessary
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def get_context(self, n_last: int = 10) -> List[Dict[str, str]]:
        """Returns the last n messages formatted for an LLM."""
        return [
            {"role": msg["role"], "content": msg["text"]}
            for msg in self.history[-n_last:]
        ]


    def reset(self):
        """Clears the history."""
        self.history.clear()
