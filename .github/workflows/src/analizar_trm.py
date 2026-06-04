"""
Análisis diario de la TRM (Tasa Representativa del Mercado - Colombia)
Obtiene datos de Yahoo Finance, analiza con Claude API y envía email HTML.
"""

import os
import smtplib
import json
import yfinance as yf
import anthropic
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
import io

# ── Configuración ────────────────────────────────────────────────────────────
CORREO_DESTINO  = os.environ["CORREO_DESTINO"]   # a quién le llega
CORREO_ORIGEN   = os.environ["CORREO_ORIGEN"]    # cuenta Gmail que envía
GMAIL_APP_PASS  = os.environ["GMAIL_APP_PASS"]   # contraseña de aplicación Gmail
ANTHROPIC_KEY   = os.environ["ANTHROPIC_API_KEY"]


# ── 1. Obtener datos TRM últimos 10 días ─────────────────────────────────────
def obtener_datos_trm(dias: int = 10) -> dict:
    ticker = yf.Ticker("USDCOP=X")
    hist = ticker.history(period=f"{dias}d")

    if hist.empty:
        raise ValueError("No se pudieron obtener datos de Yahoo Finance para USDCOP=X")

    # Filtrar solo días hábiles con datos reales
    hist = hist[hist["Close"] > 0].copy()
    hist.index = hist.index.tz_localize(None)

    registros = []
    for fecha, row in hist.iterrows():
        registros.append({
            "fecha": fecha.strftime("%Y-%m-%d"),
            "cierre": round(float(row["Close"]), 2),
            "apertura": round(float(row["Open"]), 2),
            "max": round(float(row["High"]), 2),
            "min": round(float(row["Low"]), 2),
        })

    # Ordenar de más antiguo a más reciente
    registros = sorted(registros, key=lambda x: x["fecha"])

    ultimo    = registros[-1]
    penultimo = registros[-2] if len(registros) >= 2 else ultimo

    variacion_abs = round(ultimo["cierre"] - penultimo["cierre"], 2)
    variacion_pct = round((variacion_abs / penultimo["cierre"]) * 100, 2)

    return {
        "fecha_analisis": ultimo["fecha"],
        "trm_hoy":        ultimo["cierre"],
        "trm_ayer":       penultimo["cierre"],
        "variacion_abs":  variacion_abs,
        "variacion_pct":  variacion_pct,
        "max_dia":        ultimo["max"],
        "min_dia":        ultimo["min"],
        "historico":      registros,   # últimos N días para la gráfica
    }


# ── 2. Analizar con Claude (noticias + tendencia) ────────────────────────────
def analizar_con_claude(datos: dict) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Eres un analista financiero especializado en el mercado cambiario colombiano.

Hoy es {datetime.now().strftime("%A %d de %B de %Y")}.

DATOS TRM DEL DÍA ANTERIOR ({datos['fecha_analisis']}):
- TRM de cierre: ${datos['trm_hoy']:,.2f} COP
- TRM del día previo: ${datos['trm_ayer']:,.2f} COP
- Variación absoluta: ${datos['variacion_abs']:+.2f} COP
- Variación porcentual: {datos['variacion_pct']:+.2f}%
- Máximo del día: ${datos['max_dia']:,.2f} COP
- Mínimo del día: ${datos['min_dia']:,.2f} COP

Histórico últimos días:
{json.dumps(datos['historico'], ensure_ascii=False, indent=2)}

Tu tarea:
1. Busca en web noticias recientes (últimas 24-48 horas) que expliquen el movimiento del dólar frente al peso colombiano.
2. Redacta un análisis en español con las siguientes secciones exactas, usando HTML básico (párrafos <p>, negritas <strong>, listas <ul><li>):

<seccion id="resumen">
Un párrafo conciso: qué pasó con el dólar ayer, si subió o bajó, y cuánto.
</seccion>

<seccion id="noticias">
Lista de 3-4 factores/noticias clave que explican el movimiento (locales e internacionales).
</seccion>

<seccion id="tendencia">
Un párrafo con la tendencia esperada para los próximos días y los niveles clave a vigilar.
</seccion>

<seccion id="semaforo">
Una sola palabra: ALCISTA, BAJISTA o NEUTRAL (para el dólar vs peso).
</seccion>

Sé concreto, profesional y útil para un empresario o importador colombiano."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extraer solo los bloques de texto
    texto = " ".join(
        block.text for block in response.content
        if hasattr(block, "text")
    )
    return texto


# ── 3. Generar gráfica SVG inline (sin dependencias externas) ─────────────────
def generar_grafica_svg(historico: list) -> str:
    """Genera una gráfica de línea SVG con los últimos 7 días de TRM."""
    datos = historico[-7:]  # máximo 7 días
    n = len(datos)
    if n < 2:
        return ""

    precios = [d["cierre"] for d in datos]
    fechas  = [d["fecha"][-5:] for d in datos]  # MM-DD

    min_p = min(precios) * 0.9985
    max_p = max(precios) * 1.0015
    rango = max_p - min_p or 1

    W, H = 600, 220
    pad_l, pad_r, pad_t, pad_b = 70, 20, 20, 45

    def x(i): return pad_l + (i / (n - 1)) * (W - pad_l - pad_r)
    def y(v): return pad_t + (1 - (v - min_p) / rango) * (H - pad_t - pad_b)

    # Puntos de la línea
    puntos = " ".join(f"{x(i):.1f},{y(p):.1f}" for i, p in enumerate(precios))

    # Área rellena bajo la línea
    area = f"{x(0):.1f},{H - pad_b} " + puntos + f" {x(n-1):.1f},{H - pad_b}"

    # Etiquetas eje Y (4 niveles)
    niveles_y = [min_p + rango * i / 3 for i in range(4)]
    etiq_y = "".join(
        f'<text x="{pad_l - 8}" y="{y(v) + 4:.1f}" text-anchor="end" '
        f'font-size="10" fill="#64748b">${v:,.0f}</text>'
        for v in niveles_y
    )

    # Etiquetas eje X
    etiq_x = "".join(
        f'<text x="{x(i):.1f}" y="{H - 8}" text-anchor="middle" '
        f'font-size="10" fill="#64748b">{fechas[i]}</text>'
        for i in range(n)
    )

    # Círculos en cada punto
    circulos = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(p):.1f}" r="4" fill="#2563eb" stroke="white" stroke-width="2"/>'
        for i, p in enumerate(precios)
    )

    # Color tendencia
    color = "#16a34a" if precios[-1] >= precios[0] else "#dc2626"
    color_area = "#bbf7d0" if precios[-1] >= precios[0] else "#fee2e2"

    svg = f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:600px;">
  <defs>
    <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{color_area}" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="{color_area}" stop-opacity="0.1"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="#f8fafc" rx="8"/>
  <!-- Líneas de cuadrícula -->
  {''.join(f'<line x1="{pad_l}" y1="{y(v):.1f}" x2="{W-pad_r}" y2="{y(v):.1f}" stroke="#e2e8f0" stroke-width="1"/>' for v in niveles_y)}
  <!-- Área rellena -->
  <polygon points="{area}" fill="url(#grad)"/>
  <!-- Línea principal -->
  <polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round"/>
  <!-- Puntos -->
  {circulos}
  <!-- Ejes -->
  {etiq_y}
  {etiq_x}
  <!-- Título -->
  <text x="{W//2}" y="14" text-anchor="middle" font-size="11" fill="#475569" font-weight="600">TRM USD/COP — Últimos {n} días</text>
</svg>"""
    return svg


# ── 4. Construir el email HTML ────────────────────────────────────────────────
def construir_html(datos: dict, analisis: str) -> str:

    fecha_legible = datetime.strptime(datos["fecha_analisis"], "%Y-%m-%d").strftime("%A %d de %B de %Y").capitalize()

    flecha = "▲" if datos["variacion_abs"] > 0 else ("▼" if datos["variacion_abs"] < 0 else "●")
    color_var = "#16a34a" if datos["variacion_abs"] < 0 else ("#dc2626" if datos["variacion_abs"] > 0 else "#64748b")
    # Para el peso: dólar sube → malo para importadores (rojo), baja → verde

    svg_grafica = generar_grafica_svg(datos["historico"])

    # Extraer secciones del análisis de Claude
    def extraer(tag, texto):
        import re
        m = re.search(rf'<seccion id="{tag}">(.*?)</seccion>', texto, re.DOTALL)
        return m.group(1).strip() if m else ""

    resumen   = extraer("resumen",   analisis)
    noticias  = extraer("noticias",  analisis)
    tendencia = extraer("tendencia", analisis)
    semaforo_txt = extraer("semaforo", analisis).strip().upper()

    semaforo_color = {
        "ALCISTA":  ("#fef3c7", "#d97706", "📈 ALCISTA"),
        "BAJISTA":  ("#dcfce7", "#16a34a", "📉 BAJISTA"),
        "NEUTRAL":  ("#f1f5f9", "#64748b", "➡️ NEUTRAL"),
    }.get(semaforo_txt, ("#f1f5f9", "#64748b", f"➡️ {semaforo_txt}"))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TRM Diaria — {fecha_legible}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 0;">
<tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);padding:28px 32px;">
    <p style="margin:0;color:#93c5fd;font-size:13px;letter-spacing:1px;">ANÁLISIS CAMBIARIO DIARIO</p>
    <h1 style="margin:6px 0 0;color:#ffffff;font-size:22px;">Reporte TRM — USD/COP</h1>
    <p style="margin:4px 0 0;color:#bfdbfe;font-size:13px;">{fecha_legible}</p>
  </td></tr>

  <!-- Tarjeta TRM principal -->
  <tr><td style="padding:28px 32px 0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="background:#f8fafc;border-radius:10px;padding:20px 24px;border-left:4px solid #2563eb;">
          <p style="margin:0 0 4px;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;">TRM Oficial</p>
          <p style="margin:0;font-size:36px;font-weight:700;color:#0f172a;">${datos['trm_hoy']:,.2f}</p>
          <p style="margin:4px 0 0;font-size:14px;color:{color_var};font-weight:600;">
            {flecha} {datos['variacion_abs']:+.2f} COP &nbsp;|&nbsp; {datos['variacion_pct']:+.2f}% vs día anterior
          </p>
        </td>
        <td width="16"></td>
        <td style="background:{semaforo_color[0]};border-radius:10px;padding:20px 24px;text-align:center;vertical-align:middle;">
          <p style="margin:0;font-size:11px;color:#64748b;text-transform:uppercase;">Tendencia</p>
          <p style="margin:8px 0 0;font-size:18px;font-weight:700;color:{semaforo_color[1]};">{semaforo_color[2]}</p>
        </td>
      </tr>
    </table>

    <!-- Stats secundarios -->
    <table width="100%" cellpadding="0" cellspacing="16" style="margin-top:16px;">
      <tr>
        <td style="background:#f8fafc;border-radius:8px;padding:12px 16px;text-align:center;">
          <p style="margin:0;font-size:11px;color:#64748b;">Máximo</p>
          <p style="margin:4px 0 0;font-size:16px;font-weight:600;color:#dc2626;">${datos['max_dia']:,.2f}</p>
        </td>
        <td width="12"></td>
        <td style="background:#f8fafc;border-radius:8px;padding:12px 16px;text-align:center;">
          <p style="margin:0;font-size:11px;color:#64748b;">Mínimo</p>
          <p style="margin:4px 0 0;font-size:16px;font-weight:600;color:#16a34a;">${datos['min_dia']:,.2f}</p>
        </td>
        <td width="12"></td>
        <td style="background:#f8fafc;border-radius:8px;padding:12px 16px;text-align:center;">
          <p style="margin:0;font-size:11px;color:#64748b;">Rango del día</p>
          <p style="margin:4px 0 0;font-size:16px;font-weight:600;color:#0f172a;">${datos['max_dia'] - datos['min_dia']:,.2f}</p>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Gráfica -->
  <tr><td style="padding:24px 32px 0;">
    <h2 style="margin:0 0 12px;font-size:14px;color:#374151;font-weight:600;">📊 Evolución últimos 7 días</h2>
    {svg_grafica}
  </td></tr>

  <!-- Resumen -->
  <tr><td style="padding:24px 32px 0;">
    <h2 style="margin:0 0 12px;font-size:14px;color:#374151;font-weight:600;">📋 Resumen del movimiento</h2>
    <div style="color:#374151;font-size:14px;line-height:1.7;">{resumen}</div>
  </td></tr>

  <!-- Noticias -->
  <tr><td style="padding:20px 32px 0;">
    <h2 style="margin:0 0 12px;font-size:14px;color:#374151;font-weight:600;">🌎 Factores que explican el movimiento</h2>
    <div style="color:#374151;font-size:14px;line-height:1.7;">{noticias}</div>
  </td></tr>

  <!-- Tendencia -->
  <tr><td style="padding:20px 32px 0;">
    <h2 style="margin:0 0 12px;font-size:14px;color:#374151;font-weight:600;">🔮 Tendencia esperada</h2>
    <div style="background:#eff6ff;border-radius:8px;padding:16px 20px;color:#1e40af;font-size:14px;line-height:1.7;">{tendencia}</div>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:24px 32px;margin-top:12px;">
    <hr style="border:none;border-top:1px solid #e2e8f0;margin-bottom:16px;">
    <p style="margin:0;font-size:11px;color:#94a3b8;text-align:center;">
      Datos: Yahoo Finance (USDCOP=X) · Análisis: Claude AI · Generado automáticamente<br>
      Este reporte es informativo y no constituye asesoría financiera.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


# ── 5. Enviar email ───────────────────────────────────────────────────────────
def enviar_email(html: str, datos: dict):
    fecha = datos["fecha_analisis"]
    variacion = datos["variacion_pct"]
    flecha = "▲" if variacion > 0 else ("▼" if variacion < 0 else "●")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"TRM {fecha}: {flecha} ${datos['trm_hoy']:,.2f} COP ({variacion:+.2f}%)"
    msg["From"]    = CORREO_ORIGEN
    msg["To"]      = CORREO_DESTINO

    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
        servidor.login(CORREO_ORIGEN, GMAIL_APP_PASS)
        servidor.sendmail(CORREO_ORIGEN, CORREO_DESTINO, msg.as_string())

    print(f"✅ Email enviado a {CORREO_DESTINO}")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("📊 Obteniendo datos TRM...")
    datos = obtener_datos_trm(dias=12)
    print(f"   TRM {datos['fecha_analisis']}: ${datos['trm_hoy']:,.2f} ({datos['variacion_pct']:+.2f}%)")

    print("🤖 Analizando con Claude + búsqueda de noticias...")
    analisis = analizar_con_claude(datos)

    print("📧 Construyendo email HTML...")
    html = construir_html(datos, analisis)

    print("📨 Enviando correo...")
    enviar_email(html, datos)

    print("🎉 ¡Listo! Reporte enviado exitosamente.")
