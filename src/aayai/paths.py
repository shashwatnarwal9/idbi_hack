"""आय·AI shared filesystem paths.

Everything is relative to the project root; set the AAYAI_ROOT environment
variable to relocate (used later when Airflow runs the pipeline in Docker).
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("AAYAI_ROOT", Path(__file__).resolve().parents[2]))

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
SQL_DIR = ROOT / "sql"
MODEL_DIR = ROOT / "model"
