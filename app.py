import streamlit as st
import pandas as pd
import plotly.express as px
import os
import re
import yaml

st.set_page_config(page_title="My Amazon Spending", layout="wide")

st.title("📦 My Amazon Spending")

# Configuration for data path (can be overridden by env var for Docker)
DATA_DIR = os.getenv("DATA_DIR", "data/Your Amazon Orders")
ORDER_HISTORY_FILE = os.path.join(DATA_DIR, "Order History.csv")
DIGITAL_ORDERS_FILE = os.path.join(DATA_DIR, "Digital Content Orders.csv")
# Refund Details.csv lives in a sibling folder of DATA_DIR
ORDERS_ROOT = os.path.dirname(DATA_DIR.rstrip('/')) or "."
REFUNDS_FILE = os.path.join(ORDERS_ROOT, "Your Returns & Refunds", "Refund Details.csv")


CATEGORIES_FILE = os.getenv("CATEGORIES_FILE", "categories.yaml")

# Pin Source colors so Physical stays its default blue when the digital toggle
# is on. Without this map, Plotly assigns colors in alphabetical order and
# Physical shifts.
SOURCE_COLORS = {
    "Physical": px.colors.qualitative.Plotly[0],
    "Digital": px.colors.qualitative.Plotly[1],
}


@st.cache_data
def _load_category_rules(path):
    """Load `{category: [keywords]}` mapping from YAML. Order is priority."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def _categorize_series(names: pd.Series, rules: dict) -> pd.Series:
    """Vectorized categorization: one compiled regex per category, first match wins."""
    result = pd.Series('Other', index=names.index, dtype='object')
    unassigned = pd.Series(True, index=names.index)
    lowered = names.fillna('').astype(str).str.lower()

    for category, keywords in rules.items():
        if not keywords:
            continue
        pattern = '|'.join(re.escape(str(k).lower()) for k in keywords)
        matches = lowered.str.contains(pattern, regex=True, na=False)
        to_assign = matches & unassigned
        result[to_assign] = category
        unassigned &= ~matches
        if not unassigned.any():
            break

    return result


def _normalize_amount(series):
    # pandas 3.0 made Arrow-backed strings the default dtype, so a dtype==object
    # check would skip parsing and leave commas in the values. Always coerce.
    cleaned = series.astype(str).str.replace(r'[¥$,\s]', '', regex=True)
    return pd.to_numeric(cleaned, errors='coerce').fillna(0)


def _load_physical(path):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df = df[df['Order Status'] != 'Cancelled'].copy()
    return pd.DataFrame({
        'Order Date': pd.to_datetime(df['Order Date'], utc=True, format='ISO8601').dt.tz_convert(None),
        'Order ID': df['Order ID'],
        'Product Name': df['Product Name'],
        'Order Status': df['Order Status'],
        'Total Amount': _normalize_amount(df['Total Amount']),
        'Source': 'Physical',
    })


def _load_digital(path):
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    df = df[df['Order Status'] == 'SUCCESS'].copy()
    return pd.DataFrame({
        'Order Date': pd.to_datetime(df['Order Date'], utc=True, format='ISO8601').dt.tz_convert(None),
        'Order ID': df['Order ID'],
        'Product Name': df['Product Name'],
        'Order Status': df['Order Status'],
        'Total Amount': _normalize_amount(df['Transaction Amount']),
        'Source': 'Digital',
    })


def _load_cancelled(path):
    """Cancelled rows from Order History — for display only, not counted."""
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df = df[df['Order Status'] == 'Cancelled'].copy()
    if df.empty:
        return df
    return pd.DataFrame({
        'Order Date': pd.to_datetime(df['Order Date'], utc=True, format='ISO8601').dt.tz_convert(None),
        'Order ID': df['Order ID'],
        'Product Name': df['Product Name'],
    }).assign(Year=lambda d: d['Order Date'].dt.year)


def _load_refunds(path, physical_path):
    """Refunds with product name joined from Order History when available."""
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df['Refund Amount'] = _normalize_amount(df['Refund Amount'])
    df = df[df['Refund Amount'] > 0].copy()
    if df.empty:
        return df
    refund_date = pd.to_datetime(df['Refund Date'], utc=True, format='ISO8601', errors='coerce').dt.tz_convert(None)

    products = {}
    if os.path.exists(physical_path):
        physical = pd.read_csv(physical_path)
        products = physical.drop_duplicates('Order ID').set_index('Order ID')['Product Name'].to_dict()

    return pd.DataFrame({
        'Refund Date': refund_date,
        'Order ID': df['Order ID'],
        'Refund Amount': df['Refund Amount'],
        'Product Name': df['Order ID'].map(products).fillna('—'),
        'Year': refund_date.dt.year,
    })


@st.cache_data
def load_and_clean_data(physical_path, digital_path, refunds_path):
    parts = [p for p in (_load_physical(physical_path), _load_digital(digital_path)) if p is not None]
    main_df = None
    if parts:
        main_df = pd.concat(parts, ignore_index=True)
        main_df['Year'] = main_df['Order Date'].dt.year
        main_df['Month'] = main_df['Order Date'].dt.month
        main_df['Category'] = _categorize_series(main_df['Product Name'], _load_category_rules(CATEGORIES_FILE))

    cancelled_df = _load_cancelled(physical_path)
    refunds_df = _load_refunds(refunds_path, physical_path)
    return main_df, cancelled_df, refunds_df


df, cancelled_df, refunds_df = load_and_clean_data(
    ORDER_HISTORY_FILE, DIGITAL_ORDERS_FILE, REFUNDS_FILE
)

if df is not None:
    # Sidebar filters
    years = sorted(df['Year'].unique().tolist(), reverse=True)
    selected_year = st.sidebar.selectbox("Select Year for Details", ["All"] + years)

    has_digital = (df['Source'] == 'Digital').any()
    include_digital = has_digital and st.sidebar.toggle(
        "Include digital content",
        value=False,
        help="Adds Prime renewals, Kindle, Audible and other digital purchases "
             "from Digital Content Orders.csv. Off by default — digital is "
             "typically <5% of spend and inflates row counts due to "
             "per-payment-method splits.",
    )

    display_df = df if include_digital else df[df['Source'] == 'Physical']
    if selected_year != "All":
        display_df = display_df[display_df['Year'] == selected_year]

    # Metrics
    col1, col2, col3 = st.columns(3)
    total_spent = display_df['Total Amount'].sum()
    total_items = len(display_df)
    avg_per_item = total_spent / total_items if total_items > 0 else 0
    
    col1.metric("Total Spent", f"¥{total_spent:,.0f}")
    col2.metric("Total Items", f"{total_items}")
    col3.metric("Avg per Item", f"¥{avg_per_item:,.0f}")

    # Charts — split bars/lines by Source when digital is included
    st.subheader("Spending over Time")
    split_by_source = include_digital and display_df['Source'].nunique() > 1
    color_arg = 'Source' if split_by_source else None
    if selected_year == "All":
        group_cols = ['Year', 'Source'] if split_by_source else ['Year']
        yearly_spending = display_df.groupby(group_cols)['Total Amount'].sum().reset_index()
        fig = px.bar(yearly_spending, x='Year', y='Total Amount', color=color_arg,
                     color_discrete_map=SOURCE_COLORS,
                     title="Yearly Spending", labels={'Total Amount': 'Total Spent (¥)'})
        st.plotly_chart(fig, use_container_width=True)
    else:
        group_cols = ['Month', 'Source'] if split_by_source else ['Month']
        monthly_spending = display_df.groupby(group_cols)['Total Amount'].sum().reset_index()
        fig = px.line(monthly_spending, x='Month', y='Total Amount', color=color_arg,
                      color_discrete_map=SOURCE_COLORS,
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

    # What's in "Other"? — helps the user grow categories.yaml
    other_df = display_df[display_df['Category'] == 'Other']
    if not other_df.empty:
        st.subheader('What\'s in "Other"?')
        pct = 100 * len(other_df) / len(display_df)
        st.caption(
            f"{len(other_df):,} of {len(display_df):,} items ({pct:.1f}%) didn't "
            f"match any rule. Spot recurring terms and add them to "
            f"`categories.yaml` to shrink this bucket."
        )
        other_summary = (
            other_df.groupby('Product Name')
            .agg(Orders=('Total Amount', 'size'), Spent=('Total Amount', 'sum'))
            .sort_values('Spent', ascending=False)
            .head(20)
            .reset_index()
        )
        other_summary['Spent'] = other_summary['Spent'].map(lambda v: f"¥{v:,.0f}")
        st.dataframe(other_summary, hide_index=True, use_container_width=True)

    # Data Table
    with st.expander("Show Raw Data"):
        raw_cols = ['Order Date', 'Product Name', 'Category', 'Total Amount', 'Order Status']
        if has_digital:
            raw_cols.insert(1, 'Source')
        st.dataframe(display_df[raw_cols])

    # Returned & Cancelled — informational only, not included in totals above
    has_cancelled = not cancelled_df.empty
    has_refunds = not refunds_df.empty
    if has_cancelled or has_refunds:
        st.subheader("Returned & Cancelled")
        st.caption("These are not counted in the totals or charts above.")

        if selected_year != "All":
            cancelled_view = cancelled_df[cancelled_df['Year'] == selected_year] if has_cancelled else cancelled_df
            refunds_view = refunds_df[refunds_df['Year'] == selected_year] if has_refunds else refunds_df
        else:
            cancelled_view = cancelled_df
            refunds_view = refunds_df

        col_c, col_r = st.columns(2)
        with col_c:
            st.metric("Cancelled Orders", len(cancelled_view))
            if has_cancelled:
                with st.expander(f"View cancelled ({len(cancelled_view)})"):
                    st.dataframe(
                        cancelled_view[['Order Date', 'Product Name', 'Order ID']],
                        hide_index=True, use_container_width=True,
                    )
        with col_r:
            total_refunded = refunds_view['Refund Amount'].sum() if has_refunds else 0
            st.metric(
                "Refunded",
                f"¥{total_refunded:,.0f}",
                help=f"{len(refunds_view)} refund{'s' if len(refunds_view) != 1 else ''}",
            )
            if has_refunds:
                with st.expander(f"View refunds ({len(refunds_view)})"):
                    st.dataframe(
                        refunds_view[['Refund Date', 'Product Name', 'Order ID', 'Refund Amount']],
                        hide_index=True, use_container_width=True,
                    )

else:
    st.error(f"Could not find any order CSVs in {DATA_DIR}. Expected 'Order History.csv' and/or 'Digital Content Orders.csv'.")
    st.info("Ensure your 'data/' directory is mounted to the container.")
