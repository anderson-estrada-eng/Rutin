# DATOS PROTEGIDOS — NO BORRAR / NO SOBREESCRIBIR

**Estado: HAY DATOS REALES DEL USUARIO en producción (PythonAnywhere).**

## Regla absoluta (para cualquier agente o desarrollador)

1. **Nunca** sobrescribas, resetees, regeneres ni reemplaces `data/workbook.json` con datos de ejemplo o del repo.
2. **Nunca** ejecutes en PythonAnywhere comandos que pisen ese archivo, por ejemplo:
   - `git checkout -- data/workbook.json`
   - `git restore data/workbook.json`
   - borrar o volver a clonar `data/`
3. Al hacer `git pull` en PythonAnywhere: **conservar siempre** el `workbook.json` local del servidor (stash, o ignorarlo).
4. Los cambios de código (UI, auth, schedule, etc.) **no deben tocar** el contenido de las hojas del usuario.
5. Si hace falta un archivo de plantilla, usa solo `data/workbook.example.json`. El archivo real de datos es `data/workbook.json` y vive en el servidor.

## Motivo

El usuario ya cargó tareas, hojas y horarios en la web. Perderlos al desplegar es inaceptable.

## PythonAnywhere — pull seguro (copiar tal cual)

```bash
cd ~/Rutin
# Guarda tus datos (por si acaso)
cp -n data/workbook.json data/workbook.json.bak 2>/dev/null || true
# Actualiza SOLO código; workbook.json ya no va en git
git pull origin main
# Si por error git tocó workbook.json, recupera:
# cp data/workbook.json.bak data/workbook.json
```

## Primera vez después de sacar workbook.json de Git

En el próximo `git pull`, Git puede **borrar** `data/workbook.json` del disco porque ya no está en el repo.
Haz SIEMPRE esto:

```bash
cd ~/Rutin
cp data/workbook.json ~/workbook.json.SAFE
git pull origin main
# Si el archivo desapareció o se vació:
cp ~/workbook.json.SAFE data/workbook.json
```

Luego Web → Reload. Tus datos quedan seguros.

