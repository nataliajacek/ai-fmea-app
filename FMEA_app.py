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
# RESTRUCTURED INPUTS (PERSISTENT)
# -----------------------------
st.subheader("Project Information")

user_name = st.text_input("1. User Name", key="user_name")
object_name = st.text_input("2. Product / Prototype Name", key="product_name")
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
# AI GENERATION FUNCTION WITH MISSING ITEM SUGGESTION
# -----------------------------
def generate_fmea(description, object_name, parts_list, functions_text, main_specs_text, subsystem):
    # User-provided lists
    functions = [r.strip() for r in functions_text.split("\n") if r.strip()]
    requirements = [r.strip() for r in main_specs_text.split("\n") if r.strip()]
    parts = [p.strip() for p in parts_list.split("\n") if p.strip()]
    rows = []

    # ---------------------------
    # Step 0: Ask AI for missing items
    # ---------------------------
    prompt_supplement = f"""
You are a senior reliability engineer reviewing a product for FMEA.
Product: {object_name}
Description: {description}
Subsystem: {subsystem}

User-provided functions: {', '.join(functions) if functions else 'None'}
User-provided requirements: {', '.join(requirements) if requirements else 'None'}
User-provided parts: {', '.join(parts) if parts else 'None'}

Please suggest any critical functions, requirements, or parts that are missing and should be included for a complete FMEA.
Return ONLY valid JSON, nothing else.
Format:
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

        # Strip anything outside the first { ... } block
        first = text_supp.find("{")
        last = text_supp.rfind("}")
        if first != -1 and last != -1:
            text_supp = text_supp[first:last+1]

        supplement_data = json.loads(text_supp)
    except Exception as e:
        st.warning(f"Could not get AI suggestions for missing items. Using only user inputs. Error: {e}")
        supplement_data = {"additional_functions": [], "additional_requirements": [], "additional_parts": []}

    # Append AI-suggested items
    functions += supplement_data.get("additional_functions", [])
    requirements += supplement_data.get("additional_requirements", [])
    parts += supplement_data.get("additional_parts", [])

    # ---------------------------
    # Step 1: Generate FMEA rows for all functions/requirements
    # ---------------------------
    for func in functions:
        for req in requirements:
            prompt = f"""
You are a senior reliability engineer performing FMEA for:

Product: {object_name}
Description: {description}
Subsystem: {subsystem}
Function: {func}
Requirement: {req}
Parts: {', '.join(parts)}

Generate realistic failure modes, filling all test columns. Include:
- Failure Scenario
- Part
- Failure Mode
- End Effects
- Causes (2-3)
- Current Design Controls
- Recommended Actions
- Owner
- Execution Phase
- Severity (1-5)
- Occurrence (1-4)
- Detectability (1-3)
- Estimated RPN2
- Recommended tests
- Estimated Cost
- References

Return only valid JSON.
"""
            try:
                with st.spinner(f"Generating FMEA for {func} / {req}..."):
                    response = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3
                    )
                text = response.choices[0].message.content
                failures = json.loads(text)
            except Exception as e:
                st.error(f"AI failed for {func} / {req}: {e}")
                continue

            # Process failures into table
            for f in failures:
                causes_list = f.get("Causes", [""])
                for cause in causes_list:
                    S = min(max(int(f.get("Severity", 3)), 1), 5)
                    O = min(max(int(f.get("Occurrence", 2)), 1), 4)
                    D = min(max(int(f.get("Detectability", 2)), 1), 3)
                    cost_text = f.get("Estimated Cost", "Medium (1)")
                    cost_value = float(cost_text.split("(")[1].replace(")", ""))
                    RPN = S * O * D

                    row = {
                        "Failure Scenario": f.get("Failure Scenario", ""),
                        "Function": func,
                        "Requirement": req,
                        "Part": f.get("Part", ""),
                        "Failure Mode": f.get("Failure Mode", ""),
                        "End Effects of Failure": f.get("End Effects", ""),
                        "Causes": cause,
                        "Current Design Controls": f.get("Controls", ""),
                        "Severity (S)": S,
                        "Occurrence (O)": O,
                        "Detectability (D)": D,
                        "RPN": RPN,
                        "Priority": RPN * cost_value,
                        "Recommended Actions": ", ".join(f.get("Actions", [])),
                        "Owner": f.get("Owner", ""),
                        "Execution Phase": f.get("Execution Phase", ""),
                        "Reference Links": ", ".join(f.get("References", [])),
                        "RPN2 (Post-Action)": f.get("RPN2", ""),
                        "Estimated Cost": cost_text
                    }
                    for col in test_columns:
                        row[col] = "X" if col in f.get("tests", []) else ""
                    rows.append(row)

    return pd.DataFrame(rows)

# -----------------------------
# GENERATE BUTTON
# -----------------------------
if st.button("Generate FMEA"):
    if object_name.strip() == "":
        st.warning("Enter Product / Prototype Name")
    else:
        df = generate_fmea(
            product_description or "",
            object_name or "",
            parts_input or "",
            functions_input or "",
            main_specs or "",
            subsystem or ""
        )
        if df.empty:
            st.warning("Enter at least one function and requirement")
        else:
            st.session_state.df = df

# -----------------------------
# EDITABLE TABLE AND EXCEL EXPORT
# -----------------------------
if "df" in st.session_state:
    st.subheader("Editable FMEA Table")
    edited_df = st.data_editor(st.session_state.df, use_container_width=True)

    # Update calculations
    edited_df["RPN"] = (
        edited_df["Severity (S)"] *
        edited_df["Occurrence (O)"] *
        edited_df["Detectability (D)"]
    )
    edited_df["Priority"] = edited_df["RPN"] * edited_df["Estimated Cost"].apply(lambda x: float(x.split("(")[1].replace(")","")))
    st.session_state.df = edited_df

    # -----------------------------
    # EXCEL EXPORT WITH HORIZONTAL HEADERS
    # -----------------------------
    wb = Workbook()
    ws = wb.active
    ws.title = "FMEA"

    headers = list(edited_df.columns)
    ws.append(headers)

    default_width = 25
    header_font_size = 12
    ws.row_dimensions[1].height = 60

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = Font(bold=True, color="FFFFFF", size=header_font_size)
        cell.fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[cell.column_letter].width = default_width

    fill1 = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    fill2 = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    for i, (_, row) in enumerate(edited_df.iterrows(), start=2):
        for j, value in enumerate(row, start=1):
            ws.cell(row=i, column=j, value=value)
            ws.cell(row=i, column=j).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=i, column=j).fill = fill1 if i % 2 == 0 else fill2

    output = BytesIO()
    wb.save(output)

    st.download_button(
        "Download Excel File",
        output.getvalue(),
        file_name=f"FMEA_{object_name}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
