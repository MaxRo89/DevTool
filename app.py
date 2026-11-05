"""Servidor Flask del visor responsive.

La página principal muestra varias pantallas (iframes) con la misma URL.
Cada iframe no carga el sitio directamente: pasa por /proxy, que descarga la
página con el User-Agent del dispositivo, quita las cabeceras que impiden
mostrarla dentro de un iframe y guarda las cookies en un "frasco" (jar)
separado por pantalla. /api/reset vacía todos esos frascos.
"""

import argparse
import html
import json
import logging
import os
import re
import socket
import threading
import warnings
import webbrowser
from urllib.parse import urlparse

# El Python que trae macOS usa LibreSSL y urllib3 avisa al arrancar; no
# afecta al visor, así que no mostramos ese aviso a los usuarios.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

import requests  # noqa: E402
from flask import Flask, Response, jsonify, render_template, request
from flask import cli as flask_cli

from devices import DEFAULT_DEVICE_IDS, DEVICES, DEVICES_BY_ID

app = Flask(__name__)

REQUEST_TIMEOUT = 15  # segundos

# Una sesión de requests (con su propio jar de cookies) por pantalla.
_sessions = {}
_sessions_lock = threading.Lock()

# Cabeceras de la respuesta original que no se reenvían al navegador.
DROPPED_HEADERS = {
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
    "set-cookie",
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
    "strict-transport-security",
    "date",
    "server",
}

META_CSP_RE = re.compile(
    r"<meta[^>]+http-equiv\s*=\s*[\"']?content-security-policy[^>]*>", re.I
)
HEAD_OPEN_RE = re.compile(r"<head(\s[^>]*)?>", re.I)


def get_session(frame_id):
    with _sessions_lock:
        session = _sessions.get(frame_id)
        if session is None:
            session = requests.Session()
            _sessions[frame_id] = session
        return session


FRAME_INJECT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "js", "frame-inject.js")


def frame_script(frame_id, device_id):
    """Script que se inyecta en cada página para que enlaces, formularios y
    peticiones sigan pasando por el proxy (ver static/js/frame-inject.js)."""
    with open(FRAME_INJECT_PATH, encoding="utf-8") as f:
        source = f.read()
    source = source.replace("__FRAME__", json.dumps(frame_id)).replace("__DEVICE__", json.dumps(device_id))
    return "<script>" + source.replace("</", "<\\/") + "</script>"


# Mensajes que se muestran dentro de una pantalla cuando la página no carga.
# El idioma llega como ?lang= desde la interfaz (inglés por defecto).
ERRORS = {
    "en": {
        "title": "Couldn't load the page",
        "invalid_url": "This address isn't valid. Use a URL that starts with http:// or https://.",
        "unknown_device": "Unknown device.",
        "timeout": "The site took too long to respond.",
        "connect": "Couldn't connect to the site ({name}).",
    },
    "es": {
        "title": "No se pudo cargar la página",
        "invalid_url": "La dirección no es válida. Usa una URL que empiece con http:// o https://.",
        "unknown_device": "Dispositivo desconocido.",
        "timeout": "El sitio tardó demasiado en responder.",
        "connect": "No se pudo conectar con el sitio ({name}).",
    },
}


def error_page(key, url, **fmt):
    lang = request.args.get("lang", "en")
    strings = ERRORS.get(lang, ERRORS["en"])
    page = render_template(
        "frame_error.html",
        lang=lang if lang in ERRORS else "en",
        title=strings["title"],
        message=strings[key].format(**fmt),
        url=url,
    )
    return Response(page, status=502, mimetype="text/html")


@app.route("/")
def index():
    return render_template(
        "index.html", devices=DEVICES, default_device_ids=DEFAULT_DEVICE_IDS
    )


# Cabeceras de la petición que sí se reenvían al sitio (además de las que
# empiezan con X-, como X-Requested-With o X-CSRF-Token).
FORWARDED_REQUEST_HEADERS = ("Content-Type", "Authorization")


@app.route("/proxy", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy():
    url = (request.args.get("url") or "").strip()
    frame_id = re.sub(r"[^A-Za-z0-9_-]", "", request.args.get("frame", ""))[:64] or "default"
    device = DEVICES_BY_ID.get(request.args.get("device", ""))

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return error_page("invalid_url", url)
    if device is None:
        return error_page("unknown_device", url)

    headers = {
        "User-Agent": device["ua"],
        "Accept": request.headers.get(
            "Accept", "text/html,application/xhtml+xml,*/*;q=0.8"
        ),
        "Accept-Language": request.headers.get("Accept-Language", "en-US,en;q=0.9"),
    }
    for name in FORWARDED_REQUEST_HEADERS:
        if name in request.headers:
            headers[name] = request.headers[name]
    for name, value in request.headers.items():
        if name.lower().startswith("x-") and not name.lower().startswith("x-forwarded"):
            headers[name] = value

    data = None
    if request.method != "GET":
        data = request.get_data()
        # Muchos sitios rechazan un POST (login, CSRF) si Origin/Referer no son
        # los suyos. El navegador mandaría los del visor, así que ponemos los del sitio.
        site = f"{parsed.scheme}://{parsed.netloc}"
        headers["Origin"] = site
        headers["Referer"] = site + "/"

    try:
        upstream = get_session(frame_id).request(
            request.method, url, headers=headers, data=data,
            timeout=REQUEST_TIMEOUT, allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return error_page("timeout", url)
    except requests.exceptions.RequestException as exc:
        return error_page("connect", url, name=exc.__class__.__name__)

    content_type = upstream.headers.get("Content-Type", "")
    body = upstream.content

    # Solo se inyecta en documentos que se van a mostrar en una pantalla; un
    # fragmento HTML pedido con fetch (por ejemplo htmx) se deja intacto.
    is_document = request.headers.get("Sec-Fetch-Dest", "iframe") in ("iframe", "frame", "document")

    if "text/html" in content_type and is_document:
        if "charset" not in content_type.lower():
            # Sin charset en la cabecera, requests asume ISO-8859-1; mejor adivinar.
            upstream.encoding = upstream.apparent_encoding or "utf-8"
        text = upstream.text
        text = META_CSP_RE.sub("", text)
        injection = f'<base href="{html.escape(upstream.url, quote=True)}">' + frame_script(frame_id, device["id"])
        if HEAD_OPEN_RE.search(text):
            text = HEAD_OPEN_RE.sub(lambda m: m.group(0) + injection, text, count=1)
        else:
            text = injection + text
        body = text.encode("utf-8")
        content_type = "text/html; charset=utf-8"

    resp = Response(body, status=upstream.status_code)
    for name, value in upstream.headers.items():
        if name.lower() not in DROPPED_HEADERS and name.lower() != "content-type":
            resp.headers[name] = value
    resp.headers["Content-Type"] = content_type or "application/octet-stream"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/reset", methods=["POST"])
def reset():
    """Borra todas las cookies: las del servidor (un jar por pantalla) y las
    que el navegador guardó para este origen."""
    with _sessions_lock:
        cleared = len(_sessions)
        for session in _sessions.values():
            session.close()
        _sessions.clear()

    resp = jsonify({"ok": True, "cleared_sessions": cleared})
    resp.headers["Clear-Site-Data"] = '"cookies"'
    # Respaldo para navegadores que ignoran Clear-Site-Data.
    for name in request.cookies:
        resp.delete_cookie(name)
    return resp


def find_free_port(preferred, attempts=20):
    """Devuelve el primer puerto libre a partir de `preferred`."""
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit(f"No free port found between {preferred} and {preferred + attempts - 1}.")


def main():
    parser = argparse.ArgumentParser(description="Responsive Viewer")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5050)),
                        help="port to use (default 5050, or the next free one)")
    parser.add_argument("--no-browser", action="store_true",
                        help="don't open the browser automatically")
    parser.add_argument("--debug", action="store_true",
                        help="reload the server when the code changes (for development)")
    args = parser.parse_args()

    # Con --debug, Flask arranca el servidor dos veces (el segundo proceso
    # trae WERKZEUG_RUN_MAIN): solo el primero busca puerto y abre el navegador.
    reloaded = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if reloaded:
        port = int(os.environ["RV_PORT"])
    else:
        # El puerto 5000 lo usa AirPlay en macOS; por eso 5050 por defecto.
        port = find_free_port(args.port)
        os.environ["RV_PORT"] = str(port)
        url = f"http://127.0.0.1:{port}"
        print(f"\n  Responsive Viewer is running at {url}", flush=True)
        print("  Press Ctrl+C to stop it.\n", flush=True)
        if not args.no_browser:
            threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    if not args.debug:
        # Sin el aviso rojo de "development server" ni una línea por cada
        # petición: para quien solo usa el visor, eso es ruido.
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        flask_cli.show_server_banner = lambda *a, **k: None

    app.run(host="127.0.0.1", port=port, debug=args.debug)


if __name__ == "__main__":
    main()
