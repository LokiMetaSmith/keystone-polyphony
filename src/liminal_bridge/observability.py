from typing import List, Dict, Any, Deque
from collections import deque
import time


class LogAggregator:
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.logs: Deque[Dict[str, Any]] = deque(maxlen=max_size)
        self.telemetry: Dict[str, Any] = {
            "latency": [],
            "message_count": 0,
            "contentions": 0,
        }

    def add_telemetry(self, key: str, value: Any):
        if key == "latency":
            self.telemetry["latency"].append(value)
            if len(self.telemetry["latency"]) > 100:
                self.telemetry["latency"].pop(0)
        elif key in ["message_count", "contentions"]:
            self.telemetry[key] += value

    def add_log(self, entry: Dict[str, Any]):
        """Adds a log entry to the local buffer."""
        # Ensure timestamp exists
        if "timestamp" not in entry:
            entry["timestamp"] = time.time()
        self.logs.append(entry)

    def get_logs(self) -> List[Dict[str, Any]]:
        """Returns a list of logs."""
        return list(self.logs)
