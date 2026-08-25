import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import folium
from streamlit_folium import st_folium
import pathlib
import sys

# Add parent directory to path so we can import config
BASE_DIR = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))
import config

# Set page config for a premium, wide layout
st.set_page_config(
    page_title="Market Tracking Dashboard",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium look
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .kpi-card {
        background-color: #1e2129;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        text-align: center;
        border-top: 4px solid #4CAF50;
    }
    .kpi-title {
        color: #8b92a5;
        font-size: 14px;
        text-transform: uppercase;
        font-weight: 600;
        margin-bottom: 5px;
    }
    .kpi-value {
        color: #ffffff;
        font-size: 32px;
        font-weight: 700;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #1e2129;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
        padding-left: 20px;
        padding-right: 20px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2196F3 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def load_real_estate_data():
    conn = sqlite3.connect(config.DB_PATH)
    query = """
        SELECT address, city, state, county, zip_code, status,
               previous_status, status_updated_at,
               list_price, bedrooms, bathrooms, sqft, is_vacant,
               latitude, longitude, scraped_at,
               realtor_name, realtor_email, realtor_phone
        FROM pre_mover_leads
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['list_price'] = pd.to_numeric(df['list_price'], errors='coerce')
    df['sqft']       = pd.to_numeric(df['sqft'], errors='coerce')
    df['scraped_at'] = pd.to_datetime(df['scraped_at'], errors='coerce')
    return df

@st.cache_data(ttl=60)
def load_storage_data():
    conn = sqlite3.connect(config.DB_PATH)
    query = """
        SELECT f.id, f.name, f.brand, f.address, f.city, f.state, f.zip_code,
               f.lat as latitude, f.lon as longitude,
               p.unit_size, p.web_rate, p.availability, p.scraped_at
        FROM facilities f
        LEFT JOIN (
            SELECT facility_id, unit_size, web_rate, availability, scraped_at,
                   ROW_NUMBER() OVER(PARTITION BY facility_id, unit_size ORDER BY scraped_at DESC) as rn
            FROM pricing_snapshots
        ) p ON f.id = p.facility_id AND p.rn = 1
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['scraped_at'] = pd.to_datetime(df['scraped_at'], errors='coerce')
    return df

@st.cache_data(ttl=120)
def load_storage_history():
    """Full pricing snapshot history for trend charts."""
    conn = sqlite3.connect(config.DB_PATH)
    query = """
        SELECT f.brand, p.unit_size, p.web_rate,
               date(p.scraped_at) as snap_date
        FROM pricing_snapshots p
        JOIN facilities f ON f.id = p.facility_id
        WHERE p.web_rate IS NOT NULL
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['snap_date'] = pd.to_datetime(df['snap_date'], errors='coerce')
    return df

with st.spinner("Loading market data..."):
    df_re_raw  = load_real_estate_data()
    df_st_raw  = load_storage_data()
    df_st_hist = load_storage_history()

from datetime import date, timedelta
today = date.today()

def month_bounds(d):
    first = d.replace(day=1)
    if first.month == 12:
        last = first.replace(year=first.year + 1, month=1) - timedelta(days=1)
    else:
        last = first.replace(month=first.month + 1) - timedelta(days=1)
    return first, last

cur_month_start, _ = month_bounds(today)

# Initialize session state
defaults = {
    're_statuses': None, 're_states': None, 're_counties': None, 're_price': None,
    're_date_start': cur_month_start, 're_date_end': today,
    'st_brands': None, 'st_size': None,
    'st_date_start': cur_month_start, 'st_date_end': today,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Navigation
page = st.sidebar.radio("Navigation", ["🏡 Real Estate Market", "📦 Self-Storage Market", "🗄️ Database View"])

# =====================================================================
# PAGE 1: REAL ESTATE MARKET
# =====================================================================
if page == "🏡 Real Estate Market":
    st.sidebar.write("---")
    st.sidebar.header("🏡 Real Estate Filters")

    # Date range
    st.sidebar.subheader("📅 Date Range")
    re_date_start = st.sidebar.date_input("From", value=st.session_state.re_date_start, key="re_ds")
    re_date_end   = st.sidebar.date_input("To",   value=st.session_state.re_date_end,   key="re_de")
    st.session_state.re_date_start = re_date_start
    st.session_state.re_date_end   = re_date_end
    st.sidebar.write("---")

    # Status filter
    statuses = df_re_raw['status'].dropna().unique().tolist()
    default_statuses = st.session_state.re_statuses if st.session_state.re_statuses is not None else statuses
    valid_statuses   = [s for s in default_statuses if s in statuses]
    selected_statuses = st.sidebar.multiselect("Listing Status", options=statuses, default=valid_statuses)
    st.session_state.re_statuses = selected_statuses

    # State filter
    states = sorted(df_re_raw['state'].dropna().unique().tolist())
    default_states = st.session_state.re_states if st.session_state.re_states is not None else states
    valid_states   = [s for s in default_states if s in states]
    selected_states = st.sidebar.multiselect("States", options=states, default=valid_states)
    st.session_state.re_states = selected_states

    # County filter
    counties = sorted(df_re_raw['county'].dropna().unique().tolist())
    default_counties = st.session_state.re_counties if st.session_state.re_counties is not None else counties
    valid_counties   = [c for c in default_counties if c in counties]
    selected_counties = st.sidebar.multiselect("Counties", options=counties, default=valid_counties)
    st.session_state.re_counties = selected_counties

    # Price filter
    min_price = float(df_re_raw['list_price'].min()) if not df_re_raw['list_price'].dropna().empty else 0.0
    max_price = float(df_re_raw['list_price'].max()) if not df_re_raw['list_price'].dropna().empty else 5000000.0
    default_price = st.session_state.re_price if st.session_state.re_price is not None else (min_price, max_price)
    price_range = st.sidebar.slider("Price Range ($)", min_value=min_price, max_value=max_price, value=default_price)
    st.session_state.re_price = price_range

    # Apply filters
    mask = (
        (df_re_raw['status'].isin(selected_statuses)) &
        (df_re_raw['list_price'] >= price_range[0]) &
        (df_re_raw['list_price'] <= price_range[1])
    )
    if re_date_start and re_date_end:
        mask &= (df_re_raw['scraped_at'].dt.date >= re_date_start) & (df_re_raw['scraped_at'].dt.date <= re_date_end)
    df_re = df_re_raw[mask]
    if selected_states:
        df_re = df_re[df_re['state'].isin(selected_states)]
    if selected_counties:
        df_re = df_re[df_re['county'].isin(selected_counties)]

    # Previous period for comparison
    delta_days = (re_date_end - re_date_start).days if re_date_start and re_date_end else 30
    prev_start = re_date_start - timedelta(days=delta_days + 1) if re_date_start else None
    prev_end   = re_date_start - timedelta(days=1) if re_date_start else None
    if prev_start and prev_end:
        mask_prev = (
            (df_re_raw['scraped_at'].dt.date >= prev_start) &
            (df_re_raw['scraped_at'].dt.date <= prev_end)
        )
        df_re_prev = df_re_raw[mask_prev]
    else:
        df_re_prev = pd.DataFrame()

    st.title("Regional MLS Market")
    date_label = f"{re_date_start.strftime('%b %d')} – {re_date_end.strftime('%b %d, %Y')}" if re_date_start else "All Time"
    st.caption(f"Showing data for: **{date_label}**")

    def delta_badge(cur, prev, higher_is_better=True):
        if not prev or pd.isna(prev) or prev == 0:
            return ""
        pct = (cur - prev) / abs(prev) * 100
        arrow = "↑" if pct >= 0 else "↓"
        color = "#4CAF50" if (pct >= 0) == higher_is_better else "#F44336"
        return f"<div style='font-size:12px;margin-top:4px;color:{color};'>{arrow} {abs(pct):.1f}% vs prev period</div>"

    col1, col2, col3, col4, col5 = st.columns(5)
    cur_total   = len(df_re)
    prev_total  = len(df_re_prev) if not df_re_prev.empty else 0
    cur_active  = len(df_re[df_re["status"] == "for_sale"])
    prev_active = len(df_re_prev[df_re_prev["status"] == "for_sale"]) if not df_re_prev.empty else 0
    cur_uc      = len(df_re[df_re["status"] == "under_contract"])
    prev_uc     = len(df_re_prev[df_re_prev["status"] == "under_contract"]) if not df_re_prev.empty else 0
    cur_price   = df_re['list_price'].mean()
    prev_price  = df_re_prev['list_price'].mean() if not df_re_prev.empty else 0
    cur_changed = len(df_re[df_re['previous_status'].notna()])

    with col1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Total Listings</div><div class="kpi-value">{cur_total:,}</div>{delta_badge(cur_total, prev_total)}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#2196F3;"><div class="kpi-title">Active (For Sale)</div><div class="kpi-value">{cur_active:,}</div>{delta_badge(cur_active, prev_active)}</div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#FF9800;"><div class="kpi-title">Under Contract</div><div class="kpi-value">{cur_uc:,}</div>{delta_badge(cur_uc, prev_uc)}</div>', unsafe_allow_html=True)
    with col4:
        avg_price_str = f"${cur_price:,.0f}" if pd.notnull(cur_price) else "N/A"
        st.markdown(f'<div class="kpi-card" style="border-top-color:#9C27B0;"><div class="kpi-title">Avg List Price</div><div class="kpi-value">{avg_price_str}</div>{delta_badge(cur_price or 0, prev_price or 0, higher_is_better=False)}</div>', unsafe_allow_html=True)
    with col5:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#F44336;"><div class="kpi-title">Status Changed</div><div class="kpi-value">{cur_changed:,}</div></div>', unsafe_allow_html=True)

    st.write("---")

    col_map, col_chart = st.columns([2, 1])
    with col_map:
        st.subheader("📍 Property Map")
        df_map = df_re.dropna(subset=['latitude', 'longitude'])
        if not df_map.empty:
            center_lat, center_lon = df_map['latitude'].mean(), df_map['longitude'].mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles="CartoDB dark_matter")
            if len(df_map) > 1000:
                df_map = df_map.sample(1000)
                st.caption(f"Displaying random sample of 1,000 out of {len(df_re)} properties.")
            for idx, row in df_map.iterrows():
                color = "green" if row['status'] == 'for_sale' else "orange" if row['status'] == 'under_contract' else "gray"
                price_str = f"${row['list_price']:,.0f}" if pd.notnull(row['list_price']) else "N/A"
                popup = f"<b>{row['address']}</b><br>Price: {price_str}<br>Status: {row['status']}"
                folium.CircleMarker([row['latitude'], row['longitude']], radius=4, popup=folium.Popup(popup, max_width=250), color=color, fill=True, fill_opacity=0.7).add_to(m)
            st_folium(m, width=800, height=500, returned_objects=[])
        else:
            st.info("No properties to map.")

    with col_chart:
        st.subheader("📊 Market Breakdown")
        if not df_re.empty:
            county_counts = df_re['county'].value_counts().reset_index()
            county_counts.columns = ['County', 'Count']
            fig1 = px.bar(county_counts.head(10), x='Count', y='County', orientation='h', color='Count', template="plotly_dark")
            fig1.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, margin=dict(l=0, r=0, t=0, b=0), height=240)
            st.plotly_chart(fig1, use_container_width=True)

            status_counts = df_re['status'].value_counts().reset_index()
            status_counts.columns = ['Status', 'Count']
            fig2 = px.pie(status_counts, values='Count', names='Status', hole=0.4, template="plotly_dark", color_discrete_sequence=px.colors.qualitative.Set2)
            fig2.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=240)
            st.plotly_chart(fig2, use_container_width=True)

    st.write("---")

    # ── Monthly Statistics ───────────────────────────────────────
    st.subheader("📅 Monthly Statistics")
    tab1, tab2, tab3 = st.tabs(["📈 Listings Over Time", "🏘️ County Breakdown", "🤝 Top Realtors"])

    with tab1:
        if not df_re.empty:
            df_weekly = df_re.copy()
            df_weekly['week'] = df_weekly['scraped_at'].dt.to_period('W').dt.start_time.dt.date
            weekly = df_weekly.groupby(['week', 'status']).size().reset_index(name='Count')
            fig_line = px.bar(weekly, x='week', y='Count', color='status', barmode='stack',
                              template="plotly_dark", title="Listings Added Per Week (by Status)",
                              color_discrete_sequence=px.colors.qualitative.Set2)
            fig_line.update_layout(xaxis_title="Week", yaxis_title="Listings", margin=dict(l=0, r=0, t=40, b=0), height=350)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No data in the selected date range.")

    with tab2:
        if not df_re.empty:
            county_status = df_re.groupby(['county', 'status']).size().reset_index(name='Count')
            top_counties  = df_re['county'].value_counts().head(12).index.tolist()
            county_status = county_status[county_status['county'].isin(top_counties)]
            fig_county = px.bar(county_status, x='county', y='Count', color='status', barmode='group',
                                template="plotly_dark", title="Listing Status by County (Top 12)",
                                color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_county.update_layout(xaxis_tickangle=-30, margin=dict(l=0, r=0, t=40, b=60), height=400)
            st.plotly_chart(fig_county, use_container_width=True)

            price_county = df_re.groupby('county')['list_price'].mean().dropna().sort_values(ascending=False).head(12).reset_index()
            price_county.columns = ['County', 'Avg Price']
            fig_price = px.bar(price_county, x='County', y='Avg Price', color='Avg Price',
                               color_continuous_scale='Blues', template="plotly_dark",
                               title="Avg List Price by County")
            fig_price.update_layout(xaxis_tickangle=-30, margin=dict(l=0, r=0, t=40, b=60), height=350)
            st.plotly_chart(fig_price, use_container_width=True)
        else:
            st.info("No data in the selected date range.")

    with tab3:
        if not df_re.empty and 'realtor_name' in df_re.columns:
            realtors = (
                df_re[df_re['realtor_name'].notna() & (df_re['realtor_name'] != '')]
                .groupby('realtor_name')
                .agg(
                    Listings     = ('address', 'count'),
                    Avg_Price    = ('list_price', 'mean'),
                    Phone        = ('realtor_phone', 'first'),
                    Email        = ('realtor_email', 'first'),
                    ZIPs_Covered = ('zip_code', lambda x: ', '.join(sorted(x.dropna().unique()[:5]))),
                )
                .sort_values('Listings', ascending=False)
                .reset_index()
                .head(30)
            )
            realtors['Avg_Price'] = realtors['Avg_Price'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "N/A")
            realtors.columns = ['Realtor', 'Listings', 'Avg Price', 'Phone', 'Email', 'ZIPs']
            st.dataframe(realtors, use_container_width=True, height=500)
        else:
            st.info("No realtor data available in this date range.")

    st.write("---")

    # ── Recently Changed Listings ─────────────────────────────────
    st.subheader("🔄 Recently Changed Listings")
    df_changed = df_re[df_re['previous_status'].notna()].copy()
    if not df_changed.empty:
        df_changed['transition'] = df_changed['previous_status'] + ' → ' + df_changed['status']
        col_trans_chart, col_trans_table = st.columns([1, 2])
        with col_trans_chart:
            trans_counts = df_changed['transition'].value_counts().reset_index()
            trans_counts.columns = ['Transition', 'Count']
            fig_trans = px.bar(trans_counts, x='Count', y='Transition', orientation='h',
                               color='Count', color_continuous_scale='Reds', template='plotly_dark',
                               title='Status Transitions')
            fig_trans.update_layout(yaxis={'categoryorder': 'total ascending'}, showlegend=False,
                                    margin=dict(l=0, r=0, t=30, b=0), height=300)
            st.plotly_chart(fig_trans, use_container_width=True)
        with col_trans_table:
            display_changed = df_changed[[
                'address', 'city', 'county', 'zip_code',
                'previous_status', 'status', 'list_price', 'status_updated_at'
            ]].rename(columns={
                'previous_status': 'Old Status', 'status': 'New Status',
                'list_price': 'Price', 'status_updated_at': 'Changed On'
            })
            st.dataframe(display_changed, use_container_width=True, height=300)
    else:
        st.info("No status changes detected in this period.")

    st.write("---")
    st.subheader("📋 Raw Data Explorer")
    st.dataframe(df_re[['address', 'city', 'county', 'zip_code', 'status', 'previous_status', 'list_price', 'bedrooms', 'bathrooms', 'sqft', 'is_vacant']], use_container_width=True)


# =====================================================================
# PAGE 2: SELF-STORAGE MARKET
# =====================================================================
elif page == "📦 Self-Storage Market":
    st.sidebar.write("---")
    st.sidebar.header("📦 Storage Filters")

    st.sidebar.write("---")
    status_file = pathlib.Path('.scraper_status')
    pid_file    = pathlib.Path('.scraper_pid')

    if status_file.exists():
        st.sidebar.info("🕵️‍♂️ Scraper is running in the background!")
        st.sidebar.markdown("![Scraping Animation](https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3YnNieHJscGpoNmh1cWZncm1uenAxd3NxYjVwNjB1Y3BrODIyaTluaCZlcD12MV9naWZzX3JlbGF0ZWQmY3Q9Zw/ule4vhcY1xEKQ/giphy.gif)")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with col2:
            if st.button("🛑 Stop", type="primary", use_container_width=True):
                if pid_file.exists():
                    try:
                        import os, signal
                        pid = int(pid_file.read_text())
                        os.kill(pid, signal.SIGTERM)
                    except Exception:
                        pass
                    pid_file.unlink(missing_ok=True)
                status_file.unlink(missing_ok=True)
                st.toast("Scraper stopped forcefully!", icon="🛑")
                st.rerun()
    else:
        if st.sidebar.button("🚀 Run Storage Scraper Now", use_container_width=True):
            status_file.touch()
            import threading, subprocess
            def bg_run():
                try:
                    process = subprocess.Popen(
                        [sys.executable, "-c", "from collectors.run_all import run_self_storage; run_self_storage(dry_run=False)"]
                    )
                    pid_file.write_text(str(process.pid))
                    process.wait()
                finally:
                    if status_file.exists(): status_file.unlink()
                    if pid_file.exists():    pid_file.unlink()
            threading.Thread(target=bg_run, daemon=True).start()
            st.rerun()

    st.sidebar.write("---")

    # Date range for storage
    st.sidebar.subheader("📅 Date Range")
    st_all_dates = df_st_hist['snap_date'].dropna()
    st_min_date  = st_all_dates.min().date() if not st_all_dates.empty else cur_month_start
    st_date_start = st.sidebar.date_input("From", value=st.session_state.st_date_start, min_value=st_min_date, key="st_ds")
    st_date_end   = st.sidebar.date_input("To",   value=st.session_state.st_date_end,   min_value=st_min_date, key="st_de")
    st.session_state.st_date_start = st_date_start
    st.session_state.st_date_end   = st_date_end
    st.sidebar.write("---")

    brands = sorted(df_st_raw['brand'].dropna().unique().tolist())
    default_brands = st.session_state.st_brands if st.session_state.st_brands is not None else brands
    valid_brands   = [b for b in default_brands if b in brands]
    selected_brands = st.sidebar.multiselect("Storage Brands", options=brands, default=valid_brands)
    st.session_state.st_brands = selected_brands

    unit_sizes = sorted(df_st_raw['unit_size'].dropna().unique().tolist())
    if not unit_sizes:
        unit_sizes = ["10x10"]
    default_size  = st.session_state.st_size if st.session_state.st_size in unit_sizes else unit_sizes[0]
    selected_size = st.sidebar.selectbox("Unit Size to Compare", options=unit_sizes, index=unit_sizes.index(default_size))
    st.session_state.st_size = selected_size

    # Filter snapshot data
    df_st = df_st_raw[df_st_raw['brand'].isin(selected_brands)] if selected_brands else df_st_raw.copy()

    # Filter history for charts
    df_hist = df_st_hist.copy()
    if st_date_start and st_date_end:
        df_hist = df_hist[
            (df_hist['snap_date'].dt.date >= st_date_start) &
            (df_hist['snap_date'].dt.date <= st_date_end)
        ]
    if selected_brands:
        df_hist = df_hist[df_hist['brand'].isin(selected_brands)]

    # Previous period
    st_delta      = (st_date_end - st_date_start).days if st_date_start and st_date_end else 30
    st_prev_start = st_date_start - timedelta(days=st_delta + 1) if st_date_start else None
    st_prev_end   = st_date_start - timedelta(days=1)            if st_date_start else None
    if st_prev_start and st_prev_end:
        df_hist_prev = df_st_hist[
            (df_st_hist['snap_date'].dt.date >= st_prev_start) &
            (df_st_hist['snap_date'].dt.date <= st_prev_end)
        ]
    else:
        df_hist_prev = pd.DataFrame()

    st.title("Self-Storage Market Tracker")
    date_label_st = f"{st_date_start.strftime('%b %d')} – {st_date_end.strftime('%b %d, %Y')}" if st_date_start else "All Time"
    st.caption(f"Showing data for: **{date_label_st}**")

    total_facilities = df_st['id'].nunique()
    df_pricing       = df_st[df_st['unit_size'] == selected_size]
    avg_unit_price   = df_pricing['web_rate'].mean()
    top_brand        = df_st[['id', 'brand']].drop_duplicates()['brand'].mode()[0] if not df_st.empty else "N/A"
    avail_count      = len(df_pricing[df_pricing['availability'] == 'Available']) if 'availability' in df_pricing.columns else 0

    cur_avg_hist  = df_hist[df_hist['unit_size'] == selected_size]['web_rate'].mean()  if not df_hist.empty      else 0
    prev_avg_hist = df_hist_prev[df_hist_prev['unit_size'] == selected_size]['web_rate'].mean() if not df_hist_prev.empty else 0
    price_delta_str = ""
    if prev_avg_hist and prev_avg_hist > 0 and cur_avg_hist:
        pct   = (cur_avg_hist - prev_avg_hist) / prev_avg_hist * 100
        arrow = "↑" if pct >= 0 else "↓"
        color = "#F44336" if pct >= 0 else "#4CAF50"
        price_delta_str = f"<div style='font-size:12px;margin-top:4px;color:{color};'>{arrow} {abs(pct):.1f}% vs prev period</div>"

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#E91E63;"><div class="kpi-title">Tracked Facilities</div><div class="kpi-value">{total_facilities:,}</div></div>', unsafe_allow_html=True)
    with col2:
        avg_str = f"${avg_unit_price:.2f}" if pd.notnull(avg_unit_price) else "N/A"
        st.markdown(f'<div class="kpi-card" style="border-top-color:#00BCD4;"><div class="kpi-title">Avg {selected_size} Rate</div><div class="kpi-value">{avg_str}</div>{price_delta_str}</div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#FFC107;"><div class="kpi-title">Dominant Brand</div><div class="kpi-value" style="font-size:20px;">{top_brand}</div></div>', unsafe_allow_html=True)
    with col4:
        st.markdown(f'<div class="kpi-card" style="border-top-color:#4CAF50;"><div class="kpi-title">Available ({selected_size})</div><div class="kpi-value">{avail_count:,}</div></div>', unsafe_allow_html=True)

    st.write("---")

    col_map2, col_chart2 = st.columns([2, 1])
    with col_map2:
        st.subheader("📍 Facilities Map")
        df_facilities = df_st.drop_duplicates(subset=['id']).dropna(subset=['latitude', 'longitude'])
        if not df_facilities.empty:
            center_lat, center_lon = df_facilities['latitude'].mean(), df_facilities['longitude'].mean()
            m2 = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles="OpenStreetMap")
            for idx, row in df_facilities.iterrows():
                color = "gray"
                if "Public Storage" in str(row['brand']): color = "orange"
                elif "Extra Space"   in str(row['brand']): color = "green"
                elif "CubeSmart"     in str(row['brand']): color = "red"
                elif "U-Haul"        in str(row['brand']): color = "purple"
                fac_pricing = df_pricing[df_pricing['id'] == row['id']]
                price_str   = f"${fac_pricing.iloc[0]['web_rate']:.0f}" if not fac_pricing.empty and pd.notnull(fac_pricing.iloc[0]['web_rate']) else "N/A"
                popup = f"<b>{row['name']}</b><br>{row['brand']}<br>{selected_size} Price: {price_str}"
                folium.CircleMarker([row['latitude'], row['longitude']], radius=5, popup=folium.Popup(popup, max_width=250), color=color, fill=True, fill_opacity=0.8).add_to(m2)
            st_folium(m2, width=800, height=500, returned_objects=[], key="storage_map")
        else:
            st.info("No storage facilities mapped yet.")

    with col_chart2:
        st.subheader("📈 Pricing by Brand")
        if not df_pricing.empty:
            brand_prices = df_pricing.groupby('brand')['web_rate'].mean().reset_index()
            fig3 = px.bar(brand_prices.sort_values('web_rate', ascending=False),
                          x='brand', y='web_rate', color='brand', template="plotly_dark",
                          title=f"Average {selected_size} Price")
            fig3.update_layout(showlegend=False, margin=dict(l=0, r=0, t=30, b=0), height=450)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info(f"No pricing data available for {selected_size} units.")

    st.write("---")

    # ── Monthly Statistics ───────────────────────────────────────
    st.subheader("📅 Monthly Statistics")
    tab_trend, tab_movement, tab_dist = st.tabs(["📈 Price Trends by Brand", "📊 Price Movement vs. Prev Period", "🥧 Market Share"])

    with tab_trend:
        if not df_hist.empty:
            df_hist_w = df_hist.copy()
            df_hist_w['week'] = df_hist_w['snap_date'].dt.to_period('W').dt.start_time.dt.date
            trend = df_hist_w[df_hist_w['unit_size'] == selected_size].groupby(['week', 'brand'])['web_rate'].mean().reset_index()
            if not trend.empty:
                fig_trend = px.line(trend, x='week', y='web_rate', color='brand', markers=True,
                                    template="plotly_dark", title=f"{selected_size} Avg Price Trend by Brand",
                                    color_discrete_sequence=px.colors.qualitative.Bold)
                fig_trend.update_layout(xaxis_title="Week", yaxis_title="Avg Price ($)",
                                        margin=dict(l=0, r=0, t=40, b=0), height=400)
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info(f"No trend data for {selected_size} in this date range.")
        else:
            st.info("No historical data available for this date range.")

    with tab_movement:
        st.markdown("**Price Movement: Current Period vs. Previous Period**")
        if not df_hist.empty and not df_hist_prev.empty:
            cur_avg_by_size  = df_hist.groupby('unit_size')['web_rate'].mean()
            prev_avg_by_size = df_hist_prev.groupby('unit_size')['web_rate'].mean()
            movement_df = pd.DataFrame({'This Period': cur_avg_by_size, 'Prev Period': prev_avg_by_size}).dropna()
            if not movement_df.empty:
                movement_df['Change ($)'] = movement_df['This Period'] - movement_df['Prev Period']
                movement_df['Change (%)'] = ((movement_df['This Period'] - movement_df['Prev Period']) / movement_df['Prev Period'] * 100).round(1)
                movement_df = movement_df.sort_values('Change (%)', ascending=False).reset_index()
                movement_df.rename(columns={'unit_size': 'Unit Size'}, inplace=True)
                movement_df['This Period'] = movement_df['This Period'].apply(lambda x: f"${x:,.2f}")
                movement_df['Prev Period'] = movement_df['Prev Period'].apply(lambda x: f"${x:,.2f}")
                movement_df['Change ($)']  = movement_df['Change ($)'].apply(lambda x: f"+${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}")
                movement_df['Change (%)']  = movement_df['Change (%)'].apply(lambda x: f"+{x:.1f}%" if x >= 0 else f"{x:.1f}%")
                st.dataframe(movement_df[['Unit Size', 'This Period', 'Prev Period', 'Change ($)', 'Change (%)']], use_container_width=True, height=400)
            else:
                st.info("Not enough overlapping unit sizes to compare between periods.")
        else:
            st.info("Select a date range with at least two periods of data to see price movement.")

    with tab_dist:
        col_hist2, col_pie = st.columns(2)
        with col_hist2:
            if not df_pricing.empty:
                fig_hist = px.histogram(df_pricing, x='web_rate', nbins=20,
                                        title=f"Distribution of {selected_size} Rates",
                                        template="plotly_dark", color_discrete_sequence=['#00BCD4'])
                fig_hist.update_layout(xaxis_title="Price ($)", yaxis_title="Number of Facilities",
                                       margin=dict(l=0, r=0, t=30, b=0), height=350)
                st.plotly_chart(fig_hist, use_container_width=True)
            else:
                st.info("No pricing data available for histogram.")
        with col_pie:
            df_fac_pie = df_st.drop_duplicates(subset=['id'])
            if not df_fac_pie.empty:
                brand_counts = df_fac_pie['brand'].value_counts().reset_index()
                brand_counts.columns = ['brand', 'count']
                fig_pie = px.pie(brand_counts, values='count', names='brand', hole=0.4,
                                 title="Facility Ownership by Brand",
                                 template="plotly_dark",
                                 color_discrete_sequence=px.colors.qualitative.Set3)
                fig_pie.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=350)
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("No facility data available for market share.")

    st.write("---")
    st.subheader("📋 Storage Data Explorer")
    st.dataframe(df_st[['name', 'brand', 'city', 'zip_code', 'unit_size', 'web_rate', 'availability', 'scraped_at']], use_container_width=True)


# =====================================================================
# PAGE 3: DATABASE VIEW
# =====================================================================
elif page == "🗄️ Database View":
    st.sidebar.write("---")
    st.title("🗄️ Raw Database Explorer")

    @st.cache_data(ttl=60)
    def load_full_database():
        conn = sqlite3.connect(config.DB_PATH)
        df = pd.read_sql_query("SELECT * FROM pre_mover_leads", conn)
        conn.close()
        return df

    with st.spinner("Loading complete database..."):
        df_full = load_full_database()

    st.write(f"Showing all **{len(df_full):,}** rows and **{len(df_full.columns)}** columns from the `pre_mover_leads` table.")

    search = st.text_input("Search any column (e.g., zip code, name, status)")
    if search:
        mask = df_full.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
        df_full = df_full[mask]
        st.write(f"Search results: {len(df_full):,} rows")

    st.dataframe(df_full, use_container_width=True, height=800)
