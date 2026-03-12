import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openai import OpenAI
import json
import datetime

# -----------------------------
# OPENAI CLIENT
# -----------------------------
client = OpenAI(api_key=st.secrets["openai"]["api_key"])

st.title("AI-Assisted FMEA Generator – Powered by GPT-4.1-mini")

# -----------------------------
# INITIALIZE SESSION STATE
# -----------------------------
for key in ["user_name","product_name","product_description","subsystem","parts","functions","requirements","version"]:
    if key not in st.session_state:
        st.session_state[key] = datetime.date.today() if key=="version" else ""

# -----------------------------
# INPUTS (Persistent)
# -----------------------------
st.subheader("Project Information")
user_name = st.text_input("1. User Name", key="user_name")
product_name = st.text_input("2. Product / Prototype Name", key="product_name")
product_description = st.text_area("Product Description", key="product_description")
subsystem = st.text_input("3. Subsystem to perform FMEA", key="subsystem")
parts_input = st.text_area("4. List of Parts / Components (one per line)", key="parts")
functions_input = st.text_area("5. Functions (one per line)", key="functions")
main_specs = st.text_area("6. Main Specs / Requirements (one per line)", key="requirements")
version = st.date_input("7. Version / Date", key="version")

# -----------------------------
# TEST MATRIX
# -----------------------------
test_columns = [
    "INVESTIGATION & TESTING",
    "VENDOR - PART",
    "DESIGN CHANGE",
    "DIM & WORST CASE",
    "SIMULATION",
    "CHARACTERIZE",
    "CPPP",
    "DIAGNOSTICS",
    "FUNCTIONALITY",
    "OOBE & INSTALL",
    "SYSTEM TEST",
    "SIT E2E APP",
    "HALT",
    "ALT",
    "ROBUSTNESS",
    "REGS EMC",
    "REGSSAFETY",
    "USABILITY",
    "SW-FW TESTS",
    "MFG TESTS",
    "MAINTENANCE",
    "SERVICEABILITY"
]

# -----------------------------
# COST MAPPING
# -----------------------------
cost_map = {
    "Very High": 2,
    "High": 1.5,
    "Medium": 1,
    "Low": 0.75
}

# -----------------------------
# AI GENERATION FUNCTION
# -----------------------------
def generate_fmea(description, product_name, parts_list, functions_text, main_specs_text, subsystem):
    # Convert user inputs to lists
    functions = [r.strip() for r in functions_text.split("\n") if r.strip()]
    requirements = [r.strip() for r in main_specs_text.split("\n") if r.strip()]
    parts = [p.strip() for p in parts_list.split("\n") if p.strip()]
    rows = []

    # ---------------------------
    # Step 0: Ask AI for missing items
    # ---------------------------
    prompt_supplement = f"""
You are a senior reliability engineer performing FMEA.

Product: {product_name}
Description: {description}
Subsystem: {subsystem}

User-provided functions: {', '.join(functions) if functions else 'None'}
User-provided requirements: {', '.join(requirements) if requirements else 'None'}
User-provided parts: {', '.join(parts) if parts else 'None'}

Please suggest any critical functions, requirements, or parts that are missing for a complete FMEA.
Return only **valid JSON** exactly like this format:

{{
"additional_functions": ["function1", "function2"],
"additional_requirements": ["requirement1", "requirement2"],
"additional_parts": ["part1", "part2"]
}}
"""

    try:
        response_supplement = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt_supplement}],
            temperature=0.3
        )
        text_supp = response_supplement.choices[0].message.content.strip()

        # Extract JSON from any extra text
        first = text_supp.find("{")
        last = text_supp.rfind("}")
        if first != -1 and last != -1
