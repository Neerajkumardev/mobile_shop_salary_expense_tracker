import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import pandas as pd
import calendar
from datetime import datetime
from fpdf import FPDF
import io
import json

# --- 1. FIREBASE CONNECTION (STRICT REPAIR VERSION) ---
def init_firebase():
    if not firebase_admin._apps:
        try:
            # Load the JSON file from your GitHub repository
            with open("firebase_key.json", "r") as f:
                key_data = json.load(f)
            
            # THE CRITICAL FIX: Ensures the private key has real newlines
            # This solves the 'RefreshError' and 'Invalid JWT' on Cloud servers
            if "private_key" in key_data:
                key_data["private_key"] = key_data["private_key"].replace("\\n", "\n")
            
            cred = credentials.Certificate(key_data)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://abcsalarytracker-default-rtdb.firebaseio.com/'
            })
        except Exception as e:
            st.error(f"Cloud Connection Failed: {e}")

# Run initialization
init_firebase()

# --- 2. PDF GENERATION FUNCTION ---
def create_pdf(shop_name, month, year, staff_results, shop_results, total_sales, total_out, profit):
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, f"{shop_name.upper()}", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(190, 10, f"Monthly Statement: {month} {year}", ln=True, align='C')
    pdf.ln(10)
    
    # Table Header
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(130, 10, "Description", 1, 0, 'L', True)
    pdf.cell(60, 10, "Amount (INR)", 1, 1, 'R', True)
    
    # Data Rows
    pdf.set_font("Arial", '', 11)
    for s in staff_results:
        pdf.cell(130, 10, f"{s['Name']} (Sal: {s['Salary']} + Inc: {s['Incentive']})", 1)
        pdf.cell(60, 10, f"{s['Total']:,}", 1, 1, 'R')
        
    for e in shop_results:
        pdf.cell(130, 10, f"{e['Item']}", 1)
        pdf.cell(60, 10, f"{e['Amount']:,}", 1, 1, 'R')
        
    # Totals Section
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(130, 10, "TOTAL EXPENSES", 0)
    pdf.cell(60, 10, f"{total_out:,.0f}", 0, 1, 'R')
    pdf.cell(130, 10, "TOTAL SALES", 0)
    pdf.cell(60, 10, f"{total_sales:,.0f}", 0, 1, 'R')
    
    pdf.set_text_color(200, 0, 0) # Red for Profit
    pdf.cell(130, 10, "NET PROFIT", 0)
    pdf.cell(60, 10, f"{profit:,.0f}", 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 3. PAGE CONFIG & SIDEBAR ---
st.set_page_config(page_title="Mobile Shop Pro", layout="wide")

st.sidebar.title("🏪 Store Selection")
current_shop = st.sidebar.selectbox("Select Shop", ["Shop 1", "Shop 2"])
shop_id = current_shop.replace(" ", "_")

if st.sidebar.button("🔄 Refresh Application"):
    st.rerun()

# --- 4. DATE SELECTION ---
st.title(f"📱 {current_shop} Management System")
col_m1, col_m2 = st.columns(2)
with col_m1:
    selected_year = st.selectbox("Select Year", range(2024, 2031), index=1)
with col_m2:
    months = list(calendar.month_name)[1:]
    selected_month_name = st.selectbox("Select Month", months, index=datetime.now().month - 1)

month_num = list(calendar.month_name).index(selected_month_name)
days_in_month = calendar.monthrange(selected_year, month_num)[1]

tab1, tab2, tab3 = st.tabs(["⚙️ Setup", "📄 Monthly Report", "📈 History"])

# --- TAB 1: SETUP ---
with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Staff Master Data")
        staff_ref = db.reference(f'staff/{shop_id}')
        staff_data = staff_ref.get()
        staff_df = pd.DataFrame(staff_data) if staff_data else pd.DataFrame(columns=['name', 'salary', 'inc_percent'])
        
        edited_staff = st.data_editor(staff_df, num_rows="dynamic", width='stretch', key=f"edit_st_{shop_id}")
        if st.button("Update Staff Cloud", key=f"up_st_{shop_id}"):
            staff_ref.set(edited_staff.to_dict('records'))
            st.success("Cloud Updated!")

    with col_b:
        st.subheader("Fixed Shop Expenses")
        exp_ref = db.reference(f'expenses/{shop_id}')
        exp_data = exp_ref.get()
        exp_df = pd.DataFrame(exp_data) if exp_data else pd.DataFrame(columns=['item_name', 'default_amount'])
        
        edited_exp = st.data_editor(exp_df, num_rows="dynamic", width='stretch', key=f"edit_ex_{shop_id}")
        if st.button("Update Expenses Cloud", key=f"up_ex_{shop_id}"):
            exp_ref.set(edited_exp.to_dict('records'))
            st.success("Cloud Updated!")

# --- TAB 2: MONTHLY REPORT ---
with tab2:
    st.header(f"Calculations for {selected_month_name} {selected_year}")
    
    staff_ref = db.reference(f'staff/{shop_id}')
    current_staff = staff_ref.get()
    
    total_staff_cost = 0
    staff_results = []

    if current_staff:
        st.subheader("1. Staff Payouts")
        staff_list = current_staff if isinstance(current_staff, list) else current_staff.values()
        
        for row in staff_list:
            if row and isinstance(row, dict) and 'name' in row:
                with st.expander(f"Calculate {row['name']}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    unique_key = f"{shop_id}_{selected_month_name}_{row['name']}"
                    
                    leaves = c1.number_input(f"Leaves", 0, days_in_month, key=f"L_{unique_key}")
                    service = c2.number_input(f"Service Amt", 0.0, key=f"S_{unique_key}")
                    
                    sal_val = float(row.get('salary', 0))
                    inc_val = float(row.get('inc_percent', 0))
                    
                    calc_sal = (sal_val / days_in_month) * (days_in_month - leaves)
                    calc_inc = service * (inc_val / 100)
                    total_p = calc_sal + calc_inc
                    
                    total_staff_cost += total_p
                    staff_results.append({"Name": row['name'], "Salary": round(calc_sal), "Incentive": round(calc_inc), "Total": round(total_p)})
                    
                    c3.write(f"Salary: {calc_sal:,.0f}")
                    c3.write(f"Inc ({inc_val}%): {calc_inc:,.0f}")
                    c3.metric("Net Payout", f"{total_p:,.0f}")

    st.divider()
    exp_ref = db.reference(f'expenses/{shop_id}')
    exp_data = exp_ref.get()
    total_shop_exp = 0
    shop_results = []
    if exp_data:
        st.subheader("2. Shop Monthly Bills")
        exp_list = exp_data if isinstance(exp_data, list) else exp_data.values()
        cols = st.columns(3)
        for i, row in enumerate(exp_list):
            if row and isinstance(row, dict):
                exp_key = f"EXP_{shop_id}_{selected_month_name}_{row['item_name']}"
                amt = cols[i%3].number_input(row['item_name'], value=float(row.get('default_amount', 0)), key=exp_key)
                total_shop_exp += amt
                shop_results.append({"Item": row['item_name'], "Amount": amt})

    st.divider()
    total_sales = st.number_input(f"TOTAL SALES ({current_shop})", 0.0, key=f"sales_val_{shop_id}_{selected_month_name}")
    total_out = total_staff_cost + total_shop_exp
    profit = total_sales - total_out
    
    st.info(f"Summary: Staff {total_staff_cost:,.0f} + Bills {total_shop_exp:,.0f} = Total Expenses {total_out:,.0f}")
    st.metric("NET PROFIT", f"{profit:,.0f}")

    b1, b2, b3 = st.columns(3)
    if b1.button("💾 Save Cloud History", key=f"save_{shop_id}"):
        hist_ref = db.reference(f'history/{shop_id}/{selected_month_name}_{selected_year}')
        hist_ref.set({"sales": total_sales, "expenses": total_out, "profit": profit})
        st.success("Saved to Cloud!")

    if b2.button("🖨️ View Print Table", key=f"view_{shop_id}"):
        html = f"""<div style="background-color: white; color: black; padding: 20px; border: 2px solid black; font-family: Arial;">
            <h2 style="text-align: center;">{current_shop.upper()}</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr style="background-color: #eee;"><th style="border: 1px solid black; padding: 8px;">Description</th><th style="border: 1px solid black; padding: 8px; text-align: right;">Amount</th></tr>"""
        for s in staff_results:
            html += f"<tr><td style='border:1px solid black;padding:8px;'>{s['Name']} (Sal+Inc)</td><td style='border:1px solid black;padding:8px;text-align:right;'>{s['Total']:,}</td></tr>"
        for e in shop_results:
            html += f"<tr><td style='border:1px solid black;padding:8px;'>{e['Item']}</td><td style='border:1px solid black;padding:8px;text-align:right;'>{e['Amount']:,}</td></tr>"
        html += f"</table><br><p>Profit: <b>{profit:,.0f}</b></p></div>"
        st.markdown(html, unsafe_allow_html=True)

    if staff_results or shop_results:
        pdf_bytes = create_pdf(current_shop, selected_month_name, selected_year, staff_results, shop_results, total_sales, total_out, profit)
        b3.download_button(label="📄 Download PDF", data=pdf_bytes, file_name=f"{shop_id}_{selected_month_name}.pdf", mime="application/pdf")

# --- TAB 3: HISTORY ---
with tab3:
    st.subheader(f"Cloud History: {current_shop}")
    hist_ref = db.reference(f'history/{shop_id}')
    history = hist_ref.get()
    if history:
        h_df = pd.DataFrame.from_dict(history, orient='index')
        st.bar_chart(h_df[['sales', 'profit']])
        st.dataframe(h_df, width='stretch')