import time
from typing import Dict, Optional

class SessionManager:
    def __init__(self):
        self.user_sessions: Dict[str, dict] = {}

    def get(self, key: str) -> Optional[dict]:
        return self.user_sessions.get(key)

    def set(self, key: str, value: dict):
        self.user_sessions[key] = value

    def delete(self, key: str):
        self.user_sessions.pop(key, None)

    def cleanup_expired(self, timeout_seconds: int = 180):
        now = time.time()
        expired = [k for k, s in self.user_sessions.items()
                   if s.get("state") == "awaiting_selection" and (now - s.get("timestamp", 0) > timeout_seconds)]
        for k in expired:
            self.user_sessions.pop(k, None)