from __future__ import annotations

import os
import sys
from pathlib import Path

# 1. Blindagem de ambiente: isola o app do Python global/variáveis de ambiente do host
os.environ.pop("PYTHONPATH", None)
os.environ.pop("PYTHONHOME", None)

# 2. Neutralização do NumPy: openpyxl usa números nativos em pure Python quando numpy não existe.
# Em máquinas com NumPy 2.x instalado no sistema operacional, o openpyxl falha ao iniciar com
# 'AttributeError: module numpy has no attribute short'.
# Definir sys.modules["numpy"] = None faz com que qualquer tentativa de importação levante ModuleNotFoundError,
# que é capturado perfeitamente pelo openpyxl sem alterar a integridade dos dados e sem quebrar a inicialização.
sys.modules["numpy"] = None

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kanban_app.main import run

if __name__ == "__main__":
    raise SystemExit(run())
