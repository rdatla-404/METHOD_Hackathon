# METHOD_Hackathon
Hackathon
https://methodhackathon-v5arteionw97bxspvmxqec.streamlit.app/

# Interconnection Intake Gatekeeper

---

## Project Structure

```text
Method Hackathon/
├── app.py                      # Main Streamlit user interface and frontend runner
├── requirements.txt            # Python package dependencies needed to run the app
├── test_backend.py             # Automated testing script to verify validation logic
├── backend/                    # Core logic package for validation and data processing
│   ├── __init__.py             # Marks the folder as a Python package
│   ├── adapter.py              # Data formatting and adaptation layer
│   ├── config.py               # Configuration settings and environment constants
│   ├── engine.py               # Central engine coordinating validation workflows
│   ├── extractor.py            # Data extraction utilities for reading applicant files
│   ├── fields.py               # Definition of required submission fields and schemas
│   ├── loader.py               # File loading and handling utilities
│   ├── models.py               # Data models and type structures (e.g., Optional type hints)
│   └── checks/                 # Specific validation rules folder
│       ├── __init__.py         # Marks checks as a package
│       ├── logic.py            # Custom validation logic rules
│       └── reference.py        # Reference table cross-checking rules
└── data/                       # Reference datasets and sample templates
    ├── 03_substation_reference_table.xlsx
    ├── 04_example_PASSING_submission.xlsx
    └── 05_registered_applicants.xlsx
