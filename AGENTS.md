# 📜 Reglas del proyecto — AGENTS.md

> Reglas que cualquier agente (o persona) debe seguir en este proyecto.
> Estilo GitHub: este archivo es la "fuente de verdad" de las reglas.

## 🔐 Secretos
- Los secretos viven en **`C:\Users\R\Desktop\projects\.secrets\`** — NUNCA en la carpeta del proyecto
- **NUNCA** commitar secretos (lo evita `.gitignore`)
- **NUNCA** compartir credenciales por chat, email, ni ningún medio
- Si un script necesita un credencial, lo lee de `.secrets/`

## 📊 Datos
- Los datos de salud son **personales** — se quedan locales, no se suben a ningún lado
- `descargas_google_health/` está en `.gitignore` (son datos privados)

## 🐍 Código
- **Python 3.12**
- Dependencias en `requirements.txt` → `pip install -r requirements.txt`
- Los scripts corren con `python script.py` desde la carpeta del proyecto
- Estilo: minimalista, comentarios en español, emojis en consola OK

## 📁 Estructura
- `*.py` en la raíz = scripts
- `descargas_google_health/` = datos bajados
- `docs/` = documentación
- `*.html` = web estática generada
- `fitclub/` = app (Docker + ranking)

## ✅ Commits (estilo GitHub)
- NUNCA commitar `.secrets/`, `token.json`, `client_secret.json`
- Revisá `.gitignore` antes de cada commit
- Commits con mensaje claro en español

## 🚨 Nunca
- Nunca subir credenciales ni datos de salud a git
- Nunca ejecutar scripts que expongan secretos por consola
- Nunca borrar `.secrets/` sin confirmación
