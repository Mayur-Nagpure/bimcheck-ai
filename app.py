import json
import os
from io import BytesIO

import pandas as pd
import streamlit as st

from bim_checker import check_model, build_summary, explain_issues_with_ai

st.set_page_config(page_title="BIMCheck AI", page_icon="🏗️", layout="wide")

st.title("🏗️ BIMCheck AI")
st.caption("A Python prototype for building-model data validation and quality checks.")
st.info(
    "Prototype note: this app validates structured BIM-like JSON data. "
    "It is not connected to Autodesk Revit and does not modify RVT files."
)

with st.sidebar:
    st.header("Project settings")
    api_key = st.text_input(
        "OpenAI API key (optional)",
        type="password",
        help="Leave blank to use the built-in explanations. Your key is used only if you click AI explanation."
    )
    st.caption("Works without an API key.")

sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "sample_model.json")
with open(sample_path, "r", encoding="utf-8") as f:
    sample_text = f.read()

uploaded = st.file_uploader("Upload a BIM model JSON file", type=["json"])
default_text = uploaded.getvalue().decode("utf-8") if uploaded else sample_text

with st.expander("View or edit the input model", expanded=uploaded is None):
    model_text = st.text_area(
        "JSON model data",
        value=default_text,
        height=260,
        help="Expected format: a JSON object containing an 'elements' list."
    )

run = st.button("Run quality checks", type="primary", use_container_width=True)

if run:
    try:
        model = json.loads(model_text)
        results = check_model(model)
        summary = build_summary(results)
        st.session_state["results"] = results
        st.session_state["summary"] = summary
        st.session_state["model"] = model
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
    except ValueError as exc:
        st.error(str(exc))

if "results" in st.session_state:
    results = st.session_state["results"]
    summary = st.session_state["summary"]
    issues = results["issues"]

    st.subheader("Quality-check summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Elements checked", summary["elements_checked"])
    c2.metric("Issues found", summary["issue_count"])
    c3.metric("Errors", summary["errors"])
    c4.metric("Warnings", summary["warnings"])

    if not issues:
        st.success("No issues detected by the current validation rules.")
    else:
        st.subheader("Detected issues")
        issue_df = pd.DataFrame(issues)
        st.dataframe(issue_df, use_container_width=True, hide_index=True)

        csv_bytes = issue_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download issues as CSV",
            data=csv_bytes,
            file_name="bim_quality_issues.csv",
            mime="text/csv"
        )

    st.subheader("Summary")
    st.write(summary["message"])

    if st.button("Generate AI explanation", disabled=not issues):
        with st.spinner("Preparing explanation..."):
            explanation = explain_issues_with_ai(
                issues=issues,
                api_key=api_key.strip() or None
            )
        st.markdown(explanation)

    report = {
        "project_name": st.session_state["model"].get("project_name", "Unnamed project"),
        "summary": summary,
        "issues": issues,
    }
    st.download_button(
        "⬇️ Download full report as JSON",
        data=json.dumps(report, indent=2).encode("utf-8"),
        file_name="bim_quality_report.json",
        mime="application/json"
    )

with st.expander("Validation rules used"):
    st.markdown("""
- Every element should have an ID and a supported type.
- Length, width, and height must be numeric and greater than zero when required.
- Doors and windows should reference a host wall ID.
- Element IDs should be unique.
- Elements with unusually large dimensions are flagged for review.
- These are prototype rules, not official building-code checks.
""")
