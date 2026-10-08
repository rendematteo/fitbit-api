"""
src/paths.py — Rutas centralizadas del proyecto.
Todos los scripts importan de acá para no hardcodear paths.
"""
import os

# Raíz del proyecto (fitbit-personal/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Secretos (hermano del proyecto: projects/.secrets/)
SECRETS_DIR = os.path.join(os.path.dirname(ROOT), ".secrets")

# Datos
DATA_DIR = os.path.join(ROOT, "data", "descargas_google_health")
TAKEOUT_DIR = os.path.join(ROOT, "data", "takeout")

# Web (HTML generado)
WEB_DIR = os.path.join(ROOT, "web")

# Docs
DOCS_DIR = os.path.join(ROOT, "docs")

# Plan de entrenamiento
PLAN_CSV = os.path.join(DOCS_DIR, "plan_10k_28nov.csv")
