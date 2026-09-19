#!/usr/bin/env python3
"""Torneo de animales con Jev — versión web local.

    python3 app.py          →  abre http://127.0.0.1:8777

El servidor solo escucha en esta Mac (127.0.0.1). La llave de TypeSafe se queda de este lado:
el navegador nunca la ve y el API de TypeSafe no admite llamadas directas desde una página.
"""
import json
import os
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import motor

PUERTO = int(os.environ.get("TORNEO_PUERTO", "8777"))
ORIGEN = f"http://127.0.0.1:{PUERTO}"
TOKEN = secrets.token_urlsafe(24)  # evita que otra página dispare torneos (y gaste saldo) por su cuenta
ANIMALES = motor.cargar_animales()
WEB = Path(__file__).resolve().parent / "web"


class Partida:
    def __init__(self):
        self.id = 0
        self.eventos = []
        self.cambio = threading.Condition()
        self.cancelar = threading.Event()
        self.hilo = None


PARTIDA = Partida()


def publicar(evento):
    with PARTIDA.cambio:
        PARTIDA.eventos.append(evento)
        PARTIDA.cambio.notify_all()


def correr(parametros):
    try:
        for evento in motor.torneo(ANIMALES, cancelar=PARTIDA.cancelar, **parametros):
            publicar(evento)
    except (ValueError, RuntimeError) as error:
        publicar({"t": "error", "mensaje": str(error)})
    except Exception as error:  # que la pantalla se entere en vez de quedarse esperando
        publicar({"t": "error", "mensaje": f"Fallo inesperado: {error}"})


def iniciar(cuerpo):
    tipos = [t for t in cuerpo.get("tipos", []) if t in ("terrestre", "volador", "marino")]
    semilla = cuerpo.get("semilla")
    parametros = {
        "n": int(cuerpo.get("n", 1000)),
        "arena": cuerpo.get("arena", "tierra"),
        "modo": "una" if cuerpo.get("modo") == "una" else "turbo",
        "azar": bool(cuerpo.get("azar")),
        "tipos": tipos or None,
        "semilla": int(semilla) if str(semilla or "").strip().lstrip("-").isdigit() else None,
    }
    if PARTIDA.hilo and PARTIDA.hilo.is_alive():
        PARTIDA.cancelar.set()
        PARTIDA.hilo.join(timeout=25)
    with PARTIDA.cambio:
        PARTIDA.id += 1
        PARTIDA.eventos = []
        PARTIDA.cancelar = threading.Event()
    PARTIDA.hilo = threading.Thread(target=correr, args=(parametros,), daemon=True)
    PARTIDA.hilo.start()
    return {"id": PARTIDA.id}


class Handler(BaseHTTPRequestHandler):
    def responder(self, status, contenido, mime="application/json"):
        contenido = contenido if isinstance(contenido, bytes) else contenido.encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(contenido)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(contenido)

    def local(self):
        return self.headers.get("Host") == f"127.0.0.1:{PUERTO}"

    def do_GET(self):
        if not self.local():
            return self.responder(403, "Prohibido", "text/plain")
        url = urlparse(self.path)
        if url.path == "/":
            html = (WEB / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
            return self.responder(200, html, "text/html; charset=utf-8")
        if url.path == "/api/meta":
            por_tipo = {t: sum(a["tipo"] == t for a in ANIMALES) for t in ("terrestre", "volador", "marino")}
            return self.responder(200, json.dumps({"total": len(ANIMALES), "por_tipo": por_tipo}))
        if url.path == "/api/eventos":
            consulta = parse_qs(url.query)
            if consulta.get("token", [""])[0] != TOKEN:
                return self.responder(403, "Prohibido", "text/plain")
            return self.transmitir(int(consulta.get("id", ["0"])[0]))
        self.responder(404, "No encontrado", "text/plain")

    def transmitir(self, partida_id):
        """Server-Sent Events: cada pelea llega a la pantalla en cuanto Jev la decide."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        # Si el navegador reconecta, manda el id del último evento que recibió: se reanuda, no se repite.
        ultimo = self.headers.get("Last-Event-ID", "")
        enviados = int(ultimo) + 1 if ultimo.isdigit() else 0
        try:
            while True:
                with PARTIDA.cambio:
                    while partida_id == PARTIDA.id and enviados >= len(PARTIDA.eventos):
                        PARTIDA.cambio.wait(timeout=15)
                        if enviados >= len(PARTIDA.eventos):
                            break
                    if partida_id != PARTIDA.id:
                        return
                    nuevos = PARTIDA.eventos[enviados:]
                if not nuevos:
                    self.wfile.write(b": sigo aqui\n\n")  # latido para que el navegador no corte
                    self.wfile.flush()
                    continue
                for numero, evento in enumerate(nuevos, enviados):
                    self.wfile.write(f"id: {numero}\ndata: {json.dumps(evento, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                enviados += len(nuevos)
                if nuevos[-1]["t"] in ("fin", "error"):
                    return
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        if (not self.local() or self.headers.get("X-Torneo-Token") != TOKEN
                or self.headers.get("Origin") not in (None, ORIGEN)):
            return self.responder(403, json.dumps({"error": "Solo se aceptan órdenes de la página local"}))
        try:
            largo = int(self.headers.get("Content-Length", "0"))
            cuerpo = json.loads(self.rfile.read(largo)) if 0 < largo < 4096 else {}
            if self.path == "/api/iniciar":
                return self.responder(200, json.dumps(iniciar(cuerpo)))
            if self.path == "/api/detener":
                PARTIDA.cancelar.set()
                return self.responder(200, json.dumps({"ok": True}))
            self.responder(404, json.dumps({"error": "No encontrado"}))
        except (ValueError, TypeError) as error:
            self.responder(400, json.dumps({"error": str(error)}))

    def log_message(self, *_args):
        pass


def main():
    motor.llave()  # falla de entrada, con mensaje claro, si no hay llave
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Handler)
    servidor.daemon_threads = True
    print(f"Torneo de animales con Jev: {ORIGEN}   (Ctrl+C para apagar)", flush=True)
    if not os.environ.get("TORNEO_NO_ABRIR"):
        threading.Timer(0.6, webbrowser.open, args=(ORIGEN,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        PARTIDA.cancelar.set()
        servidor.server_close()


if __name__ == "__main__":
    main()
