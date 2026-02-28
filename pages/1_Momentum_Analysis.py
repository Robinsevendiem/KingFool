import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
from scipy.stats import linregress

# Set page configuration
st.set_page_config(
    page_title="动量得分与熔断机制分析",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 动量得分与“过热熔断”机制深度分析")

# ----------------- Data Loading & Calculation -----------------

@st.cache_data
def load_data():
    """Load history data for all assets"""
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
    
    data = {}
    for name, filename in mapping.items():
        if os.path.exists(filename):
            df = pd.read_csv(filename)
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d')
            df = df.sort_values('trade_date').set_index('trade_date')
            data[name] = df
    return data

@st.cache_data
def calculate_scores_and_returns(data):
    """
    Calculate Momentum Score (WLS) and Next-20-Day Return for each day.
    To analyze predictive power of Score on Future Return.
    """
    results = []
    
    # Analyze all dates
    all_dates = sorted(list(set().union(*[df.index for df in data.values()])))
    # Filter from 2017
    all_dates = [d for d in all_dates if d >= pd.Timestamp('2017-08-01')]
    
    # Sample every 5 days to speed up? Or all days.
    # Let's use all days but only for valid windows.
    
    for asset_name, df in data.items():
        # Calculate Score for each day
        # Rolling window calculation
        
        # We need:
        # 1. Score at day T (using T-19 to T)
        # 2. Return from T+1 to T+21 (Next 20 days holding return)
        
        # Pre-calculate log prices
        df['log_price'] = np.log(df['close'])
        
        # We can loop or use rolling apply (complex with WLS)
        # Loop is easier to understand
        
        prices = df['close'].values
        dates = df.index
        
        for i in range(19, len(df) - 20): # Ensure we have 20 days future
            # Window T-19 to T
            window_prices = prices[i-19 : i+1]
            current_date = dates[i]
            
            # Calc Score
            y = np.log(window_prices)
            x = np.arange(20)
            weights = 1 + (np.linspace(0, 1, 20) ** 2)
            
            coeffs = np.polyfit(x, y, 1, w=weights)
            slope = coeffs[0]
            
            y_pred = np.polyval(coeffs, x)
            sse = np.sum(weights * (y - y_pred)**2)
            sst = np.sum(weights * (y - np.average(y, weights=weights))**2)
            r2 = 1 - sse/sst if sst != 0 else 0
            
            score = (np.exp(slope * 252) - 1) * r2 * 100
            
            # Calc Future Return (Next 20 days)
            # Price at T+1 (Buy) to T+21 (Sell)? Or T to T+20?
            # Strategy trades at T+1 Open.
            # Let's approximate: Return from T Close to T+20 Close.
            future_ret = prices[i+20] / prices[i] - 1
            
            # Future Max Drawdown (Risk)
            future_window = prices[i+1 : i+21]
            cum_max = np.maximum.accumulate(future_window)
            dd = (future_window - cum_max) / cum_max
            future_max_dd = dd.min()
            
            results.append({
                'Asset': asset_name,
                'Date': current_date,
                'Score': score,
                'Future_Return_20d': future_ret,
                'Future_MaxDD_20d': future_max_dd
            })
            
    return pd.DataFrame(results)

data = load_data()
df_analysis = calculate_scores_and_returns(data)

# ----------------- Analysis Section 1: Score Distribution -----------------

st.header("1. 动量得分分布特征")
st.markdown("""
首先，我们观察一下所有标的在历史上的动量得分分布。
大多数时候得分集中在什么区间？极端高分（>300）出现的频率是多少？
""")

col1, col2 = st.columns([2, 1])

with col1:
    fig_hist = px.histogram(
        df_analysis, 
        x="Score", 
        nbins=100, 
        color="Asset",
        title="各标的动量得分分布直方图",
        labels={"Score": "动量得分 (Slope * R² * 100)"}
    )
    fig_hist.add_vline(x=300, line_dash="dash", line_color="red", annotation_text="熔断阈值 (300)")
    st.plotly_chart(fig_hist, use_container_width=True)

with col2:
    st.subheader("统计数据")
    total_samples = len(df_analysis)
    overheated_samples = len(df_analysis[df_analysis['Score'] > 300])
    
    st.metric("总样本数", total_samples)
    st.metric("过热样本数 (>300)", overheated_samples)
    st.metric("过热占比", f"{overheated_samples / total_samples:.2%}")
    
    st.write("虽然过热样本占比极低，但它们往往对应着极端的行情。")

# ----------------- Analysis Section 2: Why Cutoff Works? -----------------

st.header("2. 为什么“熔断”能提高收益？")
st.markdown("""
核心问题：**得分越高，未来的收益真的越好吗？**
让我们看看“当前得分”与“未来20天收益”的关系。
""")

# Bin the scores
bins = [-float('inf'), 0, 100, 200, 300, 400, 500, float('inf')]
labels = ['<0 (下跌)', '0-100 (温和)', '100-200 (强势)', '200-300 (极强)', '300-400 (过热)', '400-500 (疯狂)', '>500 (泡沫)']
df_analysis['Score_Bin'] = pd.cut(df_analysis['Score'], bins=bins, labels=labels)

# Group by Bin
bin_stats = df_analysis.groupby('Score_Bin')[['Future_Return_20d', 'Future_MaxDD_20d']].mean().reset_index()

col3, col4 = st.columns(2)

with col3:
    fig_bar_ret = px.bar(
        bin_stats,
        x='Score_Bin',
        y='Future_Return_20d',
        title="不同得分区间的平均未来收益 (20天)",
        color='Future_Return_20d',
        color_continuous_scale='RdYlGn',
        text_auto='.2%'
    )
    st.plotly_chart(fig_bar_ret, use_container_width=True)
    st.info("注意看：得分在 200-300 区间时，未来收益达到顶峰。而一旦超过 300，未来收益开始**断崖式下跌**！")

with col4:
    fig_bar_dd = px.bar(
        bin_stats,
        x='Score_Bin',
        y='Future_MaxDD_20d',
        title="不同得分区间的平均未来回撤 (20天)",
        color='Future_MaxDD_20d',
        color_continuous_scale='Reds_r', # Darker red for worse dd
        text_auto='.2%'
    )
    st.plotly_chart(fig_bar_dd, use_container_width=True)
    st.info("风险视角：得分超过 300 后，未来的平均回撤显著增大。这意味着“过热”后往往紧接着剧烈的均值回归。")

# ----------------- Analysis Section 3: Scatter Plot -----------------

st.header("3. 均值回归的微观证据")
st.markdown("让我们在散点图上更直观地看到这种“倒U型”关系。")

fig_scatter = px.scatter(
    df_analysis,
    x="Score",
    y="Future_Return_20d",
    color="Asset",
    trendline="lowess", # Locally Weighted Scatterplot Smoothing
    trendline_color_override="black",
    title="动量得分 vs 未来20日收益 (散点图 + 趋势线)",
    opacity=0.5,
    hover_data=['Date']
)
fig_scatter.add_vline(x=300, line_dash="dash", line_color="red", annotation_text="收益反转点")
st.plotly_chart(fig_scatter, use_container_width=True)

# ----------------- Analysis Section 4: Case Study -----------------

st.header("4. 典型案例：那些被“熔断”救下的时刻")
st.markdown("筛选出得分 > 300 且随后大跌的典型案例。")

overheated_crashes = df_analysis[
    (df_analysis['Score'] > 300) & 
    (df_analysis['Future_Return_20d'] < -0.1)
].sort_values('Score', ascending=False).head(10)

st.table(overheated_crashes[['Date', 'Asset', 'Score', 'Future_Return_20d', 'Future_MaxDD_20d']].style.format({
    'Score': '{:.2f}',
    'Future_Return_20d': '{:.2%}',
    'Future_MaxDD_20d': '{:.2%}'
}))

st.markdown("""
### 总结
1.  **收益非线性**：动量策略并非“强者恒强”那么简单。在一定范围内（0-300），得分越高收益越好；但超过临界点（300）后，**动量效应失效，反转效应占主导**。
2.  **熔断机制的价值**：设置 Score < 300 的熔断机制，本质上是在**“动量因子”**失效的区间，自动切换到了**“反转因子”**（通过卖出避免下跌），从而完美地规避了泡沫破裂的风险。
""")
