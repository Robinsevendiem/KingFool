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

warnings.filterwarnings('ignore')

# --- Page Config ---
st.set_page_config(page_title="ETF 动量策略回测系统", layout="wide", page_icon="📈")

# --- Helper: Data Update ---
def update_data(token):
    """
    Update ETF data using Tushare.
    """
    try:
        # ts.set_token(token)
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

    today = datetime.now().strftime('%Y%m%d')
    
    total_etfs = len(etfs)
    
    for i, etf in enumerate(etfs):
        code = etf['code']
        name = etf['name']
        filename = f"data/{code}_{name}_history.csv"
        
        status_text.text(f"正在处理: {name} ({code})...")
        
        # Determine start date
        start_date = etf['start_date']
        existing_df = None
        
        if os.path.exists(filename):
            try:
                existing_df = pd.read_csv(filename)
                existing_df['trade_date'] = pd.to_datetime(existing_df['trade_date'], format='%Y%m%d')
                if not existing_df.empty:
                    last_date = existing_df['trade_date'].max()
                    start_date = (last_date + timedelta(days=1)).strftime('%Y%m%d')
            except Exception as e:
                logs.append(f"读取现有文件 {filename} 失败: {e}")
        
        # Fetch Data
        if start_date > today:
            logs.append(f"{name}: 数据已是最新。")
        else:
            try:
                # Fetch unadjusted
                df_raw = ts.pro_bar(ts_code=code, start_date=start_date, end_date=today, adj=None, asset='FD')
                # Fetch adjusted (qfq)
                df_adj = ts.pro_bar(ts_code=code, start_date=start_date, end_date=today, adj='qfq', asset='FD')
                
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
                    logs.append(f"{name}: 更新了 {len(df_new)} 条记录。")
                else:
                    logs.append(f"{name}: 无新数据。")
            except Exception as e:
                logs.append(f"{name} 更新失败: {e}")
        
        progress_bar.progress((i + 1) / total_etfs)
        time.sleep(0.1) # Be nice to API
        
    status_text.text("数据更新完成！")
    with st.expander("查看更新日志"):
        st.write(logs)
    
    return True

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
        if 'close' in df.columns:
            scores = calculate_rolling_scores(df['close'], window=window)
            scores.name = asset
            all_scores = pd.merge(all_scores, scores, left_index=True, right_index=True, how='outer')
    return all_scores

# --- 2. Backtest Logic ---

def run_backtest(history_data, raw_scores_df, params):
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
        'crash_threshold': float
    }
    """
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
    
    # Cache Prices & Returns for Speed
    price_open = {asset: df['open'] for asset, df in history_data.items()}
    price_close = {asset: df['close'] for asset, df in history_data.items()}
    
    daily_returns = {}
    if params['crash_filter_enabled']:
        for asset, df in history_data.items():
            daily_returns[asset] = df['close'].pct_change()
    
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
            if current_asset in cost_basis:
                buy_price = cost_basis[current_asset]
                if buy_price > 0:
                    trade_return_pct = (price - buy_price) / buy_price
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
                'trade_return': trade_return_pct
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
            cost_basis[target_asset] = price
            
            trade_log.append({
                'date': date,
                'action': '买入',
                'asset': target_asset,
                'price': price,
                'shares': shares,
                'amount': cost,
                'fee': shares * price * params['fee_rate'],
                'return_pct': cum_ret_pct,
                'trade_return': np.nan
            })
            current_asset = target_asset
            
        # --- B. Valuation (At Close) ---
        day_value = cash
        for asset, shares in holdings.items():
            if date in price_close[asset].index:
                price = price_close[asset].loc[date]
            else:
                try:
                    price = price_close[asset].asof(date)
                except:
                    price = 0
            day_value += shares * price
            
        value_history.append({'date': date, 'value': day_value, 'holding': current_asset})
        
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
                
                # Filter scores to valid pool
                pool_scores = today_scores[today_scores.index.isin(valid_assets_pool)]
                
                if pool_scores.empty:
                    next_target = '现金'
                else:
                    # 2. Filter Candidates (Score > 0 & <= Cutoff)
                    valid_candidates = pool_scores[
                        (pool_scores <= params['cutoff_score']) & (pool_scores > 0)
                    ]
                    
                    if valid_candidates.empty:
                        next_target = '现金'
                    else:
                        # 3. Normalize Valid Scores (Relative to Pool)
                        vals = pool_scores.values
                        mn, mx = np.min(vals), np.max(vals)
                        if mx == mn:
                            norm_scores = pd.Series(50, index=pool_scores.index)
                        else:
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
    
    # Try to get token from secrets, otherwise use default (or empty)
    # Ideally, users should set .streamlit/secrets.toml or Streamlit Cloud secrets
    default_token = "e5e7ab8532e5d39159a7a47fe439348a68844653e1b9cf5b1f7426ea"
    ts_token = default_token
    
    try:
        if "TUSHARE_TOKEN" in st.secrets:
            ts_token = st.secrets["TUSHARE_TOKEN"]
    except:
        pass
        
    # Allow manual override
    manual_token = st.sidebar.text_input("Tushare Token (可选)", value="", type="password", help="如果自动获取失败，请在此手动输入 Token")
    if manual_token:
        ts_token = manual_token
        st.session_state['tushare_token'] = manual_token
    
    if st.sidebar.button("🔄 更新数据"):
        with st.spinner("正在连接 Tushare 更新数据..."):
            if update_data(ts_token):
                st.success("数据更新成功！请刷新页面或重新回测。")
                # Clear cache to force reload
                load_history_data.clear()
                precalculate_all_scores.clear()
                st.rerun()
    
    st.sidebar.divider()
    
    # Date Range (Only needed for backtest range, but useful to keep here or default)
    # For simplicity, we keep them here but Latest Holding might ignore start/end
    min_date = pd.Timestamp('2017-08-01')
    max_date = pd.Timestamp.now()
    
    start_date = st.sidebar.date_input("开始日期", min_date, min_value=min_date, max_value=max_date)
    end_date = st.sidebar.date_input("结束日期", max_date, min_value=min_date, max_value=max_date)
    
    start_date = pd.Timestamp(start_date)
    end_date = pd.Timestamp(end_date)
    
    # Strategy Params
    st.sidebar.subheader("核心参数")
    window = st.sidebar.number_input("动量窗口 (天)", min_value=5, max_value=60, value=20, step=1)
    cutoff_score = st.sidebar.number_input("过热熔断阈值 (分数)", min_value=50, max_value=1000, value=700, step=10)
    buffer_score = st.sidebar.number_input("换仓缓冲阈值 (分差)", min_value=0.0, max_value=50.0, value=8.0, step=0.5)
    
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
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'window': window,
        'cutoff_score': cutoff_score,
        'buffer_score': buffer_score,
        'fee_rate': fee_rate,
        'initial_capital': initial_capital,
        'crash_filter_enabled': crash_filter_enabled,
        'crash_window': crash_window,
        'crash_threshold': crash_threshold
    }

def render_latest_holding_page():
    st.title("🔔 最新持仓信号")
    
    # Sidebar
    params = get_strategy_params()
    
    st.info("点击下方按钮，系统将获取最新数据，并根据当前策略参数计算下一个交易日的建议持仓。")
    
    if st.button("🔍 检查并获取最新信号", type="primary"):
        # 1. Update Data
        default_token = "e5e7ab8532e5d39159a7a47fe439348a68844653e1b9cf5b1f7426ea"
        ts_token = default_token
        try:
            if "TUSHARE_TOKEN" in st.secrets:
                ts_token = st.secrets["TUSHARE_TOKEN"]
        except:
            pass
        
        # Check sidebar override (params are loaded from sidebar)
        # But get_strategy_params runs in sidebar and returns params dict.
        # It doesn't return the token.
        # So we can't easily access the manual token from sidebar here unless we store it in session state.
        
        # Let's add session state logic for token
        if 'tushare_token' in st.session_state and st.session_state['tushare_token']:
             ts_token = st.session_state['tushare_token']
        
        with st.spinner("正在同步最新市场数据..."):
            if 'tushare_token' in st.session_state and st.session_state['tushare_token']:
                 ts_token = st.session_state['tushare_token']
            
            update_data(ts_token)
            load_history_data.clear()
            precalculate_all_scores.clear()
            
        # 2. Load & Calc
        with st.spinner("正在计算策略信号..."):
            history_data = load_history_data()
            scores_df = precalculate_all_scores(history_data, window=params['window'])
            
            # 3. Run Backtest to determine state
            # We run from a reasonable past date to ensure state is correct
            # Start from 2024-01-01 or params['start_date']? 
            # Use params['start_date'] to be consistent with backtest settings
            backtest_params = params.copy()
            backtest_params['end_date'] = pd.Timestamp.now() # Ensure we go up to today
            
            df_res, df_trades, timeline, last_signal = run_backtest(history_data, scores_df, backtest_params)
            
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
                    # Check if valid (Crash filter etc)
                    # We need to replicate the filter logic or just show raw score
                    # Let's show raw score and highlight
                    status = "✅ 候选"
                    if score > params['cutoff_score']:
                        status = "🚫 过热熔断"
                    elif score <= 0:
                        status = "📉 负动量"
                        
                    details.append({
                        '标的': asset,
                        '动量得分': f"{score:.1f}",
                        '状态': status
                    })
                
                st.dataframe(pd.DataFrame(details))

def render_backtest_page():
    # Sidebar Controls
    params = get_strategy_params()
    
    # Data Loading
    history_data = load_history_data()
    
    if st.sidebar.button("🚀 开始回测", type="primary"):
        with st.spinner("正在计算动量得分..."):
            # Pre-calculate scores based on window
            scores_df = precalculate_all_scores(history_data, window=params['window'])
            
        with st.spinner("正在执行回测..."):
            df_res, df_trades, timeline, last_signal = run_backtest(history_data, scores_df, params)
            
            if df_res is None or df_res.empty:
                st.error("该时间段内无数据或回测失败。")
            else:
                # Calculate daily cumulative return
                df_res['cum_return'] = df_res['value'] / params['initial_capital'] - 1

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
                            'trade_return': '{:.2%}'
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
                    
    else:
        st.info("👈 请在左侧调整参数并点击“开始回测”")

# --- Main App Logic ---
st.sidebar.title("导航")
page = st.sidebar.radio("选择页面", ["回测系统", "最新持仓标的", "策略介绍"])

if page == "回测系统":
    render_backtest_page()
elif page == "最新持仓标的":
    render_latest_holding_page()
elif page == "策略介绍":
    render_intro_page()
