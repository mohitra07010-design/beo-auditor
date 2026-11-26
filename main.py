import re
import streamlit as st
import pandas as pd
from pypdf import PdfReader

st.set_page_config(
    page_title="BEO Discrepancy & Margin Auditor",
    page_icon="🏨",
    layout="wide"
)

def read_uploaded_file(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    if uploaded_file.name.lower().endswith(".pdf"):
        reader = PdfReader(uploaded_file)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return uploaded_file.getvalue().decode("utf-8", errors="ignore")

def extract_event_specs(text: str) -> dict:
    text_lower = text.lower()

    def find_int(patterns, default=0):
        for pat in patterns:
            match = re.search(pat, text_lower)
            if match:
                return int(match.group(1).replace(",", ""))
        return default

    return {
        "guests": find_int([r"(\d+)\s*guests?", r"headcount[:\s]+(\d+)"], 0),
        "jain_meals": find_int([r"(\d+)\s*jain\s*meals?"], 0),
        "wireless_mics": find_int([r"(\d+)\s*wireless\s*mics?", r"(\d+)\s*mics?"], 0),
        "projectors": find_int([r"(\d+)\s*projectors?"], 0),
        "extra_hours": find_int([r"(\d+)\s*extra\s*hours?", r"extend.*?(\d+)\s*hours?"], 0),
        "quoted_price": find_int([r"₹\s*([\d,]+)", r"rs\.?\s*([\d,]+)", r"price[:\s]+([\d,]+)"], 0),
        "complimentary_mentioned": "complimentary" in text_lower or "free" in text_lower
    }

st.sidebar.header("⚙️ Hotel Cost & Rate Card")
cost_per_plate = st.sidebar.number_input("Internal Food Cost / Guest (₹)", value=1100, step=50)
bill_per_plate = st.sidebar.number_input("Billing Rate / Extra Guest (₹)", value=1600, step=50)
jain_surcharge = st.sidebar.number_input("Extra Cost / Jain Meal (₹)", value=250, step=50)
mic_rate = st.sidebar.number_input("Wireless Mic Rental / Unit (₹)", value=2500, step=500)
projector_rate = st.sidebar.number_input("Projector Rental / Unit (₹)", value=6000, step=500)
overtime_rate = st.sidebar.number_input("Hall & Staff Overtime / Hour (₹)", value=15000, step=1000)
target_margin_pct = st.sidebar.slider("Target Profit Margin (%)", 10, 50, 30)

st.title("🏨 BEO Discrepancy & Margin-Leakage Auditor")
st.markdown(
    "Upload or paste the **Official BEO** and the **Client Email/WhatsApp Thread** below "
    "to detect operational mismatches, unbilled add-ons, and margin erosion."
)

col1, col2 = st.columns(2)

with col1:
    st.subheader("📄 Official BEO Document")
    beo_file = st.file_uploader("Upload BEO (PDF or TXT)", type=["pdf", "txt"], key="beo_file")
    beo_extracted = read_uploaded_file(beo_file)
    beo_text = st.text_area(
        "Or paste BEO text here",
        value=beo_extracted,
        height=220,
        placeholder="Example:\nExpected Guests: 250 guests\n10 Jain meals\n1 wireless mic, 1 projector\nQuoted Price: ₹450000"
    )

with col2:
    st.subheader("💬 Client Email / WhatsApp Thread")
    client_file = st.file_uploader("Upload Chat/Email (PDF or TXT)", type=["pdf", "txt"], key="client_file")
    client_extracted = read_uploaded_file(client_file)
    client_text = st.text_area(
        "Or paste client messages here",
        value=client_extracted,
        height=220,
        placeholder="Example:\nPlease update to 285 guests, 25 Jain meals, 3 wireless mics, and 2 extra hours."
    )

if st.button("🔍 Run Audit", type="primary", use_container_width=True):
    if not beo_text.strip() or not client_text.strip():
        st.warning("Please upload or paste both the BEO document and the client thread before running the audit.")
        st.stop()

    beo = extract_event_specs(beo_text)
    client = extract_event_specs(client_text)

    actual = {
        k: (client[k] if client[k] > 0 else beo[k])
        for k in ["guests", "jain_meals", "wireless_mics", "projectors", "extra_hours"]
    }
    quoted_price = beo["quoted_price"] if beo["quoted_price"] > 0 else (actual["guests"] * bill_per_plate)

    conflicts = []
    unbilled_items = []

    checks = [
        ("Guest Headcount", "guests", "Kitchen & Stewarding", bill_per_plate, "High"),
        ("Jain Meals", "jain_meals", "Kitchen (Dietary)", jain_surcharge, "High"),
        ("Wireless Mics", "wireless_mics", "AV / Sound Team", mic_rate, "Medium"),
        ("Projectors", "projectors", "AV / Sound Team", projector_rate, "Medium"),
        ("Extra Hours (Overtime)", "extra_hours", "Operations & Security", overtime_rate, "High"),
    ]

    total_unbilled = 0
    for label, key, dept, unit_rate, severity in checks:
        diff = actual[key] - beo[key]
        if diff != 0:
            conflicts.append({
                "Item": label,
                "BEO Value": beo[key],
                "Client Thread Value": actual[key],
                "Variance": f"{diff:+d}",
                "Department": dept,
                "Severity": severity
            })
            if diff > 0:
                amt = diff * unit_rate
                total_unbilled += amt
                unbilled_items.append({
                    "Unbilled Add-On": label,
                    "Extra Qty": diff,
                    "Unit Rate (₹)": f"₹{unit_rate:,}",
                    "Recoverable Amount (₹)": f"₹{amt:,}"
                })

    base_cost = (
        actual["guests"] * cost_per_plate
        + actual["jain_meals"] * jain_surcharge
        + actual["wireless_mics"] * (mic_rate * 0.6)
        + actual["projectors"] * (projector_rate * 0.6)
        + actual["extra_hours"] * (overtime_rate * 0.7)
    )
    projected_profit = quoted_price - base_cost
    projected_margin_pct = (projected_profit / quoted_price) * 100 if quoted_price > 0 else 0
    recovered_margin_pct = ((projected_profit + total_unbilled) / (quoted_price + total_unbilled)) * 100 if (quoted_price + total_unbilled) > 0 else 0

    st.divider()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🚨 Silent Conflicts Found", len(conflicts))
    k2.metric("💰 Unbilled Revenue Leakage", f"₹{total_unbilled:,}")
    k3.metric(
        "📉 Current Margin (Unbilled)",
        f"{projected_margin_pct:.1f}%",
        delta=f"{projected_margin_pct - target_margin_pct:.1f}% vs Target",
        delta_color="normal"
    )
    k4.metric(
        "📈 Margin After Recovery",
        f"{recovered_margin_pct:.1f}%",
        delta=f"+{recovered_margin_pct - projected_margin_pct:.1f}% gain"
    )

    if projected_margin_pct < target_margin_pct:
        st.error(
            f"⚠️ **Margin Alert:** Unbilled changes drop event profitability to **{projected_margin_pct:.1f}%** "
            f"(below your {target_margin_pct}% target). Issue a BEO Addendum before execution."
        )
        if client["complimentary_mentioned"]:
            st.warning("🚩 **Sales Policy Flag:** Client thread mentions a 'complimentary' perk. Verify manager approval.")
    else:
        st.success(f"✅ Event margin ({projected_margin_pct:.1f}%) is within your target threshold.")

    tab1, tab2, tab3 = st.tabs(["🚨 Operational Mismatches", "💸 Revenue Leakage Breakdown", "📲 Auto-Dispatch Alerts"])

    with tab1:
        if conflicts:
            st.dataframe(pd.DataFrame(conflicts), use_container_width=True, hide_index=True)
        else:
            st.info("No mismatches detected between BEO and client thread.")

    with tab2:
        if unbilled_items:
            st.dataframe(pd.DataFrame(unbilled_items), use_container_width=True, hide_index=True)
            st.markdown(f"**Total Recoverable Billing Addendum:** `₹{total_unbilled:,}`")
        else:
            st.info("No unbilled add-ons detected.")

    with tab3:
        st.subheader("Ready-to-Send Department Alerts")
        if conflicts:
            for dept_keyword, header in [
                ("Kitchen", "👨‍🍳 KITCHEN ALERT:"),
                ("AV", "🎤 AV TEAM ALERT:"),
                ("Operations", "🕒 OPERATIONS / BILLING ALERT:")
            ]:
                dept_items = [c for c in conflicts if dept_keyword in c["Department"]]
                if dept_items:
                    lines = [f"- Update {c['Item']}: {c['BEO Value']} -> {c['Client Thread Value']} ({c['Variance']})" for c in dept_items]
                    if dept_keyword == "Operations" and total_unbilled > 0:
                        lines.append(f"- Action: Send ₹{total_unbilled:,} revised addendum to client.")
                    st.code(f"{header}\n" + "\n".join(lines), language="text")
        else:
            st.info("All departments are already aligned.")