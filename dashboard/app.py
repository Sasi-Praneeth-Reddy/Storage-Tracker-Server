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
               latitude, longitude, scraped_at
        FROM pre_mover_leads
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    df['list_price'] = pd.to_numeric(df['list_price'], errors='coerce')
    df['sqft'] = pd.to_numeric(df['sqft'], errors='coerce')
    return df

@st.cache_data(ttl=60)
def load_storage_data():
    conn = sqlite3.connect(config.DB_PATH)
    # Join facilities with latest pricing
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
    return df

with st.spinner("Loading market data..."):
    df_re_raw = load_real_estate_data()
    df_st_raw = load_storage_data()

# Initialize session state for filters to survive page navigation
if 're_statuses' not in st.session_state: st.session_state.re_statuses = None
if 're_states' not in st.session_state: st.session_state.re_states = None
if 're_counties' not in st.session_state: st.session_state.re_counties = None
if 're_price' not in st.session_state: st.session_state.re_price = None

if 'st_brands' not in st.session_state: st.session_state.st_brands = None
if 'st_size' not in st.session_state: st.session_state.st_size = None

# Create navigation for the dashboard
page = st.sidebar.radio("Navigation", ["🏡 Real Estate Market", "📦 Self-Storage Market", "🗄️ Database View"])

# =====================================================================
# PAGE 1: REAL ESTATE MARKET
# =====================================================================
if page == "🏡 Real Estate Market":
    st.sidebar.write("---")
    st.sidebar.header("🏡 Real Estate Filters")
    # Status filter
    statuses = df_re_raw['status'].dropna().unique().tolist()
    default_statuses = st.session_state.re_statuses if st.session_state.re_statuses is not None else statuses
    valid_statuses = [s for s in default_statuses if s in statuses]
    selected_statuses = st.sidebar.multiselect("Listing Status", options=statuses, default=valid_statuses)
    st.session_state.re_statuses = selected_statuses

    # State filter
    states = sorted(df_re_raw['state'].dropna().unique().tolist())
    default_states = st.session_state.re_states if st.session_state.re_states is not None else states
    valid_states = [s for s in default_states if s in states]
    selected_states = st.sidebar.multiselect("States", options=states, default=valid_states)
    st.session_state.re_states = selected_states

    # County filter
    counties = sorted(df_re_raw['county'].dropna().unique().tolist())
    default_counties = st.session_state.re_counties if st.session_state.re_counties is not None else counties
    valid_counties = [c for c in default_counties if c in counties]
    selected_counties = st.sidebar.multiselect("Counties", options=counties, default=valid_counties)
    st.session_state.re_counties = selected_counties

    # Price filter
    min_price = float(df_re_raw['list_price'].min()) if not df_re_raw['list_price'].empty else 0.0
    max_price = float(df_re_raw['list_price'].max()) if not df_re_raw['list_price'].empty else 5000000.0
    default_price = st.session_state.re_price if st.session_state.re_price is not None else (min_price, max_price)
    price_range = st.sidebar.slider("Price Range ($)", min_value=min_price, max_value=max_price, value=default_price)
    st.session_state.re_price = price_range

    df_re = df_re_raw[
        (df_re_raw['status'].isin(selected_statuses)) &
        (df_re_raw['list_price'] >= price_range[0]) &
        (df_re_raw['list_price'] <= price_range[1])
    ]
    if selected_states:
        df_re = df_re[df_re['state'].isin(selected_states)]
    if selected_counties:
        df_re = df_re[df_re['county'].isin(selected_counties)]

    st.title("Regional MLS Market")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f'<div class="kpi-card"><div class="kpi-title">Total Listings</div><div class="kpi-value">{len(df_re):,}</div></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="kpi-card" style="border-top-color: #2196F3;"><div class="kpi-title">Active (For Sale)</div><div class="kpi-value">{len(df_re[df_re["status"] == "for_sale"]):,}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="kpi-card" style="border-top-color: #FF9800;"><div class="kpi-title">Under Contract</div><div class="kpi-value">{len(df_re[df_re["status"] == "under_contract"]):,}</div></div>', unsafe_allow_html=True)
    with col4:
        avg_price = df_re['list_price'].mean()
        avg_price_str = f"${avg_price:,.0f}" if pd.notnull(avg_price) else "N/A"
        st.markdown(f'<div class="kpi-card" style="border-top-color: #9C27B0;"><div class="kpi-title">Avg List Price</div><div class="kpi-value">{avg_price_str}</div></div>', unsafe_allow_html=True)
    with col5:
        status_changed = len(df_re[df_re['previous_status'].notna()])
        st.markdown(f'<div class="kpi-card" style="border-top-color: #F44336;"><div class="kpi-title">Status Changed</div><div class="kpi-value">{status_changed:,}</div></div>', unsafe_allow_html=True)

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
            fig2.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=240)
            st.plotly_chart(fig2, use_container_width=True)

    st.write("---")

    # ── Daily Houses Added Line Chart ─────────────────────────────
    st.subheader("📈 Total Houses Added (Weekly)")
    if not df_re.empty and 'scraped_at' in df_re.columns:
        # Group by week to show chunks (~4 points per month)
        df_re['date_added'] = pd.to_datetime(df_re['scraped_at']).dt.to_period('W').dt.start_time.dt.date
        daily_counts = df_re.groupby('date_added').size().reset_index(name='Total Added')
        
        fig_line = px.line(
            daily_counts, x='date_added', y='Total Added', 
            markers=True, template="plotly_dark"
        )
        fig_line.update_layout(
            xaxis_title="Date",
            yaxis_title="Houses Added",
            margin=dict(l=0, r=0, t=10, b=0),
            height=300
        )
        fig_line.update_traces(line_color="#4CAF50")
        st.plotly_chart(fig_line, use_container_width=True)

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
            fig_trans = px.bar(
                trans_counts, x='Count', y='Transition', orientation='h',
                color='Count', color_continuous_scale='Reds', template='plotly_dark',
                title='Status Transitions'
            )
            fig_trans.update_layout(
                yaxis={'categoryorder': 'total ascending'},
                showlegend=False,
                margin=dict(l=0, r=0, t=30, b=0),
                height=300
            )
            st.plotly_chart(fig_trans, use_container_width=True)
        
        with col_trans_table:
            display_changed = df_changed[[
                'address', 'city', 'county', 'zip_code',
                'previous_status', 'status', 'list_price', 'status_updated_at'
            ]].rename(columns={
                'previous_status': 'Old Status',
                'status': 'New Status',
                'list_price': 'Price',
                'status_updated_at': 'Changed On'
            })
            st.dataframe(display_changed, use_container_width=True, height=300)
    else:
        st.info("No status changes detected yet. Run the exporter again to track transitions.")

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
    pid_file = pathlib.Path('.scraper_pid')
    
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
                        import os
                        import signal
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
            import threading
            import subprocess
            import sys
            
            def bg_run():
                try:
                    process = subprocess.Popen(
                        [sys.executable, "-c", "from collectors.run_all import run_self_storage; run_self_storage(dry_run=False)"]
                    )
                    pid_file.write_text(str(process.pid))
                    process.wait()
                finally:
                    if status_file.exists():
                        status_file.unlink()
                    if pid_file.exists():
                        pid_file.unlink()
            threading.Thread(target=bg_run, daemon=True).start()
            st.rerun()
            
    st.sidebar.write("---")
    
    brands = sorted(df_st_raw['brand'].dropna().unique().tolist())
    default_brands = st.session_state.st_brands if st.session_state.st_brands is not None else brands
    valid_brands = [b for b in default_brands if b in brands]
    selected_brands = st.sidebar.multiselect("Storage Brands", options=brands, default=valid_brands)
    st.session_state.st_brands = selected_brands
    
    unit_sizes = sorted(df_st_raw['unit_size'].dropna().unique().tolist())
    if not unit_sizes:
        unit_sizes = ["10x10"]
    default_size = st.session_state.st_size if st.session_state.st_size in unit_sizes else unit_sizes[0]
    selected_size = st.sidebar.selectbox("Unit Size to Compare", options=unit_sizes, index=unit_sizes.index(default_size))
    st.session_state.st_size = selected_size

    # Filter storage data
    if selected_brands:
        df_st = df_st_raw[df_st_raw['brand'].isin(selected_brands)]
    else:
        df_st = df_st_raw.copy()
    
    st.title("Self-Storage Market Tracker")
    
    # Calculate KPIs
    # Unique facilities
    total_facilities = df_st['id'].nunique()
    
    # Avg price for selected unit size
    df_pricing = df_st[df_st['unit_size'] == selected_size]
    avg_unit_price = df_pricing['web_rate'].mean()
    
    # Top brand by facility count
    if not df_st.empty:
        top_brand = df_st[['id', 'brand']].drop_duplicates()['brand'].mode()[0]
    else:
        top_brand = "N/A"
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f'<div class="kpi-card" style="border-top-color: #E91E63;"><div class="kpi-title">Tracked Facilities</div><div class="kpi-value">{total_facilities:,}</div></div>', unsafe_allow_html=True)
    with col2:
        avg_str = f"${avg_unit_price:.2f}" if pd.notnull(avg_unit_price) else "N/A"
        st.markdown(f'<div class="kpi-card" style="border-top-color: #00BCD4;"><div class="kpi-title">Avg {selected_size} Rate</div><div class="kpi-value">{avg_str}</div></div>', unsafe_allow_html=True)
    with col3:
        st.markdown(f'<div class="kpi-card" style="border-top-color: #FFC107;"><div class="kpi-title">Dominant Brand</div><div class="kpi-value">{top_brand}</div></div>', unsafe_allow_html=True)
        
    st.write("---")
    
    col_map2, col_chart2 = st.columns([2, 1])
    with col_map2:
        st.subheader("📍 Facilities Map")
        # For map, just use one row per facility
        df_facilities = df_st.drop_duplicates(subset=['id']).dropna(subset=['latitude', 'longitude'])
        if not df_facilities.empty:
            center_lat, center_lon = df_facilities['latitude'].mean(), df_facilities['longitude'].mean()
            m2 = folium.Map(location=[center_lat, center_lon], zoom_start=9, tiles="OpenStreetMap")
            
            for idx, row in df_facilities.iterrows():
                # Color code by brand (Public Storage = orange, Extra Space = green, CubeSmart = red, Independent = gray)
                color = "gray"
                if "Public Storage" in row['brand']: color = "orange"
                elif "Extra Space" in row['brand']: color = "green"
                elif "CubeSmart" in row['brand']: color = "red"
                elif "U-Haul" in row['brand']: color = "purple"
                
                # Try to find price for this facility
                fac_pricing = df_pricing[df_pricing['id'] == row['id']]
                price_str = f"${fac_pricing.iloc[0]['web_rate']:.0f}" if not fac_pricing.empty and pd.notnull(fac_pricing.iloc[0]['web_rate']) else "N/A"
                
                popup = f"<b>{row['name']}</b><br>{row['brand']}<br>{selected_size} Price: {price_str}"
                folium.CircleMarker([row['latitude'], row['longitude']], radius=5, popup=folium.Popup(popup, max_width=250), color=color, fill=True, fill_opacity=0.8).add_to(m2)
            st_folium(m2, width=800, height=500, returned_objects=[], key="storage_map")
        else:
            st.info("No storage facilities mapped yet.")
            
    with col_chart2:
        st.subheader("📈 Pricing by Brand")
        if not df_pricing.empty:
            brand_prices = df_pricing.groupby('brand')['web_rate'].mean().reset_index()
            fig3 = px.bar(brand_prices.sort_values('web_rate', ascending=False), x='brand', y='web_rate', color='brand', template="plotly_dark", title=f"Average {selected_size} Price")
            fig3.update_layout(showlegend=False, margin=dict(l=0, r=0, t=30, b=0), height=450)
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info(f"No pricing data available for {selected_size} units.")

    st.write("---")
    
    col_hist, col_pie = st.columns(2)
    with col_hist:
        st.subheader(f"📊 Price Distribution ({selected_size})")
        if not df_pricing.empty:
            fig_hist = px.histogram(
                df_pricing, x='web_rate', nbins=20, 
                title=f"Distribution of {selected_size} Rates",
                template="plotly_dark", color_discrete_sequence=['#00BCD4']
            )
            fig_hist.update_layout(xaxis_title="Price ($)", yaxis_title="Number of Facilities", margin=dict(l=0, r=0, t=30, b=0), height=350)
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("No pricing data available for histogram.")
            
    with col_pie:
        st.subheader("🥧 Brand Market Share")
        if not df_facilities.empty:
            brand_counts = df_facilities['brand'].value_counts().reset_index()
            brand_counts.columns = ['brand', 'count']
            fig_pie = px.pie(
                brand_counts, values='count', names='brand', hole=0.4,
                title="Facility Ownership by Brand",
                template="plotly_dark", color_discrete_sequence=px.colors.qualitative.Set3
            )
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
        # Simple text search across all string columns
        mask = df_full.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
        df_full = df_full[mask]
        st.write(f"Search results: {len(df_full):,} rows")

    st.dataframe(df_full, use_container_width=True, height=800)
