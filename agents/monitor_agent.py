"""
MonitorAgent — Supervises all agents, handles retries, errors, and escalation.
Maintains agent status, pings for liveness, and logs all system activities.
"""
import os
import json
import logging
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.parent
AGENT_STATUS_PATH = BASE_DIR / "agents" / "agent_status.json"
MESSAGE_QUEUE_PATH = BASE_DIR / "agents" / "message_queue.json"
LOGS_DIR = BASE_DIR / "logs"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'monitor_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MonitorAgent:
    """Monitors all agents, handles failures, retries, and escalation."""

    PING_INTERVAL = 30  # seconds
    FAILURE_THRESHOLD = 3
    STUCK_THRESHOLD = 300  # 5 minutes in seconds

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator
        self.agent_status: Dict[str, dict] = {}
        self.message_queue: List[dict] = []
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._load_status()
        logger.info("MonitorAgent initialized")

    def _load_status(self):
        """Load existing agent status from disk."""
        if AGENT_STATUS_PATH.exists():
            try:
                with open(AGENT_STATUS_PATH, 'r') as f:
                    self.agent_status = json.load(f)
                logger.info(f"Loaded status for {len(self.agent_status)} agents")
            except Exception as e:
                logger.error(f"Failed to load agent status: {e}")

    def _save_status(self):
        """Save agent status to disk."""
        with open(AGENT_STATUS_PATH, 'w') as f:
            json.dump(self.agent_status, f, indent=2)

    def register_agent(self, name: str, role: str, file: str):
        """Register a new agent with the monitor."""
        self.agent_status[name] = {
            "role": role,
            "file": file,
            "status": "idle",
            "last_ping": time.time(),
            "failures": 0,
            "current_task": None
        }
        logger.info(f"Monitor: Registered agent {name} ({role})")
        self._save_status()

    def update_status(self, name: str, status: str, details: str = ""):
        """Update an agent's status."""
        if name in self.agent_status:
            self.agent_status[name]["status"] = status
            self.agent_status[name]["last_ping"] = time.time()
            if details:
                self.agent_status[name]["current_task"] = details
            logger.info(f"Monitor: {name} -> {status} ({details})")
            self._save_status()

    def ping_agents(self):
        """Ping all agents to check for liveness."""
        now = time.time()
        stuck_agents = []
        unresponsive = []

        for name, status in self.agent_status.items():
            last_ping = status.get("last_ping", 0)
            if now - last_ping > self.STUCK_THRESHOLD:
                stuck_agents.append(name)
            elif now - last_ping > self.PING_INTERVAL:
                status["status"] = "unresponsive"
                unresponsive.append(name)

        for name in stuck_agents:
            logger.error(f"Agent {name} stuck for >5 minutes — escalating")
            self._escalate(name, "STUCK", f"No response for {self.STUCK_THRESHOLD}s")

        self._save_status()
        return {"stuck": stuck_agents, "unresponsive": unresponsive}

    def _escalate(self, agent_name: str, reason: str, details: str):
        """Escalate an issue to the orchestrator."""
        logger.warning(f"ESCALATION: {agent_name} — {reason}: {details}")
        self.agent_status[agent_name]["failures"] = self.agent_status[agent_name].get("failures", 0) + 1

        if self.orchestrator:
            self.orchestrator.route_message({
                "from": "MonitorAgent",
                "to": "Orchestrator",
                "type": "ESCALATION",
                "payload": {
                    "agent": agent_name,
                    "reason": reason,
                    "details": details,
                    "failure_count": self.agent_status[agent_name]["failures"]
                }
            })

    def retry_agent(self, agent_name: str) -> bool:
        """Attempt to retry a failed agent."""
        failures = self.agent_status.get(agent_name, {}).get("failures", 0)
        if failures >= self.FAILURE_THRESHOLD:
            logger.error(f"Agent {agent_name} exceeded failure threshold — manual intervention required")
            return False

        logger.info(f"Retrying agent {agent_name} (attempt {failures + 1}/{self.FAILURE_THRESHOLD})")
        self.agent_status[agent_name]["failures"] = failures + 1
        self.agent_status[agent_name]["status"] = "retrying"
        self._save_status()
        return True

    def route_message(self, message: dict):
        """Add message to queue and dispatch to recipient."""
        self.message_queue.append({
            **message,
            "queued_at": datetime.now().isoformat()
        })
        self._save_queue()

        recipient = message.get("to")
        if recipient in self.agent_status:
            self.agent_status[recipient]["status"] = "message_waiting"
            self._save_status()

    def _save_queue(self):
        """Persist message queue to disk."""
        with open(MESSAGE_QUEUE_PATH, 'w') as f:
            json.dump(self.message_queue[-100:], f, indent=2)

    def get_pending_messages(self, agent_name: str) -> List[dict]:
        """Get and clear pending messages for an agent."""
        messages = [m for m in self.message_queue if m.get("to") == agent_name]
        self.message_queue = [m for m in self.message_queue if m.get("to") != agent_name]
        self._save_queue()
        return messages

    def start_monitoring(self):
        """Start the monitoring loop in a background thread."""
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("MonitorAgent started monitoring loop")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.is_running:
            try:
                self.ping_agents()
                time.sleep(self.PING_INTERVAL)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

    def stop_monitoring(self):
        """Stop the monitoring loop."""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("MonitorAgent stopped")

    def get_system_status(self) -> Dict:
        """Get overall system status summary."""
        total = len(self.agent_status)
        active = sum(1 for s in self.agent_status.values() if s.get("status") == "running")
        idle = sum(1 for s in self.agent_status.values() if s.get("status") == "idle")
        failed = sum(1 for s in self.agent_status.values() if s.get("failures", 0) >= self.FAILURE_THRESHOLD)

        return {
            "total_agents": total,
            "active": active,
            "idle": idle,
            "failed": failed,
            "queue_size": len(self.message_queue),
            "timestamp": datetime.now().isoformat()
        }

    def log_event(self, event_type: str, details: Dict):
        """Log a system event to the error log."""
        log_path = LOGS_DIR / "system_events.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat()
        with open(log_path, 'a') as f:
            f.write(f"[{timestamp}] {event_type}: {json.dumps(details)}\n")

    def run(self):
        """Run the monitor agent."""
        logger.info("MonitorAgent running...")
        self.start_monitoring()

        registered_agents = [
            ("DataAgent", "data", "agents/data_agent.py"),
            ("ResearchAgent", "research", "agents/research_agent.py"),
            ("BacktestAgent", "backtest", "agents/backtest_agent.py"),
            ("ReviewAgent", "review", "agents/review_agent.py"),
            ("JournalAgent", "journal", "agents/journal_agent.py"),
            ("AlgoAgent", "algo", "agents/algo_agent.py"),
            ("ConfigAgent", "config", "agents/config_agent.py"),
        ]

        for name, role, file in registered_agents:
            self.register_agent(name, role, file)

        logger.info(f"MonitorAgent initialized with {len(self.agent_status)} agents")
        return self.get_system_status()


if __name__ == "__main__":
    monitor = MonitorAgent()
    status = monitor.run()
    print(f"Monitor running: {status}")