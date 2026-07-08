# PythonAnywhere WSGI
#
# En PythonAnywhere → Web → WSGI configuration file:
# reemplaza el contenido por algo parecido a esto
# (ajusta 'TU_USUARIO' y la ruta del repo).

import sys
from pathlib import Path

# Ruta donde clonaste el repo, por ejemplo:
# /home/TU_USUARIO/Rutina
project = Path("/home/TU_USUARIO/Rutina")

if str(project) not in sys.path:
    sys.path.insert(0, str(project))

# Virtualenv (si lo creaste en el panel Web):
# activate_this = "/home/TU_USUARIO/.virtualenvs/rutina/bin/activate_this.py"
# with open(activate_this) as f:
#     exec(f.read(), {"__file__": activate_this})

from app import application  # noqa: E402
