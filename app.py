import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Amazon Order Analysis", layout="wide")

st.title("📦 Amazon Order History Analysis")

# Configuration for data path (can be overridden by env var for Docker)
DATA_DIR = os.getenv("DATA_DIR", "data/Your Amazon Orders")
ORDER_HISTORY_FILE = os.path.join(DATA_DIR, "Order History.csv")


def _categorize(name):
    name = str(name).lower()
    if any(kw in name for kw in ['炭酸水', '水', '茶', 'コーヒー', '食品', '飲料', 'food', 'drink', 'sanpellegrino']):
        return 'Groceries'
    if any(kw in name for kw in ['iphone', 'usb', 'ケーブル', 'battery', 'バッテリー', 'electronics', 'はんだごて', 'pc']):
        return 'Electronics'
    if any(kw in name for kw in ['本', 'book', 'kindle', 'magazine', 'edition']):
        return 'Books'
    if any(kw in name for kw in ['服', 'shoes', 'shirt', 'clothing', 'バッグ']):
        return 'Clothing'
    if any(kw in name for kw in ['洗剤', 'shampoo', 'soap', 'beauty', 'cosmetic']):
        return 'Health & Beauty'
    return 'Other'


def _normalize_amount(series):
    # pandas 3.0 made Arrow-backed strings the default dtype, so a dtype==object
    # check would skip parsing and leave commas in the values. Always coerce.
    cleaned = series.astype(str).str.replace(r'[¥$,\s]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0)


@st.cache_data
def load_and_clean_data(physical_path):
    if not os.path.exists(physical_path):
        return None
    df = pd.read_csv(physical_path)
    df = df[df['Order Status'] != 'Cancelled'].copy()
    df['Order Date'] = pd.to_datetime(df['Order Date'], utc=True).dt.tz_convert(None)
    df['Total Amount'] = _normalize_amount(df['Total Amount'])
    df['Year'] = df['Order Date'].dt.year
    df['Month'] = df['Order Date'].dt.month
    df['Category'] = df['Product Name'].apply(_categorize)
    return df


df = load_and_clean_data(ORDER_HISTORY_FILE)

if df is not None:
    # Sidebar filters
    years = sorted(df['Year'].unique().tolist(), reverse=True)
    selected_year = st.sidebar.selectbox("Select Year for Details", ["All"] + years)

    if selected_year != "All":
        display_df = df[df['Year'] == selected_year]
    else:
        display_df = df

    # Metrics
    col1, col2, col3 = st.columns(3)
    total_spent = display_df['Total Amount'].sum()
    total_items = len(display_df)
    avg_per_item = total_spent / total_items if total_items > 0 else 0
    
    col1.metric("Total Spent", f"¥{total_spent:,.0f}")
    col2.metric("Total Items", f"{total_items}")
    col3.metric("Avg per Item", f"¥{avg_per_item:,.0f}")

    # Charts
    st.subheader("Spending over Time")
    if selected_year == "All":
        yearly_spending = display_df.groupby('Year')['Total Amount'].sum().reset_index()
        fig = px.bar(yearly_spending, x='Year', y='Total Amount',
                     title="Yearly Spending", labels={'Total Amount': 'Total Spent (¥)'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        monthly_spending = display_df.groupby('Month')['Total Amount'].sum().reset_index()
        fig = px.line(monthly_spending, x='Month', y='Total Amount',
                      title=f"Monthly Spending in {selected_year}",
                      labels={'Total Amount': 'Total Spent (¥)'}, markers=True)
        st.plotly_chart(fig, use_container_width=True)

    # Year-over-year comparison
    st.subheader("Year-over-Year Comparison")
    yoy = display_df.groupby('Year').agg(
        total_spent=('Total Amount', 'sum'),
        orders=('Order ID', 'nunique'),
    ).reset_index().sort_values('Year')
    yoy['YoY % Spending'] = yoy['total_spent'].pct_change() * 100
    yoy['YoY % Orders'] = yoy['orders'].pct_change() * 100
    yoy_display = yoy.copy()
    yoy_display['total_spent'] = yoy_display['total_spent'].map(lambda v: f"¥{v:,.0f}")
    yoy_display['YoY % Spending'] = yoy_display['YoY % Spending'].map(lambda v: "—" if pd.isna(v) else f"{v:+.1f}%")
    yoy_display['YoY % Orders'] = yoy_display['YoY % Orders'].map(lambda v: "—" if pd.isna(v) else f"{v:+.1f}%")
    st.dataframe(yoy_display, hide_index=True, use_container_width=True)

    # Category Analysis
    st.subheader("Category Analysis")
    col_cat_left, col_cat_right = st.columns(2)
    
    with col_cat_left:
        st.write("Spending by Category")
        cat_spending = display_df.groupby('Category')['Total Amount'].sum().sort_values(ascending=False).reset_index()
        fig_cat_spend = px.pie(cat_spending, values='Total Amount', names='Category', title="Spending Distribution")
        st.plotly_chart(fig_cat_spend, use_container_width=True)
        
    with col_cat_right:
        st.write("Orders by Category")
        cat_freq = display_df['Category'].value_counts().reset_index()
        cat_freq.columns = ['Category', 'Count']
        fig_cat_freq = px.pie(cat_freq, values='Count', names='Category', title="Order Distribution")
        st.plotly_chart(fig_cat_freq, use_container_width=True)

    # Top Products
    st.subheader("Top Products")
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.write("Top 10 by Spending")
        top_spending = display_df.groupby('Product Name')['Total Amount'].sum().sort_values(ascending=False).head(10).reset_index()
        fig_spending = px.bar(top_spending, x='Total Amount', y='Product Name', orientation='h',
                              labels={'Total Amount': 'Total Spent (¥)', 'Product Name': ''})
        fig_spending.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_spending, use_container_width=True)
        
    with col_right:
        st.write("Top 10 by Frequency")
        top_freq = display_df['Product Name'].value_counts().head(10).reset_index()
        top_freq.columns = ['Product Name', 'Count']
        fig_freq = px.bar(top_freq, x='Count', y='Product Name', orientation='h',
                          labels={'Count': 'Number of Orders', 'Product Name': ''})
        fig_freq.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_freq, use_container_width=True)

    # Data Table
    with st.expander("Show Raw Data"):
        st.dataframe(display_df[['Order Date', 'Product Name', 'Category', 'Total Amount', 'Order Status']])

else:
    st.error(f"Could not find the data file at {ORDER_HISTORY_FILE}. Please check the volume mapping.")
    st.info("Ensure your 'Your Orders' directory is mounted to the container.")
