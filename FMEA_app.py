import streamlit as st
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openai import OpenAI
import json
import datetime
import base64
import pdfplumber

client = OpenAI(api_key=st.secrets["openai"]["api_key"])

st.title("AI-Assisted FMEA Generator – Powered by GPT-4.1-mini")

# -------------------
# Session state
# -------------------

for key in ["user_name","product_name","product_description","subsystem","parts","functions","requirements","version"]:
    if key not in st.session_state:
        st.session_state[key] = datetime.date.today() if key=="version" else ""

# -------------------
# Inputs
# -------------------

st.subheader("Project Information")

user_name = st.text_input("1. User Name", key="user_name")
product_name = st.text_input("2. Product / Prototype Name", key="product_name")
product_description = st.text_area("Product Description", key="product_description")
subsystem = st.text_input("3. Subsystem to perform FMEA", key="subsystem")

parts_input = st.text_area("4. List of Parts / Components (one per line)", key="parts")

functions_input = st.text_area("5. Functions (one per line)", key="functions")

requirements_input = st.text_area("6. Main Specs / Requirements (one per line)", key="requirements")

version = st.date_input("7. Version / Date", key="version")

# -------------------
# NEW: File Upload Section
# -------------------

st.subheader("Additional Context (Optional)")

uploaded_files = st.file_uploader(
    "Upload diagrams, photos, datasheets or specifications",
    accept_multiple_files=True,
    type=["png","jpg","jpeg","pdf","txt"]
)

# -------------------
# Extract text from uploaded files
# -------------------

def extract_file_context(files):

    context = ""

    for file in files:

        if file.type == "application/pdf":

            with pdfplumber.open(file) as pdf:

                for page in pdf.pages:

                    text = page.extract_text()

                    if text:
                        context += text + "\n"

        elif file.type == "text/plain":

            context += file.read().decode("utf-8")

        elif file.type.startswith("image"):

            image_bytes = file.read()
            base64_image = base64.b64encode(image_bytes).decode()

            context += f"\n[Image uploaded: {file.name}]\n"

    return context

# -------------------
# Cost parser
# -------------------

def parse_cost(x):

    try:
        x = str(x)

        if "(" in x:
            return float(x.split("(")[1].replace(")",""))

        return float(x)

    except:
        return 1

# -------------------
# JSON safe parser
# -------------------

def safe_json(text):

    try:

        start = text.find("[")
        end = text.rfind("]")

        if start != -1 and end != -1:

            return json.loads(text[start:end+1])

    except:
        pass

    return []

# -------------------
# Add missing essentials
# -------------------

def ai_add_missing(functions, requirements, parts, file_context):

    prompt = f"""
Product: {product_name}
Description: {product_description}

Existing functions: {functions}
Existing requirements: {requirements}
Existing parts: {parts}

Additional information from uploaded files:
{file_context}

If important functions, requirements, or parts are missing,
add them.

Return JSON:

{{
"additional_functions": [],
"additional_requirements": [],
"additional_parts": []
}}
"""

    try:

        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role":"user","content":prompt}],
            temperature=0.2
        )

        text = r.choices[0].message.content

        data = json.loads(text[text.find("{"):text.rfind("}")+1])

        functions += data.get("additional_functions",[])
        requirements += data.get("additional_requirements",[])
        parts += data.get("additional_parts",[])

    except:
        pass

    return functions, requirements, parts

# -------------------
# Generate FMEA
# -------------------

def generate_fmea():

    functions = [f.strip() for f in functions_input.split("\n") if f.strip()]
    requirements = [r.strip() for r in requirements_input.split("\n") if r.strip()]
    parts = [p.strip() for p in parts_input.split("\n") if p.strip()]

    file_context = ""

    if uploaded_files:
        file_context = extract_file_context(uploaded_files)

    functions, requirements, parts = ai_add_missing(
        functions,
        requirements,
        parts,
        file_context
    )

    if not functions or not requirements:

        st.warning("Enter at least one function and requirement")

        return pd.DataFrame()

    rows = []

    for function in functions:

        prompt = f"""
Product: {product_name}
Description: {product_description}
Subsystem: {subsystem}

Parts: {parts}

Function: {function}

Requirements:
{requirements}

Additional information from files:
{file_context}

For EACH requirement generate 3-5 failure scenarios.

Return JSON list including:

Failure Scenario
Requirement
Part
Failure Mode
End Effects
Causes
Controls
Actions
Owner
Execution Phase
Severity
Occurrence
Detectability
Estimated Cost
tests
References
"""

        with st.spinner(f"Analyzing function: {function}"):

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role":"user","content":prompt}],
                temperature=0.3
            )

        failures = safe_json(response.choices[0].message.content)

        for f in failures:

            causes = f.get("Causes",[""])

            for cause in causes:

                S = int(f.get("Severity",3))
                O = int(f.get("Occurrence",2))
                D = int(f.get("Detectability",2))

                cost_text = f.get("Estimated Cost","Medium(1)")
                cost_val = parse_cost(cost_text)

                rpn = S*O*D

                row = {
                "Failure Scenario":f.get("Failure Scenario",""),
                "Function":function,
                "Requirement":f.get("Requirement",""),
                "Part":f.get("Part",""),
                "Failure Mode":f.get("Failure Mode",""),
                "End Effects of Failure":f.get("End Effects",""),
                "Causes":cause,
                "Current Design Controls":f.get("Controls",""),
                "Severity (S)":S,
                "Occurrence (O)":O,
                "Detectability (D)":D,
                "RPN":rpn,
                "Priority":rpn*cost_val,
                "Recommended Actions":",".join(f.get("Actions",[])),
                "Owner":f.get("Owner",""),
                "Execution Phase":f.get("Execution Phase",""),
                "Reference Links":",".join(f.get("References",[])),
                "Estimated Cost":cost_text
                }

                rows.append(row)

    return pd.DataFrame(rows)

# -------------------
# Generate button
# -------------------

if st.button("Generate FMEA"):

    df = generate_fmea()

    if not df.empty:
        st.session_state.df = df

# -------------------
# Editable table
# -------------------

if "df" in st.session_state:

    st.subheader("Editable FMEA Table")

    edited_df = st.data_editor(
        st.session_state.df,
        use_container_width=True
    )

    edited_df["RPN"] = (
        edited_df["Severity (S)"]
        * edited_df["Occurrence (O)"]
        * edited_df["Detectability (D)"]
    )

    edited_df["Priority"] = edited_df["RPN"] * edited_df["Estimated Cost"].apply(parse_cost)

    st.session_state.df = edited_df

    wb = Workbook()
    ws = wb.active
    ws.title = "FMEA"

    headers = list(edited_df.columns)
    ws.append(headers)

    for r,row in enumerate(edited_df.values,2):

        for c,val in enumerate(row,1):

            if isinstance(val,list):
                val = ", ".join(val)

            if val is None:
                val = ""

            ws.cell(row=r,column=c,value=str(val))

    output = BytesIO()
    wb.save(output)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        file_name=f"FMEA_{product_name}.xlsx"
    )
