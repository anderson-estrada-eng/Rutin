# Rutina

Hoja de cálculo web para armar tu día: tareas con o sin horario, duración en minutos/horas, y al reordenar se recalculan las horas (de **6:00 AM** hacia adelante, tope **4:00 PM**).

## Local

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Abre http://127.0.0.1:5000

## GitHub → PythonAnywhere

Pasos detallados en el chat de Cursor / abajo en `DEPLOY.txt` si existe.

Resumen:

1. `git init` → `git add .` → `git commit` → crear repo público en GitHub → `git push -u origin main`
2. En PythonAnywhere: clone del repo, virtualenv, `pip install -r requirements.txt`
3. Web app → WSGI apunta a `app.application` (ver `wsgi.py`)
4. Reload → visitar `https://TU_USUARIO.pythonanywhere.com`
