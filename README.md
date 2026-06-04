# 📊 TRM Diaria — Análisis Automático USD/COP

Envia cada mañana (lunes a viernes a las 6 AM hora Colombia) un correo con:
- TRM oficial del día anterior con variación
- Gráfica de los últimos 7 días
- Análisis de noticias que explican el movimiento
- Tendencia esperada generada por Claude AI

---

## 🚀 Configuración paso a paso

### Paso 1 — Subir este proyecto a GitHub

1. Ve a [github.com](https://github.com) → botón **"New repository"**
2. Ponle nombre: `trm-diaria`
3. Selecciona **Private** (recomendado, contiene tus credenciales)
4. Clic en **"Create repository"**
5. Sube los archivos: arrastra la carpeta del proyecto o usa Git:

```bash
git init
git add .
git commit -m "primer commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/trm-diaria.git
git push -u origin main
```

---

### Paso 2 — Obtener la API Key de Anthropic (Claude)

1. Ve a [console.anthropic.com](https://console.anthropic.com)
2. Menú lateral → **"API Keys"**
3. Clic en **"Create Key"** → cópiala (empieza con `sk-ant-...`)
4. Guárdala, solo se muestra una vez

---

### Paso 3 — Configurar contraseña de aplicación en Gmail

> ⚠️ Gmail NO permite usar tu contraseña normal para envío automático.
> Debes crear una "contraseña de aplicación" especial.

1. Ve a tu cuenta Google → [myaccount.google.com](https://myaccount.google.com)
2. Seguridad → **Verificación en dos pasos** (actívala si no la tienes)
3. Luego busca: **"Contraseñas de aplicaciones"**
   - O ve directamente a: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
4. En "Seleccionar app" elige **"Correo"**
5. En "Seleccionar dispositivo" elige **"Otro"** → escribe "TRM Bot"
6. Clic **"Generar"** → copia la contraseña de 16 caracteres (ej: `abcd efgh ijkl mnop`)
7. Elimina los espacios al guardarla: `abcdefghijklmnop`

---

### Paso 4 — Agregar los secretos en GitHub

En tu repositorio de GitHub:

1. Ve a **Settings** → **Secrets and variables** → **Actions**
2. Clic en **"New repository secret"** para cada uno:

| Nombre del secreto   | Valor                              |
|---------------------|------------------------------------|
| `ANTHROPIC_API_KEY` | Tu API key de Anthropic            |
| `CORREO_ORIGEN`     | Tu email de Gmail (quien envía)    |
| `CORREO_DESTINO`    | El email donde quieres recibirlo   |
| `GMAIL_APP_PASS`    | La contraseña de aplicación Gmail  |

---

### Paso 5 — Probar manualmente

1. En tu repositorio ve a la pestaña **"Actions"**
2. Selecciona el workflow **"TRM Diaria"**
3. Clic en **"Run workflow"** → **"Run workflow"**
4. Espera ~2 minutos y revisa tu correo

Si aparece ✅ verde, ¡todo funciona! A partir de ahora correrá automáticamente cada día hábil a las 6 AM.

---

## 📁 Estructura del proyecto

```
trm-diaria/
├── .github/
│   └── workflows/
│       └── trm-diaria.yml    # Programación automática (GitHub Actions)
├── src/
│   └── analizar_trm.py       # Script principal
├── requirements.txt          # Dependencias Python
└── README.md                 # Este archivo
```

---

## ❓ Preguntas frecuentes

**¿Tiene costo?**
- GitHub Actions: gratis (hasta 2,000 minutos/mes en repos privados, este script usa ~2 min/día)
- Anthropic API: tiene costo mínimo (~$0.01 USD por ejecución)
- Gmail: completamente gratis

**¿Qué pasa los fines de semana?**
El cron está configurado solo para lunes a viernes (`1-5`). Los lunes recibirás el análisis del viernes anterior.

**¿Puedo cambiar la hora?**
Sí, edita la línea `cron` en `.github/workflows/trm-diaria.yml`.
Colombia es UTC-5, así que 6 AM Colombia = 11:00 UTC → `'0 11 * * 1-5'`

**¿Puedo enviarlo a varios correos?**
Cambia `CORREO_DESTINO` por una lista separada por comas, o crea múltiples secrets.
