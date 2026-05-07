"""
DataFeeder — Streams tick-by-tick data for backtesting simulation.
Mimics live market data feed with configurable speed control.
"""
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Callable

import pandas as pd

BASE_DIR = Path(__file__).parent.parent.parent.parent
FEEDS_DIR = BASE_DIR / "data" / "feeds"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler(Path(__file__).parent.parent.parent / 'logs' / 'data_feeder.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class DataFeeder:
    """Streams tick-by-tick data from simulation feed with pause/resume/speed control."""

    def __init__(self, feed_path: Path = None):
        self.feed_path = feed_path or (FEEDS_DIR / "simulation_feed.json")
        self.data: List[Dict] = []
        self.current_index = 0
        self.speed = 1  # 1x, 10x, 100x
        self.paused = False
        self.callbacks: Dict[str, Callable] = {}
        self.is_running = False
        self.load_data()

    def load_data(self):
        """Load tick data from JSON or XLSX."""
        if self.feed_path.suffix == ".xlsx":
            df = pd.read_excel(self.feed_path, sheet_name='Ticks')
            self.data = df.to_dict('records')
        elif self.feed_path.suffix == ".json":
            with open(self.feed_path) as f:
                self.data = json.load(f)
        else:
            raise ValueError(f"Unsupported feed format: {self.feed_path}")
        logger.info(f"DataFeeder loaded {len(self.data)} records from {self.feed_path}")

    def register_callback(self, event: str, callback: Callable):
        """Register callback for specific events: on_tick, on_candle_close, on_new_day, on_expiry."""
        self.callbacks[event] = callback

    def _emit(self, event: str, data: dict):
        if event in self.callbacks:
            try:
                self.callbacks[event](data)
            except Exception as e:
                logger.error(f"Callback error for {event}: {e}")

    def pause(self):
        self.paused = True
        logger.info("DataFeeder paused")

    def resume(self):
        self.paused = False
        logger.info("DataFeeder resumed")

    def set_speed(self, speed: int):
        self.speed = speed
        logger.info(f"DataFeeder speed set to {speed}x")

    def reset(self):
        self.current_index = 0
        logger.info("DataFeeder reset to beginning")

    def run(self, tick_interval: float = 0.1):
        """Run the feeder, emitting ticks at tick_interval (adjusted by speed)."""
        self.is_running = True
        self.current_index = 0

        while self.current_index < len(self.data) and self.is_running:
            if self.paused:
                time.sleep(0.1)
                continue

            tick = self.data[self.current_index]
            self._emit('on_tick', tick)

            if 'timestamp' in tick:
                current_date = str(tick.get('timestamp', ''))[:10]
                if hasattr(self, '_last_date') and str(self._last_date) != current_date:
                    self._emit('on_new_day', {'date': current_date})
                self._last_date = current_date

            self.current_index += 1

            adjusted_interval = tick_interval / self.speed
            time.sleep(adjusted_interval)

        logger.info(f"DataFeeder completed. Emitted {self.current_index} ticks.")

    def stop(self):
        self.is_running = False

    def get_current_data(self) -> List[Dict]:
        return self.data[:self.current_index]

    def get_remaining(self) -> int:
        return len(self.data) - self.current_index


if __name__ == "__main__":
    feeder = DataFeeder()
    print(f"Loaded {len(feeder.data)} records. Ready to feed.")