"""SEO fixes helper: dev-only endpoint that serves a single HTML page with the
THREE full modified files (vercel.json, server.py, seo_copy_page.py). Each
file has a "Copy entire file" button and a "Download file" link (which uses
Content-Disposition: attachment so the user can upload the raw file to GitHub
in one commit — no search-and-replace needed).

Attached to the FastAPI router from server.py.
"""
from __future__ import annotations

import html as _html
import os
from fastapi import APIRouter
from starlette.responses import Response as StarletteResponse

seo_copy_router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# (display_label, repo_relative_path, local_absolute_path, mode)
#   mode = "new" for a brand-new file, "mod" for a modified existing file.
_FILES = [
    (
        "frontend/vercel.json",
        "frontend/vercel.json",
        os.path.join(_BASE_DIR, "..", "frontend", "vercel.json"),
        "mod",
    ),
    (
        "backend/server.py",
        "backend/server.py",
        os.path.join(_BASE_DIR, "server.py"),
        "mod",
    ),
    (
        "backend/seo_copy_page.py",
        "backend/seo_copy_page.py",
        os.path.join(_BASE_DIR, "seo_copy_page.py"),
        "new",
    ),
]


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        return f"(no se pudo leer {path}: {exc})"


@seo_copy_router.get("/dev/seo-copy/download")
async def dev_seo_copy_download(file: str):
    """Serve a single modified file as a download attachment so the user can
    drag-and-drop it into GitHub's "Upload file" flow and overwrite the repo
    file in one commit."""
    # Whitelist by display label — the user never gets to read arbitrary paths.
    for label, _repo, local_path, _mode in _FILES:
        if file == label and os.path.exists(local_path):
            with open(local_path, "rb") as f:
                data = f.read()
            fname = os.path.basename(local_path)
            return StarletteResponse(
                content=data,
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f'attachment; filename="{fname}"',
                    "X-Robots-Tag": "noindex, nofollow",
                    "Cache-Control": "private, no-store",
                },
            )
    return StarletteResponse(content="not found", status_code=404)


@seo_copy_router.get("/dev/seo-copy")
async def dev_seo_copy_page():
    e = _html.escape

    file_sections = []
    for i, (label, repo_path, local_path, mode) in enumerate(_FILES, 1):
        content = _read(local_path)
        line_count = content.count("\n") + 1
        size_kb = round(len(content.encode("utf-8")) / 1024, 1)
        mode_tag = (
            '<span class="pill new">NUEVO</span>'
            if mode == "new"
            else '<span class="pill mod">MODIFICADO</span>'
        )
        download_url = f"/api/dev/seo-copy/download?file={label}"
        file_sections.append(
            '<section class="file-section">'
            f'<div class="file-head">'
            f'<h2>Archivo <span class="filen">{e(repo_path)}</span> {mode_tag}</h2>'
            f'<div class="file-meta">{line_count:,} líneas · {size_kb} KB</div>'
            f'</div>'
            f'<p class="hint">Pulsa <b>Descargar</b> y sube ese fichero a GitHub '
            f'con <b>Upload file</b> (sobrescribe el existente). Alternativa: '
            f'<b>Copiar todo</b>, abre el fichero en github.com, Ctrl+A, Delete, '
            f'Ctrl+V, Commit.</p>'
            f'<div class="actions">'
            f'<a class="btn primary" href="{download_url}" download>⬇ Descargar '
            f'{e(os.path.basename(local_path))}</a>'
            f'<button class="btn" onclick="copyBlock(this,\'file{i}\')">📋 '
            f'Copiar todo el archivo</button>'
            f'</div>'
            f'<details class="prev"><summary>Ver contenido '
            f'({line_count:,} líneas)</summary>'
            f'<pre id="file{i}"><code>{e(content)}</code></pre>'
            f'</details>'
            '</section>'
        )

    files_html = "\n".join(file_sections)

    html_out = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        '<title>SEO fixes · Archivos para subir a GitHub</title>'
        '<style>'
        ':root{--bg:#0a0a0c;--card:#121216;--line:#262630;--pink:#ff0055;--cyan:#00f0ff;--muted:#a1a1aa;--green:#22c55e}'
        '*{box-sizing:border-box}'
        'body{margin:0;background:var(--bg);color:#fff;font:14.5px/1.6 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto}'
        '.wrap{max-width:1100px;margin:0 auto;padding:24px 18px 80px}'
        'h1{font-size:30px;margin:0 0 6px;letter-spacing:-.02em}'
        'h1 .accent{color:var(--pink)}'
        '.lead{color:#c9c9d1;margin:0 0 22px;max-width:820px}'
        '.steps{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 24px;margin:0 0 32px}'
        '.steps b{color:var(--cyan)}'
        '.steps ol{margin:10px 0 0 20px;padding:0}'
        '.steps li{margin:8px 0}'
        '.file-section{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:20px 22px;margin:0 0 22px}'
        '.file-head{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin:0 0 10px}'
        '.file-section h2{font-size:19px;margin:0;display:flex;align-items:center;gap:10px;flex-wrap:wrap}'
        '.filen{color:var(--cyan);font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:17px}'
        '.file-meta{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}'
        '.pill{font-size:11px;padding:3px 10px;border-radius:999px;font-weight:800;letter-spacing:.05em}'
        '.pill.new{background:#064e3b;color:#6ee7b7}'
        '.pill.mod{background:#1e3a8a;color:#93c5fd}'
        '.hint{color:#c9c9d1;font-size:13px;margin:0 0 14px}'
        '.hint b{color:#fff}'
        '.actions{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 10px}'
        '.btn{background:#1b1b22;color:#fff;border:1px solid var(--line);border-radius:999px;padding:10px 18px;font-weight:700;font-size:13.5px;cursor:pointer;text-decoration:none;display:inline-block;transition:transform .08s}'
        '.btn:hover{border-color:#3a3a46}'
        '.btn:active{transform:scale(.97)}'
        '.btn.primary{background:var(--pink);color:#fff;border-color:var(--pink);box-shadow:0 2px 14px rgba(255,0,85,.25)}'
        '.btn.ok{background:var(--green);color:#fff;border-color:var(--green)}'
        'details.prev{margin:10px 0 0}'
        'details.prev summary{color:var(--muted);font-size:12.5px;cursor:pointer;padding:6px 0;user-select:none}'
        'details.prev summary:hover{color:#fff}'
        'details[open] summary{color:#fff;margin-bottom:8px}'
        'pre{margin:0;padding:16px 18px;background:#07070a;border:1px solid var(--line);border-radius:14px;overflow:auto;max-height:520px;font-variant-ligatures:none}'
        'code{font:12.5px/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:#e4e4e7;white-space:pre}'
        'footer{color:var(--muted);font-size:12px;margin:40px 0 0;text-align:center;line-height:1.7}'
        '</style></head>'
        '<body><div class="wrap">'
        '<h1>Fixes SEO <span class="accent">quienva.me</span></h1>'
        '<p class="lead">Esta página expone los <b>3 archivos modificados</b> listos '
        'para subir a GitHub. Cada archivo tiene su botón <b>Descargar</b>. '
        'Página <code>noindex,nofollow</code> y no linkada en ningún sitio.</p>'
        '<div class="steps"><b>Cómo subirlos a GitHub (sin Save to GitHub):</b>'
        '<ol>'
        '<li>Pulsa <b>Descargar</b> en cada uno de los 3 archivos de abajo. Se guardan en tu carpeta de descargas.</li>'
        '<li>Abre tu repo en github.com.</li>'
        '<li>Para los dos archivos existentes (<code>frontend/vercel.json</code> y <code>backend/server.py</code>): ábrelos en GitHub, pulsa el lápiz, pulsa <b>Delete file</b> → commit. Luego sube el archivo descargado con <b>Add file → Upload files</b> arrastrando a la misma carpeta → commit.</li>'
        '<li>Alternativa más limpia (1 commit): abre cada archivo en GitHub, pulsa el lápiz, Ctrl+A → Delete → pega el contenido copiado con <b>Copiar todo</b> → Commit.</li>'
        '<li>Para <code>backend/seo_copy_page.py</code> (archivo NUEVO): en la carpeta <code>backend/</code> de tu repo, pulsa <b>Add file → Upload files</b> y suelta el archivo descargado → Commit.</li>'
        '<li>Vercel + Render redesplegarán solos en ~2-3 minutos.</li>'
        '<li>En Google Search Console, reenvía el sitemap y vuelve a solicitar indexación de /fiestas/ibiza, /fiestas/palma, etc. Espera 3-6 semanas para ver recuperación.</li>'
        '</ol></div>'
        + files_html +
        '<footer>Fixes aplicados: A (changefreq daily), B (sitemap solo ES + hreflang preservado), C (contenido editorial único por ciudad), D (eventos pasados noindex en vez de 410/301), E (/event → /fiesta), F (noindex rutas SPA + robots.txt sin Disallow masivo), G (sitemap-artists rewrite), H (lastmod blog dinámico).</footer>'
        '</div>'
        '<script>'
        'function copyBlock(btn,id){'
        'var el=document.getElementById(id);'
        'var txt=el.innerText||el.textContent;'
        'navigator.clipboard.writeText(txt).then(function(){'
        'var o=btn.textContent;btn.textContent="✓ Copiado!";btn.classList.add("ok");'
        'setTimeout(function(){btn.textContent=o;btn.classList.remove("ok");},1800);'
        '}).catch(function(){alert("No se pudo copiar automáticamente. Abre el bloque y selecciona + Ctrl+C manualmente.");});}'
        '</script>'
        '</body></html>'
    )
    return StarletteResponse(
        content=html_out,
        media_type="text/html; charset=utf-8",
        headers={
            "X-Robots-Tag": "noindex, nofollow",
            "Cache-Control": "private, no-store",
        },
    )
