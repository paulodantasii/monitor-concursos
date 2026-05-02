"""Garante que o pacote raiz seja importável pelos testes / Ensures the project root is importable in tests"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
