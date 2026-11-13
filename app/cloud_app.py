"""Entrada do Streamlit Community Cloud."""
import os
import runpy
from pathlib import Path

os.environ["JURISIA_CLOUD"] = "1"
runpy.run_path(str(Path(__file__).with_name("streamlit_app.py")), run_name="__main__")
