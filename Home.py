import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import warnings
import tushare as ts
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

warnings.filterwarnings('ignore')

# --- Page Config ---
st.set_page_config(page_title="ETF 动量策略回测系统", layout="wide", page_icon="📈")

import statsmodels.api as sm

# --- Helper: Data Update ---
def update_data(token, force=False):
    """
    Update ETF data using Tushare.
    force: If True, re-download all data from scratch.
    """
    if not token:
        st.error("未检测到 Tushare Token，无法更新数据。")
        return False

    try:
        ts.set_token(token)
        pro = ts.pro_api(token)
    except Exception as e:
        st.error(f"Tushare 初始化失败: {e}")
        return False

    etfs = [
        {'code': '513520.SH', 'name': '日经ETF', 'start_date': '20190612'},
        {'code': '513100.SH', 'name': '纳指ETF', 'start_date': '20130515'},
        {'code': '513020.SH', 'name': '港股科技ETF', 'start_date': '20220127'},
        {'code': '510180.SH', 'name': '180ETF', 'start_date': '20060518'},
        {'code': '588120.SH', 'name': '科创板ETF', 'start_date': '20230908'},
        {'code': '159915.SZ', 'name': '创业板ETF', 'start_date': '20111209'},
        {'code': '501018.SH', 'name': '南方原油(LOF)', 'start_date': '20160624'},
        {'code': '518880.SH', 'name': '黄金ETF', 'start_date': '20130729'},
        {'code': '511090.SH', 'name': '30年国债ETF', 'start_date': '20230613'},
    ]

    progress_bar = st.progress(0)
    status_text = st.empty()
    log_area = st.empty()
    logs = []

    # Use Shanghai timezone and latest open trade date to avoid server timezone drift.
    sh_now = datetime.now(ZoneInfo("Asia/Shanghai"))
    calendar_end = sh_now.strftime('%Y%m%d')
    today = calendar_end
    try:
        cal_start = (sh_now - timedelta(days=31)).strftime('%Y%m%d')
        trade_cal = pro.trade_cal(exchange='', start_date=cal_start, end_date=calendar_end, is_open='1')
        if trade_cal is not None and not trade_cal.empty:
            today = str(trade_cal['cal_date'].max())
    except Exception as e:
        logs.append(f"交易日历获取失败，回退到自然日 {calendar_end}: {e}")
    
    total_etfs = len(etfs)
    
    for i, etf in enumerate(etfs):
        code = etf['code']
        name = etf['name']
        filename = f"data/{code}_{name}_history.csv"
        
        status_text.text(f"正在处理: {name} ({code})...")
        
        # Determine start date
        start_date = etf['start_date']
        existing_df = None
        
        if not force and os.path.exists(filename):
            try:
                existing_df = pd.read_csv(filename)
                # Ensure correct datetime parsing
                if 'trade_date' in existing_df.columns:
                    try:
                        existing_df['trade_date'] = pd.to_datetime(existing_df['trade_date'], format='%Y%m%d')
                    except:
                        existing_df['trade_date'] = pd.to_datetime(existing_df['trade_date'])
                        
                if not existing_df.empty:
                    last_date = existing_df['trade_date'].max()
                    start_date = (last_date + timedelta(days=1)).strftime('%Y%m%d')
            except Exception as e:
                logs.append(f"读取现有文件 {filename} 失败: {e}")
        
        # Fetch Data
        if not force and start_date > today:
            logs.append(f"{name}: 数据已是最新。")
        else:
            try:
                # Use retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Fetch unadjusted
                        df_raw = ts.pro_bar(ts_code=code, start_date=start_date, end_date=today, adj=None, asset='FD')
                        # Fetch adjusted (qfq)
                        df_adj = ts.pro_bar(ts_code=code, start_date=start_date, end_date=today, adj='qfq', asset='FD')
                        
                        break # Success
                    except Exception as e:
                        if attempt == max_retries - 1:
                            raise e
                        time.sleep(1)
                
                if df_raw is not None and not df_raw.empty:
                    if df_adj is None or df_adj.empty:
                        df_adj = df_raw.copy()
                    
                    df_raw = df_raw.set_index('trade_date').sort_index()
                    df_adj = df_adj.set_index('trade_date').sort_index()
                    
                    adj_cols = ['open', 'high', 'low', 'close']
                    existing_adj_cols = [c for c in adj_cols if c in df_adj.columns]
                    df_adj_subset = df_adj[existing_adj_cols].rename(columns={c: f'adj_{c}' for c in existing_adj_cols})
                    
                    df_new = df_raw.join(df_adj_subset, how='left').reset_index()
                    df_new['trade_date'] = pd.to_datetime(df_new['trade_date'], format='%Y%m%d')
                    
                    # Merge
                    if existing_df is not None:
                        # Ensure types match
                        # existing_df already has datetime trade_date
                        df_final = pd.concat([existing_df, df_new], ignore_index=True)
                        df_final.drop_duplicates(subset=['trade_date'], inplace=True)
                    else:
                        df_final = df_new
                        
                    df_final.sort_values('trade_date', inplace=True)
                    # Save back with %Y%m%d format for consistency if needed, but pandas saves default format. 
                    # Original script read/write cycle might change format. 
                    # Let's ensure trade_date is saved in a way readable by read_csv later.
                    # Original script: to_csv index=False.
                    # Standard pandas to_csv saves datetime as YYYY-MM-DD.
                    # Our load function uses: pd.to_datetime(df['trade_date'], format='%Y%m%d')
                    # Wait, original script saved as default (likely YYYY-MM-DD or whatever).
                    # But load function specifies format='%Y%m%d'. 
                    # If pandas saves as YYYY-MM-DD, load might fail if format is strict.
                    # Let's check original script:
                    # df['trade_date'] in tushare is usually string 'YYYYMMDD'.
                    # In download_etf_data.py: df_final.to_csv(...)
                    # It doesn't convert to datetime object before saving. So it saves 'YYYYMMDD' strings.
                    # My update logic converted to datetime: df_new['trade_date'] = pd.to_datetime(...)
                    # So I should convert back to 'YYYYMMDD' string before saving to match original format.
                    
                    df_final['trade_date'] = df_final['trade_date'].dt.strftime('%Y%m%d')
                    df_final.to_csv(filename, index=False, encoding='utf-8-sig')
                    latest_saved_date = df_final['trade_date'].max()
                    logs.append(f"{name}: 更新了 {len(df_new)} 条记录，最新日期 {latest_saved_date}。")
                else:
                    logs.append(f"{name}: 无新数据（当前按最近开放交易日 {today} 检查）。")
            except Exception as e:
                logs.append(f"{name} 更新失败: {e}")
        
        progress_bar.progress((i + 1) / total_etfs)
        time.sleep(0.1) # Be nice to API
        
    status_text.text("数据更新完成！")
    with st.expander("查看更新日志"):
        st.write(logs)
    
    return True

def get_tushare_token():
    """
    Read Tushare token from Streamlit secrets or sidebar session override.
    """
    ts_token = ""

    try:
        if "TUSHARE_TOKEN" in st.secrets:
            ts_token = st.secrets["TUSHARE_TOKEN"]
    except:
        pass

    if not ts_token:
        ts_token = os.getenv("TUSHARE_TOKEN", "").strip()

    if 'tushare_token' in st.session_state and st.session_state['tushare_token']:
        ts_token = st.session_state['tushare_token']

    return ts_token

# --- 1. Data Loading ---

@st.cache_data
def load_history_data():
    mapping = {
        '创业板': 'data/159915.SZ_创业板ETF_history.csv',
        '南方原油': 'data/501018.SH_南方原油(LOF)_history.csv',
        '上证180': 'data/510180.SH_180ETF_history.csv',
        '30年国债': 'data/511090.SH_30年国债ETF_history.csv',
        '港股科技': 'data/513020.SH_港股科技ETF_history.csv',
        '纳指100': 'data/513100.SH_纳指ETF_history.csv',
        '日经ETF': 'data/513520.SH_日经ETF_history.csv',
        '黄金ETF': 'data/518880.SH_黄金ETF_history.csv',
        '科创板': 'data/588120.SH_科创板ETF_history.csv'
    }
    history_data = {}
    for name, filename in mapping.items():
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename)
                # Flexible parsing
                if 'trade_date' in df.columns:
                    # Try YYYYMMDD first
                    try:
                        df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
                    except:
                        # Try auto
                        df['trade_date'] = pd.to_datetime(df['trade_date'])
                        
                df = df.sort_values('trade_date').set_index('trade_date')
                history_data[name] = df
            except Exception as e:
                st.error(f"Error loading {filename}: {e}")
    return history_data

def filter_history_data(history_data, selected_assets):
    """
    Filter history_data by asset names.
    selected_assets: list[str] | None
    """
    if not selected_assets:
        return {}
    selected_set = set(selected_assets)
    return {k: v for k, v in history_data.items() if k in selected_set}

@st.cache_data
def calculate_rolling_scores(series, window=20):
    """
    Calculate Quadratic Weighted Linear Regression Momentum Score.
    """
    scores = pd.Series(index=series.index, dtype=float)
    scores[:] = np.nan
    
    # Pre-compute weights
    x = np.arange(window)
    x_norm = np.linspace(0, 1, window)
    weights = 1 + x_norm ** 2
    
    # We need log prices
    log_prices = np.log(series)
    values = log_prices.values
    
    # Loop over the series
    for i in range(window, len(values) + 1):
        window_data = values[i-window : i]
        
        # Check for NaNs
        if np.isnan(window_data).any():
            continue
            
        try:
            coeffs = np.polyfit(x, window_data, 1, w=weights)
            slope = coeffs[0]
            
            # R2
            y_pred = np.polyval(coeffs, x)
            sse = np.sum(weights * (window_data - y_pred)**2)
            y_mean = np.average(window_data, weights=weights)
            sst = np.sum(weights * (window_data - y_mean)**2)
            
            if sst == 0: r2 = 0
            else: r2 = 1 - sse / sst
            
            score = (np.exp(slope * 252) - 1) * r2 * 100
            scores.iloc[i-1] = score
        except:
            pass
            
    return scores

@st.cache_data
def precalculate_all_scores(history_data, window=20):
    all_scores = pd.DataFrame()
    for asset, df in history_data.items():
        # Prefer adjusted close
        if 'adj_close' in df.columns:
            series = df['adj_close']
        elif 'close' in df.columns:
            series = df['close']
        else:
            continue
            
        scores = calculate_rolling_scores(series, window=window)
        scores.name = asset
        all_scores = pd.merge(all_scores, scores, left_index=True, right_index=True, how='outer')
    return all_scores

@st.cache_data
def calculate_rsrs_score(df, N=18, M=600):
    """
    Calculate RSRS Z-Score.
    N: Regression Window
    M: Standardization Window
    """
    if 'adj_high' in df.columns and 'adj_low' in df.columns:
        highs = df['adj_high']
        lows = df['adj_low']
    elif 'high' in df.columns and 'low' in df.columns:
        highs = df['high']
        lows = df['low']
    else:
        return None
        
    values_high = highs.values
    values_low = lows.values
    
    beta_series = np.full(len(df), np.nan)
    
    # Calculate Betas (Rolling Regression)
    # We only need the last beta if M is large, but to calculate Z-Score we need M betas.
    # So we need to calculate at least M+N betas back.
    # For efficiency, if len(df) is huge, we can trim? No, cache handles it.
    
    for i in range(N, len(df) + 1):
        y = values_high[i-N:i]
        x = values_low[i-N:i]
        
        # Simple check for NaNs
        if np.isnan(x).any() or np.isnan(y).any():
            continue
            
        try:
            # Using numpy polyfit is faster than statsmodels for simple linear regression
            coeffs = np.polyfit(x, y, 1)
            beta = coeffs[0]
            beta_series[i-1] = beta
        except:
            pass
            
    # Calculate Z-Score
    betas = pd.Series(beta_series, index=df.index)
    mean_beta = betas.rolling(M).mean()
    std_beta = betas.rolling(M).std()
    z_score = (betas - mean_beta) / std_beta
    
    return z_score

@st.cache_data
def precalculate_all_rsrs(history_data):
    all_rsrs = pd.DataFrame()
    for asset, df in history_data.items():
        rsrs = calculate_rsrs_score(df)
        if rsrs is not None:
            rsrs.name = asset
            all_rsrs = pd.merge(all_rsrs, rsrs, left_index=True, right_index=True, how='outer')
    return all_rsrs

# --- Alpha Factors ---

@st.cache_data
def calculate_alpha51(df, window=10, threshold=0.01):
    """
    Alpha 51: Trend Deceleration Identification Factor
    Generalized: If (Prev_10d_Return - Curr_10d_Return) < -Threshold, Signal=1 (Risk).
    This means Current Rally is WEAKER than Previous Rally by 'Threshold'.
    """
    # Use adjusted close if available
    if 'adj_close' in df.columns:
        c = df['adj_close']
    else:
        c = df['close']
        
    w = window
    
    # Part 1: Previous Rally Speed (Price[t-2w] to Price[t-w])
    # Note: Using (New - Old) / w for positive speed
    speed_prev = (c.shift(w) - c.shift(2*w)) / w
    
    # Part 2: Current Rally Speed (Price[t-w] to Price[t])
    speed_curr = (c - c.shift(w)) / w
    
    # Diff = Speed_Curr - Speed_Prev
    # If Diff < -Threshold, it means Speed_Curr is significantly less than Speed_Prev -> Deceleration
    diff = speed_curr - speed_prev
    
    cond = diff < -threshold
    
    # Return boolean series (True = Risk/Signal)
    return cond

@st.cache_data
def precalculate_alpha51_all(history_data, window=10, threshold=0.01):
    all_a51 = pd.DataFrame()
    for asset, df in history_data.items():
        # Returns boolean Series
        a51 = calculate_alpha51(df, window, threshold)
        a51.name = asset
        all_a51 = pd.merge(all_a51, a51, left_index=True, right_index=True, how='outer')
    return all_a51

@st.cache_data
def calculate_alpha55(history_data):
    """
    Alpha 55: Price-Volume Relation Factor
    Formula: -1 * correlation(rank((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12))), rank(volume), 6)
    Note: Requires cross-sectional ranking across all assets.
    """
    # 1. Prepare DataFrames for Close, High, Low, Volume
    closes = pd.DataFrame()
    highs = pd.DataFrame()
    lows = pd.DataFrame()
    volumes = pd.DataFrame()
    
    for asset, df in history_data.items():
        # Prefer adjusted for price, but volume is usually raw (or adjusted volume)
        # Tushare 'vol' is volume.
        
        if 'adj_close' in df.columns: c = df['adj_close']
        else: c = df['close']
            
        if 'adj_high' in df.columns: h = df['adj_high']
        else: h = df['high']
            
        if 'adj_low' in df.columns: l = df['adj_low']
        else: l = df['low']
        
        if 'vol' in df.columns: v = df['vol']
        elif 'volume' in df.columns: v = df['volume']
        else: v = pd.Series(np.nan, index=df.index)
            
        c.name = asset
        h.name = asset
        l.name = asset
        v.name = asset
        
        closes = pd.merge(closes, c, left_index=True, right_index=True, how='outer')
        highs = pd.merge(highs, h, left_index=True, right_index=True, how='outer')
        lows = pd.merge(lows, l, left_index=True, right_index=True, how='outer')
        volumes = pd.merge(volumes, v, left_index=True, right_index=True, how='outer')
        
    # 2. Calculate K term
    # (close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12))
    
    ll12 = lows.rolling(12).min()
    hh12 = highs.rolling(12).max()
    
    denom = hh12 - ll12
    # Avoid division by zero
    denom = denom.replace(0, np.nan)
    
    K = (closes - ll12) / denom
    
    # 3. Rank K (Cross-sectional)
    # axis=1 means rank across columns (assets) for each row (date)
    # pct=True to normalize to 0-1
    rank_K = K.rank(axis=1, pct=True)
    
    # 4. Rank Volume (Cross-sectional)
    rank_V = volumes.rank(axis=1, pct=True)
    
    # 5. Rolling Correlation (Time-series)
    # correlation(rank_K, rank_V, 6)
    # For each asset (column), calculate rolling corr of its rank series
    
    alpha55 = rank_K.rolling(6).corr(rank_V)
    
    # Multiply by -1
    alpha55 = alpha55 * -1
    
    return alpha55

@st.cache_data
def precalculate_alpha51_all(history_data, window=10, threshold=0.01):
    all_a51 = pd.DataFrame()
    for asset, df in history_data.items():
        # Returns boolean Series
        a51 = calculate_alpha51(df, window, threshold)
        a51.name = asset
        all_a51 = pd.merge(all_a51, a51, left_index=True, right_index=True, how='outer')
    return all_a51

# --- 2. Backtest Logic ---

def run_backtest(history_data, raw_scores_df, params, alpha51_df=None):
    """
    params: {
        'start_date': datetime,
        'end_date': datetime,
        'cutoff_score': float,
        'buffer_score': float,
        'fee_rate': float,
        'initial_capital': float,
        'crash_filter_enabled': bool,
        'crash_window': int,
        'crash_threshold': float,
        'exclude_overheated_from_norm': bool,
        'use_alpha51': bool
    }
    """
    # Apply user-selected universe (if provided) to keep pool consistent across history/prices/scores.
    selected_assets = params.get('selected_assets', None)
    if selected_assets:
        history_data = filter_history_data(history_data, selected_assets)
        keep_cols = [c for c in raw_scores_df.columns if c in set(selected_assets)]
        raw_scores_df = raw_scores_df[keep_cols] if keep_cols else raw_scores_df.iloc[:, 0:0]
        if alpha51_df is not None:
            keep_a51_cols = [c for c in alpha51_df.columns if c in set(selected_assets)]
            alpha51_df = alpha51_df[keep_a51_cols] if keep_a51_cols else alpha51_df.iloc[:, 0:0]

    # Filter Timeline
    timeline = [d for d in raw_scores_df.index if params['start_date'] <= d <= params['end_date']]
    timeline = sorted(timeline)
    
    if not timeline:
        return None, None, None, None # Return 4 values now

    # State
    cash = params['initial_capital']
    holdings = {} # {asset: shares}
    current_asset = '现金'
    target_asset = '现金' # Signal from yesterday
    
    # Cache Prices & Returns for Speed (Use Adjusted if available for Backtest to avoid Split Crashes)
    # Note: Using Adjusted prices for backtest execution preserves % returns but "Price" in logs will be adjusted.
    price_open = {}
    price_close = {}
    price_high = {}
    price_low = {}
    
    for asset, df in history_data.items():
        if 'adj_open' in df.columns and 'adj_close' in df.columns:
            price_open[asset] = df['adj_open']
            price_close[asset] = df['adj_close']
            price_high[asset] = df['adj_high'] if 'adj_high' in df.columns else df['high']
            price_low[asset] = df['adj_low'] if 'adj_low' in df.columns else df['low']
        else:
            price_open[asset] = df['open']
            price_close[asset] = df['close']
            price_high[asset] = df['high']
            price_low[asset] = df['low']
    
    daily_returns = {}
    if params['crash_filter_enabled']:
        for asset, df in history_data.items():
            # Use same price series as execution
            if asset in price_close:
                 daily_returns[asset] = price_close[asset].pct_change()
    
    value_history = []
    trade_log = []
    
    last_signal_info = {} # To store the final T+1 signal
    
    cost_basis = {} # {asset: price_per_share}

    for date in timeline:
        # --- A. Execution (At Open) ---
        can_sell = True
        can_buy = True
        
        # Check tradability
        if current_asset != '现金':
            if date not in price_open[current_asset].index: can_sell = False
        if target_asset != '现金':
            if date not in price_open[target_asset].index: can_buy = False
            
        # Calculate NAV at Open for logging (before any trade)
        nav_open = cash
        if current_asset != '现金' and current_asset in holdings:
             # If we can't get open price, use last close or just skip (but we only log if we trade)
             if date in price_open[current_asset].index:
                 nav_open += holdings[current_asset] * price_open[current_asset].loc[date]
        
        cum_ret_pct = (nav_open / params['initial_capital']) - 1

        # Sell
        if current_asset != target_asset and current_asset != '现金' and can_sell:
            price = price_open[current_asset].loc[date]
            shares = holdings[current_asset]
            proceeds = shares * price * (1 - params['fee_rate'])
            cash += proceeds
            del holdings[current_asset]
            
            # Calculate trade return
            trade_return_pct = 0.0
            pnl_amount = 0.0
            
            if current_asset in cost_basis:
                avg_buy_cost = cost_basis[current_asset]
                if avg_buy_cost > 0:
                    # Trade Return % (based on price movement, rough approx or exact?)
                    # Let's use money-weighted: (Proceeds - Cost) / Cost
                    total_buy_cost = shares * avg_buy_cost
                    pnl_amount = proceeds - total_buy_cost
                    trade_return_pct = pnl_amount / total_buy_cost
                del cost_basis[current_asset]
            
            trade_log.append({
                'date': date,
                'action': '卖出',
                'asset': current_asset,
                'price': price,
                'shares': shares,
                'amount': proceeds,
                'fee': shares * price * params['fee_rate'],
                'return_pct': cum_ret_pct,
                'trade_return': trade_return_pct,
                'pnl_amount': pnl_amount
            })
            current_asset = '现金'
            
        # Buy
        if current_asset == '现金' and target_asset != '现金' and can_buy:
            price = price_open[target_asset].loc[date]
            invest_amount = cash
            shares = invest_amount / (price * (1 + params['fee_rate']))
            cost = shares * price * (1 + params['fee_rate'])
            cash -= cost
            holdings[target_asset] = shares
            
            # Record average cost per share (including fee) for PnL calculation
            cost_basis[target_asset] = cost / shares
            
            trade_log.append({
                'date': date,
                'action': '买入',
                'asset': target_asset,
                'price': price,
                'shares': shares,
                'amount': cost,
                'fee': shares * price * params['fee_rate'],
                'return_pct': cum_ret_pct,
                'trade_return': np.nan,
                'pnl_amount': np.nan
            })
            current_asset = target_asset
            
        # --- B. Valuation (At Close) ---
        day_value = cash
        day_high = cash
        day_low = cash
        
        for asset, shares in holdings.items():
            # Close
            if date in price_close[asset].index:
                price = price_close[asset].loc[date]
            else:
                try:
                    price = price_close[asset].asof(date)
                except:
                    price = 0
            day_value += shares * price
            
            # High
            if date in price_high[asset].index:
                ph = price_high[asset].loc[date]
            else:
                try: ph = price_high[asset].asof(date)
                except: ph = 0
            day_high += shares * ph
            
            # Low
            if date in price_low[asset].index:
                pl = price_low[asset].loc[date]
            else:
                try: pl = price_low[asset].asof(date)
                except: pl = 0
            day_low += shares * pl
            
        value_history.append({
            'date': date, 
            'value': day_value, 
            'high': day_high,
            'low': day_low,
            'holding': current_asset
        })
        
        # --- C. Signal Generation (At Close) ---
        if date not in raw_scores_df.index:
            next_target = '现金'
        else:
            today_scores = raw_scores_df.loc[date].dropna()
            
            if today_scores.empty:
                next_target = '现金'
            else:
                # 1. Apply Crash Filter (If Enabled)
                valid_assets_pool = today_scores.index.tolist()
                
                if params['crash_filter_enabled']:
                    valid_after_crash = []
                    for asset in valid_assets_pool:
                        is_crashed = False
                        if asset in daily_returns:
                            try:
                                # Get recent returns ending today
                                # Need location
                                if date in daily_returns[asset].index:
                                    idx = daily_returns[asset].index.get_loc(date)
                                    start_idx = max(0, idx - params['crash_window'] + 1)
                                    recent_rets = daily_returns[asset].iloc[start_idx : idx+1]
                                    
                                    # Check threshold (positive value in params, check against negative return)
                                    if recent_rets.min() < -params['crash_threshold']:
                                        is_crashed = True
                            except:
                                pass
                        
                        if not is_crashed:
                            valid_after_crash.append(asset)
                    
                    valid_assets_pool = valid_after_crash
                
                # 1.5 Apply Alpha 51 Filter (If Enabled)
                # If Alpha 51 signal is True (Risk), exclude from pool.
                if params.get('use_alpha51', False) and alpha51_df is not None:
                    valid_after_a51 = []
                    # Check if date exists in alpha51_df
                    if date in alpha51_df.index:
                        a51_today = alpha51_df.loc[date]
                        for asset in valid_assets_pool:
                            # Check risk signal
                            is_risk = False
                            if asset in a51_today and a51_today[asset] == True:
                                is_risk = True
                            
                            if not is_risk:
                                valid_after_a51.append(asset)
                    else:
                        # If no alpha data, keep as is (or strict mode?)
                        # Keep as is for now
                        valid_after_a51 = valid_assets_pool
                    
                    valid_assets_pool = valid_after_a51
                
                # Filter scores to valid pool
                pool_scores = today_scores[today_scores.index.isin(valid_assets_pool)]
                
                if pool_scores.empty:
                    next_target = '现金'
                else:
                    # 2. Filter Candidates (Score > 0 & <= Cutoff)
                    # Use Asset-Specific Cutoff
                    
                    # We need to map asset name to code again to lookup config
                    name_to_code = {
                        '日经ETF': '513520.SH', '纳指ETF': '513100.SH', '港股科技ETF': '513020.SH', 
                        '港股科技': '513020.SH', '纳指100': '513100.SH',
                        '180ETF': '510180.SH', '上证180': '510180.SH',
                        '科创板ETF': '588120.SH', '科创板': '588120.SH',
                        '创业板ETF': '159915.SZ', '创业板': '159915.SZ',
                        '南方原油(LOF)': '501018.SH', '南方原油': '501018.SH',
                        '黄金ETF': '518880.SH', 
                        '30年国债ETF': '511090.SH', '30年国债': '511090.SH'
                    }
                    
                    def get_cutoff(asset_name):
                        code = name_to_code.get(asset_name)
                        if code and code in params['user_cutoffs']:
                            return params['user_cutoffs'][code]
                        return 300 # Fallback default
                        
                    # Vectorized cutoff check? Hard with dict lookup. Loop is easier for candidates.
                    # Or apply map to index
                    
                    current_cutoffs = pd.Series(pool_scores.index.map(get_cutoff), index=pool_scores.index)
                    
                    valid_candidates = pool_scores[
                        (pool_scores <= current_cutoffs) & (pool_scores > 0)
                    ]
                    
                    if valid_candidates.empty:
                        next_target = '现金'
                    else:
                        # 3. Normalize Valid Scores (Relative to Pool)
                        # Check normalization mode
                        exclude_overheated = params.get('exclude_overheated_from_norm', False)
                        
                        if exclude_overheated:
                            # Use only valid candidates (which are already filtered by cutoff) for normalization range
                            norm_basis = valid_candidates
                        else:
                            # Use entire pool (including overheated)
                            norm_basis = pool_scores
                            
                        vals = norm_basis.values
                        mn, mx = np.min(vals), np.max(vals)
                        
                        if mx == mn:
                            norm_scores = pd.Series(50, index=pool_scores.index)
                        else:
                            # Normalize all scores based on the chosen range
                            norm_scores = (pool_scores - mn) / (mx - mn) * 100
                            
                        # Best Valid Asset
                        best_valid_asset = valid_candidates.idxmax()
                        best_valid_norm = norm_scores[best_valid_asset]
                        
                        # 4. Switching Logic
                        if current_asset not in valid_candidates.index:
                            # Current is invalid (crashed, score too low, or score too high) -> Switch
                            next_target = best_valid_asset
                        else:
                            # Current is valid -> Check Buffer
                            curr_norm = norm_scores[current_asset]
                            
                            # Buffer: New - Current > Threshold
                            if best_valid_norm - curr_norm > params['buffer_score']:
                                next_target = best_valid_asset
                            else:
                                next_target = current_asset
                            
        target_asset = next_target
        
        # Capture last signal info
        if date == timeline[-1]:
            last_signal_info = {
                'date': date,
                'next_holding': target_asset,
                'score': pool_scores.get(target_asset, 0) if target_asset != '现金' else 0
            }
        
    return pd.DataFrame(value_history).set_index('date'), pd.DataFrame(trade_log), timeline, last_signal_info

# --- 3. UI Layout ---

def plot_asset_trades(asset_name, df_ohlc, trades, start_date, end_date):
    """
    Generate Close Price chart with Buy/Sell markers.
    """
    # Filter OHLC by date range
    mask = (df_ohlc.index >= pd.Timestamp(start_date)) & (df_ohlc.index <= pd.Timestamp(end_date))
    chart_data = df_ohlc.loc[mask]
    
    if chart_data.empty:
        return None

    # Determine which columns to use (match backtest logic preference for Adjusted)
    if 'adj_close' in chart_data.columns:
        c = chart_data['adj_close']
        price_type = "(后复权)"
    else:
        c = chart_data['close']
        price_type = "(未复权)"

    # Line Chart
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=chart_data.index,
        y=c,
        mode='lines',
        name=f'收盘价 {price_type}',
        line=dict(color='#1f77b4', width=2)
    ))

    # Buy Markers
    buy_trades = trades[trades['action'] == '买入']
    if not buy_trades.empty:
        fig.add_trace(go.Scatter(
            x=buy_trades['date'],
            y=buy_trades['price'],
            mode='markers',
            marker=dict(symbol='triangle-up', size=12, color='red', line=dict(width=1, color='black')),
            name='买入点',
            hovertext=buy_trades['price'].apply(lambda x: f"买入价: {x:.3f}")
        ))

    # Sell Markers
    sell_trades = trades[trades['action'] == '卖出']
    if not sell_trades.empty:
        hover_texts = []
        for _, row in sell_trades.iterrows():
            ret_str = f"{row['trade_return']:.2%}" if pd.notnull(row['trade_return']) else "N/A"
            pnl_str = f"{row['pnl_amount']:.2f}" if pd.notnull(row['pnl_amount']) else "N/A"
            hover_texts.append(f"卖出价: {row['price']:.3f}<br>本次收益率: {ret_str}<br>本次盈亏额: {pnl_str}")
            
        fig.add_trace(go.Scatter(
            x=sell_trades['date'],
            y=sell_trades['price'], 
            mode='markers',
            marker=dict(symbol='triangle-down', size=12, color='green', line=dict(width=1, color='black')),
            name='卖出点',
            hovertext=hover_texts
        ))

    fig.update_layout(
        title=f"{asset_name} 交易复盘 {price_type}",
        xaxis_title="日期",
        yaxis_title="价格",
        height=500,
        hovermode="closest"
    )
    return fig

def render_intro_page():
    st.title("📚 策略原理与交易者指南")
    
    st.markdown("""
    ### 1. 核心设计理念
    本策略是一个**基于动量的轮动策略**，旨在通过数学模型自动捕捉市场中趋势最强的资产，同时通过严格的风险控制机制避免由于市场过热或突发暴跌带来的损失。
    
    ### 2. 数据来源与处理
    - **数据源**: 策略使用 **Tushare Pro** 接口获取 ETF 的日线数据。
    - **复权处理**: 计算收益率时使用**后复权 (Adj Close)** 数据，以保证价格的连续性和收益计算的准确性。
    
    ### 3. 策略标的池详情
    本策略精选了 9 只具有代表性的 ETF，覆盖了不同的市场和资产类别，以实现低相关性的多元化配置。
    
    | 代码 | 名称 | 资产类别 | 典型特征 |
    | :--- | :--- | :--- | :--- |
    | **513100.SH** | 纳指ETF | 🇺🇸 美股科技 | 全球科技龙头，高成长高波动 |
    | **513520.SH** | 日经ETF | 🇯🇵 日本股市 | 亚洲发达市场，与A股相关性低 |
    | **513020.SH** | 港股科技ETF | 🇭🇰 港股科技 | 中国互联网巨头，估值弹性大 |
    | **510180.SH** | 180ETF | 🇨🇳 A股蓝筹 | 上海市场核心资产，金融地产占比高 |
    | **588120.SH** | 科创板ETF | 🇨🇳 A股硬科技 | 半导体、生物医药等硬核科技 |
    | **159915.SZ** | 创业板ETF | 🇨🇳 A股成长 | 新能源、医药等成长风格 |
    | **501018.SH** | 南方原油 | 🛢️ 商品原油 | 抗通胀，与股市相关性低 |
    | **518880.SH** | 黄金ETF | 🥇 商品黄金 | 避险资产，对抗货币贬值 |
    | **511090.SH** | 30年国债ETF | 🇨🇳 债券 | 防御性资产，股市下跌时的避风港 |
    
    ### 4. 核心因子：二次加权线性回归动量
    为了更精准地识别趋势，我们采用了**二次加权线性回归 (Quadratic Weighted Linear Regression)** 模型，而非简单的收益率排名。
    
    #### 计算公式
    $$
    Score = (e^{Slope \\times 252} - 1) \\times R^2 \\times 100
    $$
    
    其中：
    - **Slope (斜率)**: 通过对过去 20 天的对数价格进行加权线性回归得出，代表资产的**上涨速度**。
    - **R² (拟合优度)**: 代表价格走势的**平稳度**。$R^2$ 越接近 1，说明价格上涨越平稳，回撤越小。
    - **权重 ($w_t$)**: $w_t = 1 + (t/T)^2$，赋予最近的交易日更高的权重，使模型对趋势变化更敏感。
    
    > **核心逻辑**: 我们不仅追求“涨得快”（Slope），更追求“涨得稳”（$R^2$）。一个波动剧烈的大涨不如一个稳步向上的小涨得分高。
    
    ### 5. 关键参数解析
    
    #### (a) 动量窗口 (20天)
    - **设定**: 采用 20 个交易日（约一个月）作为动量计算窗口。
    - **原因**: 经测试，20天是捕捉中短期趋势的最佳平衡点。太短（如5-10天）容易被市场噪音干扰；太长（如60天）则对趋势反转反应迟钝。
    
    #### (b) 过热熔断阈值 (Score > 300)
    - **设定**: 当动量得分超过 300 分时，禁止开仓该标的，甚至强制卖出。
    - **深度分析**: 
        - 统计发现，得分与未来收益呈**倒 U 型曲线**关系。
        - 当得分适中（50-200）时，动量效应显著，未来大概率继续上涨。
        - 当得分极端高（>300）时，往往意味着资产价格呈指数级爆发（如年化收益率推算超过几百%），这种状态不可持续，极易发生均值回归或崩盘。
        - **结论**: 300分是“贪婪”与“危险”的分界线。
    
    #### (c) 换仓缓冲阈值 (Score Diff > 8)
    - **设定**: 只有当新标的的归一化得分比当前持仓标的高出 8 分以上时，才进行调仓。
    - **原因**: 避免“反复横跳”。如果两个标的得分相近，频繁切换只会徒增交易成本和滑点。8分的缓冲带确保了只有确定的“更强趋势”出现时才行动。
    
    ### 6. 风控机制：短期大跌剔除
    - **逻辑**: 如果某标的在最近 3 天内出现单日跌幅超过 3% 的情况，立即将其从候选池中剔除。
    - **目的**: “君子不立危墙之下”。在暴跌初期果断离场，规避可能发生的连续下跌风险。

    ### 7. 辅助分析工具：动量得分分布与预期收益分析
    我们提供了一个独立的分析工具，用于深入研究“动量得分”与“未来收益”之间的非线性关系（即倒 U 型曲线）。

    - **访问方式**: 请点击左侧侧边栏的 **"Momentum Analysis"** 页面。
    - **功能**: 
        - 可视化不同得分区间的未来收益分布。
        - 验证“过热熔断”阈值（300分）的合理性。

    ### 8. 参数统计与稳定性分析
    我们对策略参数进行了全量的网格搜索与统计分析，以验证策略的稳健性。

    - **访问方式**: 请点击左侧侧边栏的 **"Parameter Analysis"** 页面。
    - **核心结论**: 
        - 验证了参数平原的存在，排除了过拟合风险。
        - 确定了 **Window=25** 为策略还原的基石。
    """)

def get_strategy_params():
    """
    Render sidebar strategy controls and return params dict.
    """
    st.sidebar.header("⚙️ 策略参数设置")
    
    # Data Update Section
    st.sidebar.divider()
    st.sidebar.subheader("📥 数据更新")
    
    ts_token = get_tushare_token()
        
    # Allow manual override
    manual_token = st.sidebar.text_input("Tushare Token (可选)", value="", type="password", help="如果自动获取失败，请在此手动输入 Token")
    if manual_token:
        ts_token = manual_token
        st.session_state['tushare_token'] = manual_token
    
    if st.sidebar.button("🔄 更新数据"):
        # Add a force update checkbox logic or just detect if user wants to force?
        # Since button is stateless, we can add a checkbox before it.
        pass # Logic moved below

    force_update = st.sidebar.checkbox("强制全量更新 (修复数据分裂/缺失)", value=False, help="勾选后将删除现有数据并重新下载所有历史数据。如果发现价格图表有异常缺口，请使用此功能。")
    
    if st.sidebar.button("🔄 执行更新"):
        with st.spinner("正在连接 Tushare 更新数据..."):
            if update_data(ts_token, force=force_update):
                st.success("数据更新成功！请刷新页面或重新回测。")
                # Clear cache to force reload
                load_history_data.clear()
                precalculate_all_scores.clear()
                precalculate_all_rsrs.clear()
                precalculate_alpha51_all.clear()
                st.rerun()
    
    st.sidebar.divider()
    
    # Date Range (Only needed for backtest range, but useful to keep here or default)
    # For simplicity, we keep them here but Latest Holding might ignore start/end
    min_date = pd.Timestamp('2017-08-01')
    max_date = pd.Timestamp.now()
    
    st.sidebar.subheader("📅 回测时间设置")
    time_range_option = st.sidebar.radio(
        "选择回测时长",
        ("最近1年", "最近2年", "最近3年", "最近4年", "最近5年", "自定义时间范围"),
        index=0
    )

    if time_range_option == "自定义时间范围":
        start_date = st.sidebar.date_input("开始日期", min_date, min_value=min_date, max_value=max_date)
        end_date = st.sidebar.date_input("结束日期", max_date, min_value=min_date, max_value=max_date)
        start_date = pd.Timestamp(start_date)
        end_date = pd.Timestamp(end_date)
    else:
        # Calculate start date based on selection
        end_date = pd.Timestamp.now()
        years_map = {
            "最近1年": 1,
            "最近2年": 2,
            "最近3年": 3,
            "最近4年": 4,
            "最近5年": 5
        }
        years_back = years_map[time_range_option]
        start_date = end_date - pd.DateOffset(years=years_back)
        
        # If calculated start date is before min_date, clamp it
        if start_date < min_date:
            start_date = min_date
            
        # Display the calculated range for info
        st.sidebar.caption(f"范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
    
    # Strategy Params
    st.sidebar.subheader("核心参数")
    
    window = st.sidebar.number_input("动量窗口 (天)", min_value=5, max_value=60, value=20, step=1)

    # Universe selection
    st.sidebar.subheader("标的池")
    code_to_name_all = {
        '588120.SH': '科创板',
        '513100.SH': '纳指100',
        '513520.SH': '日经ETF',
        '159915.SZ': '创业板',
        '513020.SH': '港股科技',
        '510180.SH': '上证180',
        '518880.SH': '黄金ETF',
        '501018.SH': '南方原油',
        '511090.SH': '30年国债'
    }
    universe_all = list(code_to_name_all.values())
    selected_assets = st.sidebar.multiselect(
        "参与轮动的标的",
        options=universe_all,
        default=universe_all,
        help="未勾选的标的不会参与动量评分、过滤、归一化与换仓决策。"
    )
    
    # Custom Cutoff Logic
    st.sidebar.markdown("**过热熔断阈值设置**")
    
    cutoff_mode = st.sidebar.radio(
        "阈值模式", 
        ["分标的独立设置", "全局统一设置"],
        index=1,
        help="选择'全局统一'将对所有标的使用相同阈值；选择'分标的独立'可为不同波动率的资产设置不同阈值。"
    )
    
    user_cutoffs = {}
    
    # Map code to friendly name for display
    code_to_name = {code: name for code, name in code_to_name_all.items() if name in set(selected_assets)}

    if cutoff_mode == "全局统一设置":
        global_cutoff = st.sidebar.number_input("全局熔断阈值", min_value=50, max_value=2000, value=600, step=50)
        for code in code_to_name.keys():
            user_cutoffs[code] = global_cutoff
    else:
        # Default initial values based on statistical analysis
        default_cutoffs = {
            '588120.SH': 500,  # 科创板
            '513100.SH': 600,  # 纳指100
            '513520.SH': 300,  # 日经ETF
            '159915.SZ': 1000, # 创业板
            '513020.SH': 400,  # 港股科技
            '510180.SH': 600,  # 上证180
            '518880.SH': 500,  # 黄金ETF
            '501018.SH': 1000, # 南方原油
            '511090.SH': 300,  # 30年国债
        }
        
        with st.sidebar.expander("自定义各标的阈值", expanded=True):
            for code, name in code_to_name.items():
                default_val = default_cutoffs.get(code, 300)
                val = st.number_input(f"{name} ({code})", min_value=50, max_value=2000, value=default_val, step=50)
                user_cutoffs[code] = val
            
    buffer_score = st.sidebar.number_input("换仓缓冲阈值 (分差)", min_value=0.0, max_value=50.0, value=5.0, step=0.5)
    
    exclude_overheated_from_norm = st.sidebar.checkbox(
        "归一化时剔除过热标的", 
        value=True,
        help="勾选后，在计算归一化分数时，将先剔除超过熔断阈值的标的，再以剩余标的的最高分作为100分基准。这会放大剩余标的之间的分差，可能增加换仓频率。"
    )
    
    # Crash Filter Params
    st.sidebar.subheader("风控参数")
    crash_filter_enabled = st.sidebar.checkbox("启用短期暴跌剔除", value=False)
    if crash_filter_enabled:
        crash_window = st.sidebar.number_input("暴跌监测窗口 (天)", min_value=1, max_value=10, value=3)
        crash_threshold = st.sidebar.number_input("单日跌幅阈值 (%)", min_value=1.0, max_value=20.0, value=3.0, step=0.5) / 100
    else:
        crash_window = 3
        crash_threshold = 0.03
    
    # Execution Params
    st.sidebar.subheader("交易参数")
    fee_rate = st.sidebar.number_input("交易费率 (%)", min_value=0.0, max_value=1.0, value=0.05, step=0.01) / 100
    initial_capital = st.sidebar.number_input("初始资金", min_value=10000, value=100000, step=10000)
    
    # Alpha Factors
    st.sidebar.subheader("Alpha 因子增强")
    use_alpha51 = st.sidebar.checkbox("启用 Alpha 51 (趋势减速识别)", value=False, help="如果启用，当识别到标的上涨趋势明显减速时（涨速差 > 1%），将禁止开仓或强制平仓。")
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'window': window,
        'selected_assets': selected_assets,
        'user_cutoffs': user_cutoffs,
        'buffer_score': buffer_score,
        'exclude_overheated_from_norm': exclude_overheated_from_norm,
        'fee_rate': fee_rate,
        'initial_capital': initial_capital,
        'crash_filter_enabled': crash_filter_enabled,
        'crash_window': crash_window,
        'crash_threshold': crash_threshold,
        'use_alpha51': use_alpha51
    }

def render_latest_holding_page():
    st.title("🔔 最新持仓信号")
    
    # Hidden Link Button
    st.markdown("""
    <style>
    .stButton button {
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)
    
    col_a, col_b = st.columns([0.8, 0.2])
    with col_b:
        # Use a generic label and open in new tab via JS to "hide" URL in status bar partially
        # But Streamlit link_button shows URL. 
        # To truly hide, we can use a small hack or just a generic link text.
        # "External Resource"
        st.link_button("🌐 外部数据源", "https://168.nbjiadao.com/")
    
    # Sidebar
    params = get_strategy_params()

    if not params.get('selected_assets'):
        st.warning("请至少选择一个参与轮动的标的。")
        return
    
    st.info("点击下方按钮，系统将获取最新数据，并根据当前策略参数计算下一个交易日的建议持仓。")
    
    if st.button("🔍 检查并获取最新信号", type="primary"):
        # 1. Update Data
        ts_token = get_tushare_token()
        
        with st.spinner("正在同步最新市场数据..."):
            # Default to incremental update for "Latest Holding" check
            update_data(ts_token, force=False)
            load_history_data.clear()
            precalculate_all_scores.clear()
            precalculate_all_rsrs.clear()
            precalculate_alpha51_all.clear()
            
        # 2. Load & Calc
        with st.spinner("正在计算策略信号..."):
            history_data = filter_history_data(load_history_data(), params.get('selected_assets'))
            scores_df = precalculate_all_scores(history_data, window=params['window'])
            rsrs_df = precalculate_all_rsrs(history_data)
            
            # Alpha 51
            if params.get('use_alpha51', False):
                alpha51_df = precalculate_alpha51_all(history_data, window=10, threshold=0.01)
            else:
                alpha51_df = None
            
            # 3. Run Backtest to determine state
            # We run from a reasonable past date to ensure state is correct
            # Start from 2024-01-01 or params['start_date']? 
            # Use params['start_date'] to be consistent with backtest settings
            backtest_params = params.copy()
            backtest_params['end_date'] = pd.Timestamp.now() # Ensure we go up to today
            
            df_res, df_trades, timeline, last_signal = run_backtest(history_data, scores_df, backtest_params, alpha51_df)
            
            if not timeline:
                st.error("无法计算信号，请检查数据或日期范围。")
                return

            # 4. Display Result
            latest_date = timeline[-1].strftime('%Y-%m-%d')
            next_holding = last_signal.get('next_holding', '现金')
            next_score = last_signal.get('score', 0)
            
            st.divider()
            st.markdown(f"### 📅 数据日期: {latest_date}")
            
            # Big Display
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 建议持仓 (T+1)")
                if next_holding == '现金':
                    st.warning(f"### 💵 {next_holding}")
                else:
                    st.success(f"### 🚀 {next_holding}")
            
            with col2:
                st.markdown("#### 动量得分")
                st.metric("Score", f"{next_score:.1f}")
                
            st.divider()
            
            # Show details of candidates
            st.markdown("#### 📊 当日标的得分详情")
            
            if latest_date in scores_df.index:
                today_scores = scores_df.loc[latest_date].dropna().sort_values(ascending=False)
                
                # Format for display
                details = []
                for asset, score in today_scores.items():
                    # Get cutoff for this asset
                    cutoff = 300
                    if 'user_cutoffs' in params:
                        # Need to find code
                        # name_to_code is local in backtest func, recreate or use simple lookup
                        # We don't have code here easily without re-mapping.
                        # Let's just do a quick lookup
                        pass # Cutoff might be slightly off in display if we don't map, but acceptable for now or fix properly.
                        
                    # Re-map for accurate cutoff display
                    name_to_code_disp = {
                        '日经ETF': '513520.SH', '纳指ETF': '513100.SH', '港股科技ETF': '513020.SH', 
                        '港股科技': '513020.SH', '纳指100': '513100.SH',
                        '180ETF': '510180.SH', '上证180': '510180.SH',
                        '科创板ETF': '588120.SH', '科创板': '588120.SH',
                        '创业板ETF': '159915.SZ', '创业板': '159915.SZ',
                        '南方原油(LOF)': '501018.SH', '南方原油': '501018.SH',
                        '黄金ETF': '518880.SH', 
                        '30年国债ETF': '511090.SH', '30年国债': '511090.SH'
                    }
                    
                    cutoff_val = 300
                    asset_code = name_to_code_disp.get(asset)
                    if asset_code and 'user_cutoffs' in params and asset_code in params['user_cutoffs']:
                        cutoff_val = params['user_cutoffs'][asset_code]
                        
                    status = "✅ 候选"
                    if score > cutoff_val:
                        status = f"🚫 过热 (>{cutoff_val})"
                    elif score <= 0:
                        status = "📉 负动量"
                        
                    # Get RSRS
                    rsrs_val = np.nan
                    if latest_date in rsrs_df.index and asset in rsrs_df.columns:
                        rsrs_val = rsrs_df.loc[latest_date, asset]
                        
                    rsrs_str = f"{rsrs_val:.2f}" if not np.isnan(rsrs_val) else "-"
                    
                    # RSRS Status
                    rsrs_status = ""
                    if not np.isnan(rsrs_val):
                        if rsrs_val > 0.7:
                            rsrs_status = "🔥 强势"
                        elif rsrs_val < -0.7:
                            rsrs_status = "🧊 弱势"
                        else:
                            rsrs_status = "↔️ 震荡"
                        
                    details.append({
                        '标的': asset,
                        '动量得分': f"{score:.1f}",
                        'RSRS指标': f"{rsrs_str} {rsrs_status}",
                        '熔断阈值': cutoff_val,
                        '状态': status
                    })
                
                st.dataframe(pd.DataFrame(details))

def calculate_thermometer(df):
    """
    Calculate Strategy Thermometer Indicator.
    Input df must have 'high', 'low', 'value' (as close) columns.
    """
    # 1. 计算价格源 hlcc4 (Using 'value' as close)
    # Ensure columns exist, 'value' is close
    c = df['value']
    h = df['high']
    l = df['low']
    
    src = (h + l + c * 2) / 4 
    
    # 2. 计算 RSI (采用 RMA 平滑) 
    def rma(series, period): 
        return series.ewm(alpha=1/period, adjust=False).mean() 
    
    delta = src.diff() 
    up = rma(delta.clip(lower=0), 14) 
    down = rma(-delta.clip(upper=0), 14) 
    rsi = 100 - (100 / (1 + up / down)) 
    
    # 3. 计算 TSI (价格与时间的相关系数) 
    # Use integer index for correlation
    # We can create a temporary series
    tsi_window = 14
    
    # Rolling correlation requires Series
    # We correlate src with a rolling window of indices?
    # No, rolling correlation between two series.
    # We need a series that represents time.
    # If df has datetime index, we can't correlate directly with that easily in rolling.
    # Create a 0..N series
    time_idx = pd.Series(np.arange(len(df)), index=df.index)
    
    tsi = src.rolling(window=tsi_window).corr(time_idx)
    tsi_norm = (tsi + 1) / 2 * 100 
    
    # 4. 计算 BB%B (布林带百分比) 
    sma_bb = src.rolling(window=20).mean() 
    std_bb = src.rolling(window=20).std() 
    bb_percent = (src - (sma_bb - 2 * std_bb)) / (4 * std_bb) * 100 
    bb_percent = bb_percent.clip(0, 100) 

    # 5. 最终加权合成 (线性) 
    thermometer = (rsi * 0.45) + (tsi_norm * 0.26) + (bb_percent * 0.29) 
    
    # 6. 3日SMA平滑 
    plot_line = thermometer.rolling(window=3).mean() 
    
    return thermometer, plot_line

def render_backtest_page():
    # Sidebar Controls
    params = get_strategy_params()

    if not params.get('selected_assets'):
        st.warning("请至少选择一个参与轮动的标的。")
        return
    
    # Data Loading
    history_data = filter_history_data(load_history_data(), params.get('selected_assets'))
    
    if st.sidebar.button("🚀 开始回测", type="primary"):
        with st.spinner("正在计算动量得分..."):
            # Pre-calculate scores based on window
            scores_df = precalculate_all_scores(history_data, window=params['window'])
            
            # Alpha 51
            if params.get('use_alpha51', False):
                alpha51_df = precalculate_alpha51_all(history_data, window=10, threshold=0.01)
            else:
                alpha51_df = None
            
        with st.spinner("正在执行回测..."):
            df_res, df_trades, timeline, last_signal = run_backtest(history_data, scores_df, params, alpha51_df)
            
            # Store results in session state
            st.session_state['bt_results'] = {
                'df_res': df_res,
                'df_trades': df_trades,
                'timeline': timeline,
                'last_signal': last_signal,
                'scores_df': scores_df,
                'params': params
            }

    # Check if results exist
    if 'bt_results' in st.session_state:
        res = st.session_state['bt_results']
        df_res = res['df_res']
        df_trades = res['df_trades']
        timeline = res['timeline']
        last_signal = res['last_signal']
        scores_df = res['scores_df']
        run_params = res['params'] # Use the params that were used for this run

        if df_res is None or df_res.empty:
            st.error("该时间段内无数据或回测失败。")
        else:
            # Calculate daily cumulative return
            df_res['cum_return'] = df_res['value'] / run_params['initial_capital'] - 1

            # --- Metrics Calculation ---
            total_ret = df_res['value'].iloc[-1] / df_res['value'].iloc[0] - 1
            days = (df_res.index[-1] - df_res.index[0]).days
            if days > 0:
                ann_ret = (1 + total_ret) ** (365 / days) - 1
            else:
                ann_ret = 0
            
            # Volatility
            daily_ret = df_res['value'].pct_change().dropna()
            vol = daily_ret.std() * np.sqrt(252)
            
            # Sharpe
            risk_free = 0.02
            sharpe = (ann_ret - risk_free) / vol if vol != 0 else 0
            
            # Max Drawdown
            cum_max = df_res['value'].cummax()
            drawdown = (df_res['value'] - cum_max) / cum_max
            max_dd = drawdown.min()
            current_dd = drawdown.iloc[-1]
            
            # --- Display Metrics ---
            st.markdown("### 📊 回测绩效概览")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("总收益率", f"{total_ret:.2%}", delta_color="normal")
            col2.metric("年化收益率", f"{ann_ret:.2%}", delta_color="normal")
            col3.metric("夏普比率", f"{sharpe:.2f}")
            col4.metric("最大回撤", f"{max_dd:.2%}", delta_color="inverse")
            col5.metric("年化波动率", f"{vol:.2%}", delta_color="inverse")
            
            st.divider()

            # --- NEW: Asset Contribution Analysis ---
            st.markdown("### 🧬 各标的贡献分析")
            
            # 1. Holding Days
            # Group by 'holding' column in df_res
            holding_days = df_res.groupby('holding').size()
            
            # 2. PnL & Max Drawdown per Asset
            # PnL from trades
            asset_pnl = df_trades[df_trades['action'] == '卖出'].groupby('asset')['pnl_amount'].sum()
            
            # Max Drawdown Calculation per Asset (Strategy MDD during holding period)
            asset_mdd = {}
            
            # Identify continuous segments for each asset
            # Create a group id that changes when holding changes
            df_res['group'] = (df_res['holding'] != df_res['holding'].shift()).cumsum()
            
            for group_id, group_df in df_res.groupby('group'):
                asset_name = group_df['holding'].iloc[0]
                if asset_name == '现金':
                    continue
                    
                # Calculate MDD for this segment
                # We look at the strategy value curve during this period
                vals = group_df['value']
                # To capture drawdown correctly, we need the peak from the START of this segment
                # But actually, drawdown is usually relative to the running max OF THE SEGMENT?
                # Or relative to the all-time high?
                # "Strategy's Max Drawdown while holding Asset X" usually means 
                # looking at the curve segment and finding the max drop within it.
                # Standard MDD for a series:
                cum_max_segment = vals.cummax()
                dd_segment = (vals - cum_max_segment) / cum_max_segment
                min_dd_segment = dd_segment.min()
                
                if asset_name not in asset_mdd:
                    asset_mdd[asset_name] = min_dd_segment
                else:
                    # Take the worst drawdown across all segments for this asset
                    asset_mdd[asset_name] = min(asset_mdd[asset_name], min_dd_segment)
            
            # Combine into DataFrame
            all_assets_involved = set(holding_days.index) | set(asset_pnl.index)
            # Remove Cash if present
            if '现金' in all_assets_involved:
                all_assets_involved.remove('现金')
                
            contribution_data = []
            for asset in all_assets_involved:
                days = holding_days.get(asset, 0)
                pnl = asset_pnl.get(asset, 0.0)
                mdd = asset_mdd.get(asset, 0.0)
                
                # Contribution to Total Return
                # Use initial capital as base
                contrib_pct = pnl / run_params['initial_capital']
                
                contribution_data.append({
                    '标的': asset,
                    '总持仓天数 (交易日)': days,
                    '持仓占比': days / len(df_res) if len(df_res) > 0 else 0,
                    '贡献收益率': contrib_pct,
                    '期间最大回撤': mdd
                })
                
            if contribution_data:
                df_contrib = pd.DataFrame(contribution_data).sort_values('贡献收益率', ascending=False)
                
                # Formatting
                st.dataframe(
                    df_contrib.style.format({
                        '持仓占比': '{:.1%}',
                        '贡献收益率': '{:.2%}',
                        '期间最大回撤': '{:.2%}'
                    }),
                    use_container_width=True
                )
            else:
                st.info("暂无持仓数据。")
            
            st.divider()
            
            # --- NEW SECTION: Current Status Info ---
            # 1. Data Updated To
            latest_data_date = timeline[-1].strftime('%Y-%m-%d')
            
            # 2. T+1 Holding
            next_holding = last_signal.get('next_holding', '未知')
            next_score = last_signal.get('score', 0)
            
            # Map code if possible
            etf_code_map = {
                '日经ETF': '513520.SH',
                '纳指ETF': '513100.SH',
                '港股科技': '513020.SH', 
                '港股科技ETF': '513020.SH',
                '上证180': '510180.SH',
                '180ETF': '510180.SH',
                '科创板': '588120.SH',
                '科创板ETF': '588120.SH',
                '创业板': '159915.SZ',
                '创业板ETF': '159915.SZ',
                '南方原油': '501018.SH',
                '南方原油(LOF)': '501018.SH',
                '黄金ETF': '518880.SH',
                '30年国债': '511090.SH',
                '30年国债ETF': '511090.SH'
            }
            # Clean name for mapping
            holding_code = etf_code_map.get(next_holding, '')
            if holding_code:
                holding_display = f"{next_holding} ({holding_code})"
            else:
                holding_display = next_holding
            
            # 3. Current Drawdown
            # Calculated above as current_dd
            
            # 4. Other Scores
            # We need scores for the last date in timeline
            other_scores_display = ""
            if latest_data_date in scores_df.index:
                today_scores = scores_df.loc[latest_data_date].dropna().sort_values(ascending=False)
                # Filter out the winner to avoid duplication if desired, or show all
                # Let's show top 5 others
                score_strs = []
                for asset, score in today_scores.items():
                    if asset != next_holding:
                        score_strs.append(f"{asset}: {score:.1f}")
                
                if score_strs:
                    other_scores_display = " | ".join(score_strs)
            
            st.info(f"""
            **📅 策略状态面板**  
            **数据更新至**: {latest_data_date}  
            **T+1 建议持仓**: **{holding_display}** (动量分: {next_score:.1f})  
            **当前回撤**: {current_dd:.2%}
            
            **其他标的得分**: {other_scores_display}
            """)
            
            st.divider()
            
            # --- Charts ---
            st.markdown("### 📈 收益与回撤曲线")
            
            # Plotly Chart
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.05, 
                                subplot_titles=("策略净值曲线", "回撤曲线"),
                                row_heights=[0.7, 0.3])
            
            # Equity Curve
            fig.add_trace(go.Scatter(x=df_res.index, y=df_res['value'], 
                                     mode='lines', name='策略净值',
                                     line=dict(color='#00CC96', width=2)), row=1, col=1)
            
            # Drawdown Curve
            fig.add_trace(go.Scatter(x=df_res.index, y=drawdown, 
                                     mode='lines', name='回撤',
                                     fill='tozeroy',
                                     line=dict(color='#EF553B', width=1)), row=2, col=1)
            
            fig.update_layout(height=600, margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)
            
            st.divider()

            # --- Thermometer Chart ---
            st.markdown("### 🌡️ 策略温度计指标")
            
            # Calculate
            thermometer, plot_line = calculate_thermometer(df_res)
            
            fig_therm = go.Figure()
            
            fig_therm.add_trace(go.Scatter(
                x=thermometer.index, 
                y=thermometer,
                mode='lines',
                name='温度计 (Thermometer)',
                line=dict(color='#FFD700', width=1),
                fill='tozeroy',
                fillcolor='rgba(255, 215, 0, 0.1)'
            ))
            
            fig_therm.add_trace(go.Scatter(
                x=plot_line.index,
                y=plot_line,
                mode='lines',
                name='平滑线 (Signal)',
                line=dict(color='#FF4500', width=2)
            ))
            
            # Add horizontal lines
            fig_therm.add_hline(y=20, line_dash="dash", line_color="green", annotation_text="超卖 (20)")
            fig_therm.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="超买 (80)")
            
            fig_therm.update_layout(
                height=300, 
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis=dict(range=[0, 100], title="温度"),
                hovermode="x unified"
            )
            
            st.plotly_chart(fig_therm, use_container_width=True)
            
            st.divider()

            # --- NEW: Periodic Return Analysis ---
            st.markdown("### 🗓️ 周期收益分析")
            
            # 1. Prepare Data
            # df_res has 'value' and 'cum_return'
            # We need to calculate periodic returns
            
            # Resample
            df_daily = df_res[['value']].copy()
            df_daily['return'] = df_daily['value'].pct_change()
            
            # Heatmap Data Construction
            # Year on Y-axis, Month on X-axis
            
            df_daily['year'] = df_daily.index.year
            df_daily['month'] = df_daily.index.month
            df_daily['quarter'] = df_daily.index.quarter
            
            # Calculate monthly returns by compounding daily returns
            monthly_rets = df_daily.groupby(['year', 'month'])['return'].apply(lambda x: (1 + x).prod() - 1)
            monthly_rets_df = monthly_rets.unstack(level='month') * 100 # In percent
            
            # Yearly returns
            yearly_rets = df_daily.groupby(['year'])['return'].apply(lambda x: (1 + x).prod() - 1) * 100
            
            # Quarterly returns
            quarterly_rets = df_daily.groupby(['year', 'quarter'])['return'].apply(lambda x: (1 + x).prod() - 1) * 100
            
            # UI Control
            period_view = st.radio("显示模式", ["月度热力图", "年度收益柱状图", "季度收益柱状图"], horizontal=True)
            
            if period_view == "月度热力图":
                # Heatmap
                # x: Month, y: Year, z: Return
                
                # Fill missing months with 0 or NaN
                # Reindex columns 1-12
                for m in range(1, 13):
                    if m not in monthly_rets_df.columns:
                        monthly_rets_df[m] = np.nan
                monthly_rets_df = monthly_rets_df[sorted(monthly_rets_df.columns)]
                
                # Add Year Total column?
                monthly_rets_df['Year Total'] = yearly_rets
                
                # Plotly Heatmap
                # We transpose for Y=Year, X=Month
                # But heatmap expects z as 2D array
                
                # Better to use text for values
                z_vals = monthly_rets_df.values
                x_labels = [f"{m}月" for m in range(1, 13)] + ['年度合计']
                y_labels = monthly_rets_df.index.astype(str)
                
                # Custom Color Scale: Green (Negative) -> White (Zero) -> Red (Positive)
                # Using specific colors for better visibility
                custom_colorscale = [
                    [0.0, '#008000'],   # Green for Loss
                    [0.5, '#ffffff'],   # White for Zero
                    [1.0, '#ff0000']    # Red for Profit
                ]
                
                # Determine symmetric range for color balance
                # Filter nans for calculation
                valid_vals = z_vals[~np.isnan(z_vals)]
                if len(valid_vals) > 0:
                    max_abs = np.max(np.abs(valid_vals))
                    # Ensure a minimum range to avoid solid colors for small returns
                    if max_abs < 1: max_abs = 1
                else:
                    max_abs = 10
                
                # Create annotations
                annotations = []
                for i, row in enumerate(z_vals):
                    for j, val in enumerate(row):
                        if pd.notnull(val):
                            # Contrast text color
                            # If background is dark (high absolute value), use white text
                            text_color = "white" if abs(val) > (max_abs * 0.5) else "black"
                            
                            annotations.append(dict(
                                x=x_labels[j], y=y_labels[i],
                                text=f"{val:.1f}%",
                                xref="x", yref="y",
                                showarrow=False,
                                font=dict(color=text_color, size=14)
                            ))
                
                fig_heat = go.Figure(data=go.Heatmap(
                    z=z_vals,
                    x=x_labels,
                    y=y_labels,
                    colorscale=custom_colorscale,
                    zmid=0,
                    zmin=-max_abs,
                    zmax=max_abs,
                    hoverongaps=False,
                    xgap=1, # Add gap between cells
                    ygap=1
                ))
                
                fig_heat.update_layout(
                    title="月度收益率热力图 (%)",
                    height=400 + len(y_labels) * 40, # Increase height per row
                    annotations=annotations,
                    xaxis_side="top",
                    margin=dict(l=0, r=0, t=50, b=0) # Adjust margins
                )
                st.plotly_chart(fig_heat, use_container_width=True)
                
            elif period_view == "年度收益柱状图":
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=yearly_rets.index,
                    y=yearly_rets.values,
                    marker_color=['#EF553B' if x > 0 else '#00CC96' for x in yearly_rets.values],
                    text=[f"{x:.1f}%" for x in yearly_rets.values],
                    textposition='auto'
                ))
                fig_bar.update_layout(
                    title="年度收益率 (%)",
                    xaxis_title="年份",
                    yaxis_title="收益率 (%)",
                    showlegend=False
                )
                st.plotly_chart(fig_bar, use_container_width=True)
                
            elif period_view == "季度收益柱状图":
                # Format index for display: "2023-Q1"
                q_labels = [f"{y}-Q{q}" for y, q in quarterly_rets.index]
                
                fig_q = go.Figure()
                fig_q.add_trace(go.Bar(
                    x=q_labels,
                    y=quarterly_rets.values,
                    marker_color=['#EF553B' if x > 0 else '#00CC96' for x in quarterly_rets.values],
                    text=[f"{x:.1f}%" for x in quarterly_rets.values],
                    textposition='auto'
                ))
                fig_q.update_layout(
                    title="季度收益率 (%)",
                    xaxis_title="季度",
                    yaxis_title="收益率 (%)",
                    showlegend=False
                )
                st.plotly_chart(fig_q, use_container_width=True)

            # --- Trade Log & Holdings ---
            st.markdown("### 📝 交易记录与持仓明细")
            
            tab1, tab2 = st.tabs(["调仓记录", "每日持仓"])
            
            with tab1:
                if df_trades is not None and not df_trades.empty:
                    # Sort descending
                    df_trades_sorted = df_trades.sort_values('date', ascending=False)
                    st.dataframe(df_trades_sorted.style.format({
                        'price': '{:.3f}', 
                        'shares': '{:.0f}', 
                        'amount': '{:.2f}',
                        'fee': '{:.2f}',
                        'return_pct': '{:.2%}',
                        'trade_return': '{:.2%}',
                        'pnl_amount': '{:,.2f}'
                    }, na_rep="-"), use_container_width=True)
                else:
                    st.info("该期间无交易记录。")
                    
            with tab2:
                # Sort descending
                df_res_sorted = df_res.sort_index(ascending=False)
                st.dataframe(df_res_sorted.style.format({
                    'value': '{:.2f}',
                    'cum_return': '{:.2%}'
                }), use_container_width=True)
            
            st.divider()

            # --- NEW: Asset Trade Visualization ---
            st.markdown("### 📈 标的交易详情可视化")
            st.info("点击下方展开查看各标的的收盘价曲线及买卖点标记。鼠标悬停在卖出点（绿色倒三角）可查看该笔交易的收益率。")

            # Get list of assets traded
            traded_assets = df_trades['asset'].unique() if df_trades is not None else []
            
            if len(traded_assets) > 0:
                for asset in traded_assets:
                    with st.expander(f"查看 {asset} 交易记录"):
                        # Get OHLC
                        if asset in history_data:
                            asset_ohlc = history_data[asset]
                            asset_trades = df_trades[df_trades['asset'] == asset]
                            
                            # Plot
                            fig_asset = plot_asset_trades(
                                asset, 
                                asset_ohlc, 
                                asset_trades, 
                                df_res.index[0], # Start Date of backtest
                                df_res.index[-1] # End Date of backtest
                            )
                            
                            if fig_asset:
                                st.plotly_chart(fig_asset, use_container_width=True)
                            else:
                                st.warning(f"无法获取 {asset} 的价格数据")
            else:
                st.write("无交易标的。")
                
    else:
        st.info("👈 请在左侧调整参数并点击“开始回测”")

# --- Main App Logic ---
st.sidebar.title("导航")
page = st.sidebar.radio("选择页面", ["回测系统", "最新持仓标的", "策略介绍"], index=0)

if page == "回测系统":
    render_backtest_page()
elif page == "最新持仓标的":
    render_latest_holding_page()
elif page == "策略介绍":
    render_intro_page()
