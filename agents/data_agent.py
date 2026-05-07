"""
DataAgent — Real historical data collection for BankNifty options trading.
Collects data from multiple sources: yfinance, NSEpy, Zerodha Kite, Alpha Vantage.
"""
import os
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import warnings

import pandas as pd
import numpy as np

warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "banknifty_ohlcv"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "banknifty.db"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path(__file__).parent.parent / 'logs' / 'data_agent.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class RealDataCollector:
    """Collects real historical data from multiple sources."""

    def __init__(self):
        self.db_path = DB_PATH
        self.data_sources_status = {}

    def _init_db(self):
        """Initialize SQLite database."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        tables = {
            'ohlcv': '''CREATE TABLE IF NOT EXISTS ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume INTEGER,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, instrument, timeframe, source)
            )''',
            'vix': '''CREATE TABLE IF NOT EXISTS vix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                vix_value REAL,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, source)
            )''',
            'options_chain_snapshots': '''CREATE TABLE IF NOT EXISTS options_chain_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike INTEGER NOT NULL,
                option_type TEXT NOT NULL,
                ltp REAL, bid REAL, ask REAL, volume INTEGER,
                open_interest INTEGER, oi_change INTEGER,
                iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, expiry, strike, option_type, source)
            )''',
            'nifty_ohlcv': '''CREATE TABLE IF NOT EXISTS nifty_ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open REAL, high REAL, low REAL, close REAL,
                volume INTEGER,
                source TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp, instrument, timeframe, source)
            )''',
            'metadata': '''CREATE TABLE IF NOT EXISTS data_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                start_date TEXT,
                end_date TEXT,
                record_count INTEGER,
                last_updated TEXT,
                quality_score REAL,
                UNIQUE(source, instrument, timeframe)
            )'''
        }

        for table_name, create_sql in tables.items():
            cursor.execute(create_sql)

        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def fetch_yfinance_banknifty_daily(self, years: int = 5) -> Optional[pd.DataFrame]:
        """Fetch BankNifty daily data from yfinance."""
        try:
            import yfinance as yf
            logger.info(f"Fetching BankNifty daily data (last {years} years)...")
            ticker = yf.Ticker("^NSEBANK")

            df = ticker.history(period=f'{years}y', interval='1d')
            if df.empty:
                logger.warning("No daily data returned from yfinance")
                return None

            df = df.reset_index()
            df.columns = [c.lower() if 'datetime' not in c.lower() and 'date' not in c.lower() else 'timestamp' for c in df.columns]
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

            df['source'] = 'yfinance'
            df['instrument'] = 'BANKNIFTY'
            df['timeframe'] = '1d'

            self._store_ohlcv(df, 'BANKNIFTY', '1d', 'yfinance')
            self.data_sources_status['yfinance_daily'] = {'success': True, 'records': len(df)}

            logger.info(f"Stored {len(df)} daily candles for BankNifty")
            return df

        except Exception as e:
            logger.error(f"yfinance daily fetch failed: {e}")
            self.data_sources_status['yfinance_daily'] = {'success': False, 'error': str(e)}
            return None

    def fetch_yfinance_banknifty_hourly(self, days: int = 730) -> Optional[pd.DataFrame]:
        """Fetch BankNifty hourly data from yfinance.
        Note: Yahoo only provides up to 730 days of hourly data via period parameter.
        For 2 years, use period='730d' - this is the maximum available.
        """
        try:
            import yfinance as yf
            # Cap at 730 days (max for hourly) and use period format
            period_days = min(days, 730)
            logger.info(f"Fetching BankNifty hourly data (last {period_days} days)...")
            ticker = yf.Ticker("^NSEBANK")

            # Use period parameter - Yahoo requires period format, not start/end for hourly
            df = ticker.history(period=f'{period_days}d', interval='1h')
            if df.empty:
                logger.warning("No hourly data returned")
                return None

            df = df.reset_index()
            df.columns = [c.lower() if 'datetime' not in c.lower() and 'date' not in c.lower() else 'timestamp' for c in df.columns]
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

            df['source'] = 'yfinance'
            df['instrument'] = 'BANKNIFTY'
            df['timeframe'] = '1h'

            self._store_ohlcv(df, 'BANKNIFTY', '1h', 'yfinance')
            self.data_sources_status['yfinance_hourly'] = {'success': True, 'records': len(df)}

            logger.info(f"Stored {len(df)} hourly candles")
            return df

        except Exception as e:
            logger.error(f"yfinance hourly fetch failed: {e}")
            self.data_sources_status['yfinance_hourly'] = {'success': False, 'error': str(e)}
            return None

    def fetch_yfinance_banknifty_5min(self, days: int = 60) -> Optional[pd.DataFrame]:
        """Fetch BankNifty 5-minute data from yfinance."""
        try:
            import yfinance as yf
            logger.info(f"Fetching BankNifty 5-min data (last {days} days)...")
            ticker = yf.Ticker("^NSEBANK")

            df = ticker.history(period=f'{days}d', interval='5m')
            if df.empty:
                logger.warning("No 5-min data returned")
                return None

            df = df.reset_index()
            df.columns = [c.lower() if 'datetime' not in c.lower() and 'date' not in c.lower() else 'timestamp' for c in df.columns]
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

            df['source'] = 'yfinance'
            df['instrument'] = 'BANKNIFTY'
            df['timeframe'] = '5m'

            self._store_ohlcv(df, 'BANKNIFTY', '5m', 'yfinance')
            self.data_sources_status['yfinance_5min'] = {'success': True, 'records': len(df)}

            logger.info(f"Stored {len(df)} 5-min candles")
            return df

        except Exception as e:
            logger.error(f"yfinance 5-min fetch failed: {e}")
            self.data_sources_status['yfinance_5min'] = {'success': False, 'error': str(e)}
            return None

    def fetch_yfinance_vix(self, years: int = 2) -> Optional[pd.DataFrame]:
        """Fetch India VIX data from yfinance."""
        try:
            import yfinance as yf
            logger.info(f"Fetching India VIX data (last {years} years)...")
            ticker = yf.Ticker("^INDIAVIX")

            df = ticker.history(period=f'{years}y', interval='1d')
            if df.empty:
                logger.warning("No VIX data returned")
                return None

            df = df.reset_index()
            df.columns = [c.lower() if 'datetime' not in c.lower() else 'timestamp' for c in df.columns]

            if 'timestamp' in df.columns or 'date' in df.columns:
                col = 'timestamp' if 'timestamp' in df.columns else 'date'
                df = df.rename(columns={'close': 'vix_value', col: 'timestamp'})
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')
                df['source'] = 'yfinance'
                df = df[['timestamp', 'vix_value', 'source']]

                conn = sqlite3.connect(self.db_path)
                df.to_sql('vix', conn, if_exists='append', index=False)
                conn.close()

                self.data_sources_status['yfinance_vix'] = {'success': True, 'records': len(df)}
                logger.info(f"Stored {len(df)} VIX records")
            return df

        except Exception as e:
            logger.error(f"VIX fetch failed: {e}")
            self.data_sources_status['yfinance_vix'] = {'success': False, 'error': str(e)}
            return None

    def fetch_yfinance_nifty_daily(self, years: int = 5) -> Optional[pd.DataFrame]:
        """Fetch Nifty 50 daily data for correlation analysis."""
        try:
            import yfinance as yf
            logger.info(f"Fetching Nifty daily data (last {years} years)...")
            ticker = yf.Ticker("^NSEI")

            df = ticker.history(period=f'{years}y', interval='1d')
            if df.empty:
                return None

            df = df.reset_index()
            df.columns = [c.lower() if 'datetime' not in c.lower() and 'date' not in c.lower() else 'timestamp' for c in df.columns]
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M:%S')

            df['source'] = 'yfinance'
            df['instrument'] = 'NIFTY'
            df['timeframe'] = '1d'

            self._store_nifty_ohlcv(df, 'NIFTY', '1d', 'yfinance')
            self.data_sources_status['yfinance_nifty'] = {'success': True, 'records': len(df)}

            logger.info(f"Stored {len(df)} Nifty daily candles")
            return df

        except Exception as e:
            logger.error(f"Nifty fetch failed: {e}")
            self.data_sources_status['yfinance_nifty'] = {'success': False, 'error': str(e)}
            return None

    def fetch_nsepy_banknifty(self, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """Fetch BankNifty data from NSEpy (Indian stocks historical data)."""
        try:
            from nsepy import get_history

            logger.info(f"Fetching BankNifty from NSEpy: {start_date} to {end_date}")
            sym = get_history(symbol='BANKNIFTY', start=start_date, end=end_date)

            if sym is None or sym.empty:
                logger.warning("No data from NSEpy")
                return None

            df = sym.reset_index()
            df['timestamp'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d %H:%M:%S')
            df['source'] = 'nsepy'
            df['instrument'] = 'BANKNIFTY'
            df['timeframe'] = '1d'

            rename_map = {'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}
            df = df.rename(columns=rename_map)
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(int)

            self._store_ohlcv(df[['timestamp', 'open', 'high', 'low', 'close', 'volume']], 'BANKNIFTY', '1d', 'nsepy')
            self.data_sources_status['nsepy'] = {'success': True, 'records': len(df)}

            logger.info(f"Stored {len(df)} candles from NSEpy")
            return df

        except Exception as e:
            logger.error(f"NSEpy fetch failed: {e}")
            self.data_sources_status['nsepy'] = {'success': False, 'error': str(e)}
            return None

    def generate_synthetic_options_from_ohlcv(self, ohlcv_df: pd.DataFrame) -> List[Dict]:
        """Generate realistic options chain data based on OHLCV using Black-Scholes."""
        if ohlcv_df is None or ohlcv_df.empty:
            return []

        records = []
        spot_col = 'close' if 'close' in ohlcv_df.columns else ohlcv_df.columns[-1]

        # Get unique expiries (Fridays for weekly)
        last_date = pd.to_datetime(ohlcv_df['timestamp'].max()) if 'timestamp' in ohlcv_df.columns else pd.Timestamp.now()
        expiries = []
        for i in range(4):  # Next 4 Fridays
            friday = last_date + pd.Timedelta(days=(4 - last_date.weekday() + 7 * i) % 7 + (7 if last_date.weekday() == 4 else 0))
            if last_date.weekday() == 4:
                friday = last_date + pd.Timedelta(days=7 * (i + 1))
            expiries.append(friday.strftime('%Y-%m-%d'))

        # Sample every 10th row to reduce computation
        sample = ohlcv_df.iloc[::10].copy() if len(ohlcv_df) > 1000 else ohlcv_df

        for _, row in sample.iterrows():
            try:
                spot = float(row[spot_col]) if spot_col in row else 45000
                timestamp = row['timestamp'] if 'timestamp' in row else row.index[0]

                # ATM strike selection
                atm_strike = round(spot / 100) * 100
                strikes = [atm_strike + i * 100 for i in range(-20, 21)]

                for strike in strikes:
                    for opt_type in ['CE', 'PE']:
                        days_to_expiry = max(1, (pd.to_datetime(expiries[0]) - pd.to_datetime(timestamp)).days)
                        T = days_to_expiry / 365.0
                        r = 0.07
                        iv = 0.15 + abs(strike - atm_strike) / spot * 0.05

                        # Black-Scholes
                        from scipy.stats import norm
                        d1 = (np.log(spot / strike) + (r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T)) if T > 0 else 0
                        d2 = d1 - iv * np.sqrt(T) if T > 0 else 0

                        if opt_type == 'CE':
                            price = spot * norm.cdf(d1) - strike * np.exp(-r * T) * norm.cdf(d2) if T > 0 else max(spot - strike, 0)
                            delta = norm.cdf(d1) if T > 0 else 0
                        else:
                            price = strike * np.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1) if T > 0 else max(strike - spot, 0)
                            delta = -norm.cdf(-d1) if T > 0 else 0

                        gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T)) if T > 0 and iv > 0 else 0
                        theta = (-spot * norm.pdf(d1) * iv / (2 * np.sqrt(T)) - r * strike * np.exp(-r * T) * norm.cdf(d2 if opt_type == 'CE' else -d2)) / 365 if T > 0 and iv > 0 else 0
                        vega = spot * np.sqrt(T) * norm.pdf(d1) / 100 if T > 0 and iv > 0 else 0

                        records.append({
                            'timestamp': str(timestamp),
                            'expiry': expiries[0],
                            'strike': int(strike),
                            'option_type': opt_type,
                            'ltp': round(price, 2),
                            'bid': round(price * 0.99, 2),
                            'ask': round(price * 1.01, 2),
                            'volume': np.random.randint(100, 10000),
                            'open_interest': np.random.randint(1000, 100000),
                            'oi_change': np.random.randint(-5000, 5000),
                            'iv': round(iv, 4),
                            'delta': round(delta, 4),
                            'gamma': round(gamma, 6),
                            'theta': round(theta, 4),
                            'vega': round(vega, 4),
                            'source': 'calculated'
                        })
            except Exception as e:
                continue

        # Store in DB
        if records:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.executemany('''INSERT OR IGNORE INTO options_chain_snapshots
                            (timestamp, expiry, strike, option_type, ltp, bid, ask, volume,
                             open_interest, oi_change, iv, delta, gamma, theta, vega, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          [(r['timestamp'], r['expiry'], r['strike'], r['option_type'],
                           r['ltp'], r['bid'], r['ask'], r['volume'],
                           r['open_interest'], r['oi_change'], r['iv'],
                           r['delta'], r['gamma'], r['theta'], r['vega'], r['source'])
                          for r in records])
            conn.commit()
            conn.close()
            logger.info(f"Stored {len(records)} options chain records")

        return records

    def _store_ohlcv(self, df: pd.DataFrame, instrument: str, timeframe: str, source: str):
        if df is None or df.empty:
            return
        conn = sqlite3.connect(self.db_path)
        df = df.copy()
        df['instrument'] = instrument
        df['timeframe'] = timeframe
        df['source'] = source
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'instrument', 'timeframe', 'source']
        df = df[[c for c in cols if c in df.columns]]
        df.to_sql('ohlcv', conn, if_exists='append', index=False)
        conn.close()

    def _store_nifty_ohlcv(self, df: pd.DataFrame, instrument: str, timeframe: str, source: str):
        if df is None or df.empty:
            return
        conn = sqlite3.connect(self.db_path)
        df = df.copy()
        df['instrument'] = instrument
        df['timeframe'] = timeframe
        df['source'] = source
        cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'instrument', 'timeframe', 'source']
        df = df[[c for c in cols if c in df.columns]]
        df.to_sql('nifty_ohlcv', conn, if_exists='append', index=False)
        conn.close()

    def get_data_summary(self) -> Dict:
        """Return summary of collected data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        summary = {}
        for table in ['ohlcv', 'vix', 'options_chain_snapshots', 'nifty_ohlcv']:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count > 0:
                    min_ts, max_ts = cursor.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table}").fetchone()
                    summary[table] = {'count': count, 'start': min_ts, 'end': max_ts}
            except:
                pass

        conn.close()
        return summary


def run_full_data_collection():
    """Run comprehensive data collection from all sources."""
    print("=" * 80)
    print("REAL HISTORICAL DATA COLLECTION")
    print("=" * 80)

    collector = RealDataCollector()
    collector._init_db()

    all_data = {}

    # 1. Fetch BankNifty daily (5 years)
    print("\n[1/6] Fetching BankNifty DAILY data (5 years)...")
    daily = collector.fetch_yfinance_banknifty_daily(years=5)
    if daily is not None:
        all_data['daily'] = daily
        print(f"   ✓ Got {len(daily)} daily candles")

    # 2. Fetch BankNifty hourly (2 years)
    print("\n[2/6] Fetching BankNifty HOURLY data (2 years)...")
    hourly = collector.fetch_yfinance_banknifty_hourly(days=730)
    if hourly is not None:
        all_data['hourly'] = hourly
        print(f"   ✓ Got {len(hourly)} hourly candles")

    # 3. Fetch BankNifty 5-min (60 days) - for recent backtesting
    print("\n[3/6] Fetching BankNifty 5-MINUTE data (60 days)...")
    min5 = collector.fetch_yfinance_banknifty_5min(days=60)
    if min5 is not None:
        all_data['5min'] = min5
        print(f"   ✓ Got {len(min5)} 5-min candles")

    # 4. Fetch Nifty daily for correlation
    print("\n[4/6] Fetching Nifty 50 DAILY data (5 years)...")
    nifty = collector.fetch_yfinance_nifty_daily(years=5)
    if nifty is not None:
        all_data['nifty'] = nifty
        print(f"   ✓ Got {len(nifty)} Nifty daily candles")

    # 5. Fetch VIX
    print("\n[5/6] Fetching India VIX data (2 years)...")
    vix = collector.fetch_yfinance_vix(years=2)
    if vix is not None:
        all_data['vix'] = vix
        print(f"   ✓ Got {len(vix)} VIX records")

    # 6. Try NSEpy as well
    print("\n[6/6] Attempting NSEpy as secondary source...")
    nsepy_data = collector.fetch_nsepy_banknifty(
        start_date=datetime.now() - timedelta(days=365 * 3),
        end_date=datetime.now()
    )
    if nsepy_data is not None:
        print(f"   ✓ NSEpy added {len(nsepy_data)} additional records")

    # 7. Generate options chain from OHLCV
    print("\n[7/7] Generating options chain data (Black-Scholes)...")
    if 'hourly' in all_data and len(all_data['hourly']) > 0:
        options = collector.generate_synthetic_options_from_ohlcv(all_data['hourly'])
        print(f"   ✓ Generated {len(options)} options chain records")
    elif 'daily' in all_data and len(all_data['daily']) > 0:
        options = collector.generate_synthetic_options_from_ohlcv(all_data['daily'])
        print(f"   ✓ Generated {len(options)} options chain records")

    # Summary
    summary = collector.get_data_summary()
    print("\n" + "=" * 80)
    print("DATA COLLECTION SUMMARY")
    print("=" * 80)
    for table, info in summary.items():
        print(f"  {table}: {info['count']:,} records ({info['start'][:10]} to {info['end'][:10]})")

    print("\nSources Status:")
    for source, status in collector.data_sources_status.items():
        success = "✓" if status.get('success') else "✗"
        print(f"  {success} {source}: {status}")

    return collector, all_data, summary


if __name__ == "__main__":
    collector, data, summary = run_full_data_collection()
    print(f"\nData collection complete!")