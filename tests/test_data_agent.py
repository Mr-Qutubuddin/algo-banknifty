-- Test suite for BankNifty Options Algo Trading System

-- Test DataAgent
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_data_agent_import():
    from agents.data_agent import DataAgent
    assert DataAgent is not None

def test_data_agent_init():
    from agents.data_agent import DataAgent
    agent = DataAgent()
    assert agent is not None
    assert agent.db_path is not None

def test_greeks_calculation():
    from agents.data_agent import DataAgent
    agent = DataAgent()
    greeks = agent.calculate_greeks(45000, 45000, 7, 0.07, 0.20, "CE")
    assert 'delta' in greeks
    assert 'gamma' in greeks
    assert 'theta' in greeks
    assert 'vega' in greeks
    assert 0 < greeks['delta'] < 1

def test_synthetic_data_generation():
    from agents.data_agent import DataAgent
    from datetime import datetime, timedelta
    agent = DataAgent()
    end = datetime.now()
    start = end - timedelta(days=30)
    df = agent.generate_synthetic_ohlcv(start, end, base_price=45000)
    assert len(df) > 0
    assert 'timestamp' in df.columns
    assert 'close' in df.columns

def test_simulation_feed_generation():
    from agents.data_agent import DataAgent
    from pathlib import Path
    agent = DataAgent()
    output_json = Path("data/feeds/test_feed.json")
    output_xlsx = Path("data/feeds/test_feed.xlsx")
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=7)
    df = agent.build_simulation_feed(start, end, output_json, output_xlsx)
    assert output_json.exists() or output_xlsx.exists()


-- Test OrderSimulator
def test_order_simulator_init():
    from backtests.simulation_engine.order_simulator import OrderSimulator
    sim = OrderSimulator()
    assert sim is not None
    assert sim.lot_size == 15

def test_market_order():
    from backtests.simulation_engine.order_simulator import OrderSimulator
    sim = OrderSimulator()
    order = sim.place_market_order("BANKNIFTY", "BUY", 1, 350, "CE")
    assert order['status'] == 'FILLED'
    assert order['fill_price'] > 0

def test_charges_calculation():
    from backtests.simulation_engine.order_simulator import OrderSimulator
    sim = OrderSimulator()
    charges = sim.calculate_charges(350, "BUY")
    assert 'brokerage' in charges
    assert 'stt' in charges
    assert 'gst' in charges
    assert 'total_charges' in charges
    assert charges['total_charges'] > 0


-- Test PortfolioTracker
def test_portfolio_init():
    from backtests.simulation_engine.portfolio_tracker import PortfolioTracker
    pt = PortfolioTracker(100000)
    assert pt.initial_capital == 100000
    assert pt.cash == 100000

def test_position_open():
    from backtests.simulation_engine.portfolio_tracker import PortfolioTracker
    from backtests.simulation_engine.order_simulator import OrderSimulator
    pt = PortfolioTracker(100000)
    sim = OrderSimulator()
    order = sim.place_market_order("BANKNIFTY", "BUY", 1, 350, "CE")
    pt.open_position(order)
    assert pt.get_open_positions_count() == 1

def test_pnl_calculation():
    from backtests.simulation_engine.portfolio_tracker import PortfolioTracker
    pt = PortfolioTracker(100000)
    assert pt.get_total_pnl() == 0


-- Test ConfigAgent
def test_config_agent_init():
    from agents.config_agent import ConfigAgent
    agent = ConfigAgent()
    assert agent is not None

def test_config_get():
    from agents.config_agent import ConfigAgent
    agent = ConfigAgent()
    config = agent.get("master_config")
    assert isinstance(config, dict)


-- Test PaperTrading Broker
def test_paper_broker_init():
    from algo.brokers.paper_trading import PaperTradingBroker
    broker = PaperTradingBroker()
    assert broker.is_connected == True

def test_paper_market_order():
    from algo.brokers.paper_trading import PaperTradingBroker
    broker = PaperTradingBroker()
    order = broker.place_market_order("BANKNIFTY", "BUY", 1, 350, "CE")
    assert order['status'] == 'FILLED'


-- Test ReviewAgent
def test_review_agent_init():
    from agents.review_agent import ReviewAgent
    agent = ReviewAgent()
    assert agent is not None

def test_disqualification_check():
    from agents.review_agent import ReviewAgent
    agent = ReviewAgent()
    result = {'sharpe_ratio': 0.5, 'max_drawdown_pct': 30, 'total_trades': 20}
    disqualified, reason = agent.check_disqualification(result)
    assert disqualified == True


-- Test DataFeeder
def test_data_feeder_init():
    from backtests.simulation_engine.data_feeder import DataFeeder
    from pathlib import Path
    feeder = DataFeeder(Path("data/feeds/simulation_feed.json"))
    # If no data, that's okay for unit test
    assert feeder is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])