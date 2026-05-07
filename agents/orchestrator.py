"""
Orchestrator Agent — Master coordinator for BankNifty Options Trading System.
Spawns, supervises, and coordinates all sub-agents throughout the trading pipeline.
"""
import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
MESSAGE_QUEUE_PATH = BASE_DIR / "agents" / "message_queue.json"
AGENT_STATUS_PATH = BASE_DIR / "agents" / "agent_status.json"
AGENTS_DIR = BASE_DIR / "agents"

class OrchestratorAgent:
    """Master orchestrator coordinating all trading system agents."""

    def __init__(self):
        self.agents: Dict[str, str] = {}
        self.active_agents: Dict[str, dict] = {}
        self.message_queue: List[dict] = []
        logger.info("OrchestratorAgent initialized")

    def _load_config(self) -> dict:
        config_path = BASE_DIR / "config" / "master_config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path) as f:
                return yaml.safe_load(f)
        return {}

    def _init_message_queue(self):
        if not MESSAGE_QUEUE_PATH.exists():
            with open(MESSAGE_QUEUE_PATH, 'w') as f:
                json.dump([], f)

    def _init_agent_status(self):
        if not AGENT_STATUS_PATH.exists():
            with open(AGENT_STATUS_PATH, 'w') as f:
                json.dump({}, f)

    def register_agent(self, name: str, agent_file: str, role: str):
        """Register an agent with the system."""
        self.agents[name] = agent_file
        self.active_agents[name] = {
            "role": role,
            "status": "idle",
            "last_ping": time.time(),
            "file": agent_file
        }
        logger.info(f"Registered agent: {name} ({role})")

    def route_message(self, message: dict):
        """Route a message to the appropriate agent via message queue."""
        self.message_queue.append({
            **message,
            "timestamp": datetime.now().isoformat()
        })
        with open(MESSAGE_QUEUE_PATH, 'w') as f:
            json.dump(self.message_queue, f, indent=2)

    def get_pending_messages(self, agent_name: str) -> List[dict]:
        """Get pending messages for a specific agent."""
        messages = [m for m in self.message_queue if m.get("to") == agent_name]
        self.message_queue = [m for m in self.message_queue if m.get("to") != agent_name]
        with open(MESSAGE_QUEUE_PATH, 'w') as f:
            json.dump(self.message_queue, f, indent=2)
        return messages

    def ping_agents(self):
        """Ping all registered agents to check liveness."""
        for name, status in self.active_agents.items():
            if time.time() - status["last_ping"] > 300:
                logger.warning(f"Agent {name} has not responded in >5 minutes")
                status["status"] = "unresponsive"
        self._save_agent_status()

    def _save_agent_status(self):
        with open(AGENT_STATUS_PATH, 'w') as f:
            json.dump(self.active_agents, f, indent=2)

    def update_agent_status(self, name: str, status: str, details: str = ""):
        """Update an agent's status."""
        if name in self.active_agents:
            self.active_agents[name]["status"] = status
            self.active_agents[name]["last_ping"] = time.time()
            if details:
                self.active_agents[name]["details"] = details
            logger.info(f"Agent {name} status: {status} — {details}")
            self._save_agent_status()

    def run_phase(self, phase: int, agents: List[str]):
        """Run a specific phase with specified agents."""
        logger.info(f"=== PHASE {phase} STARTED with agents: {agents} ===")
        for agent in agents:
            if agent in self.agents:
                logger.info(f"Executing {agent} for phase {phase}")
                self.update_agent_status(agent, "running", f"Phase {phase}")

    def broadcast(self, message_type: str, payload: dict, exclude: List[str] = None):
        """Broadcast a message to all agents."""
        exclude = exclude or []
        for name in self.agents:
            if name not in exclude:
                self.route_message({
                    "from": "Orchestrator",
                    "to": name,
                    "type": message_type,
                    "payload": payload
                })

    def shutdown(self):
        """Graceful shutdown of all agents."""
        logger.info("Orchestrator shutting down...")
        self.broadcast("SYSTEM_SHUTDOWN", {"reason": "Orchestrator shutdown"})
        self.update_agent_status("Orchestrator", "shutdown")

if __name__ == "__main__":
    orch = OrchestratorAgent()
    print("Orchestrator Agent started. Waiting for tasks...")