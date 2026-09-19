"""Motor del torneo de animales arbitrado por Jev (TypeSafe System One).

Lo usan por igual la versión de Terminal (`torneo.py`) y la web local (`app.py`).
Sin dependencias: solo biblioteca estándar. La llave nunca se imprime ni se guarda aquí.
"""
import csv
import http.client
import json
import os
import random
import queue
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HOST, RUTA = "api.typesafe.ai", "/v1/systemone"
PRECIO_POR_MTOK = 0.042  # US$ por millón de tokens de entrada; la salida es gratis
ENV = Path.home() / "jev-ultrafast" / ".env"

COMUN = "Pelea uno contra uno entre dos animales adultos y sanos, hasta que uno muere o ya no puede seguir. "
ARENAS = {
    "tierra": {
        "nombre": "Tierra",
        "arena": "Domo cerrado sobre tierra firme y seca, de 100 metros de diámetro y 30 metros de alto. "
        "No hay agua. Ningún animal puede salir.",
        "reglas": COMUN + "Un animal marino está fuera del agua: según su especie queda indefenso o se mueve "
        "con torpeza. Un animal volador puede volar dentro del domo.",
    },
    "agua": {
        "nombre": "Agua",
        "arena": "Mar abierto y profundo, lejos de la costa. No hay tierra, fondo alcanzable ni objetos "
        "flotantes. Ningún animal puede salir de la zona.",
        "reglas": COMUN + "Los dos empiezan dentro del agua. Un animal marino está en su medio. Un animal "
        "terrestre tiene que nadar: según su especie nada bien, nada mal o se ahoga. Un animal volador puede "
        "volar sobre el agua, pero no tiene dónde posarse y termina agotado.",
    },
    "aire": {
        "nombre": "Aire",
        "arena": "Cielo abierto a 1,000 metros de altura sobre un desierto de roca. No hay plataformas ni "
        "dónde posarse hasta llegar al suelo.",
        "reglas": COMUN + "Los dos son soltados a la vez desde esa altura. Un animal volador puede volar y "
        "atacar en el aire. Un animal que no vuela cae hasta el suelo: los animales grandes y pesados mueren "
        "por la caída; los muy pequeños y livianos, como insectos, arañas o ratones, suelen sobrevivirla. "
        "Gana el que queda vivo y en mejores condiciones.",
    },
}
ARENA_SORTEO = "sorteo"  # cada pelea cae en una arena al azar


# ---------------------------------------------------------------- cliente de Jev
def llave():
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key and ENV.exists():
        for line in ENV.read_text().splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit(f"Falta la llave: define TYPESAFE_API_KEY o ponla en {ENV}")
    return key


def _tls():
    """El Python de python.org en macOS viene sin CA raíz: se usa un almacén de respaldo.
    La verificación de certificados nunca se desactiva."""
    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"]:
        return context
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for bundle in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if os.path.exists(bundle):
            return ssl.create_default_context(cafile=bundle)
    sys.exit("No hay certificados raíz disponibles para verificar HTTPS")


_TLS = None
_LIBRES = queue.LifoQueue()  # conexiones vivas compartidas: evitan repetir el saludo TLS en cada llamada


def _tomar(nueva=False):
    global _TLS
    if _TLS is None:
        _TLS = _tls()
    if not nueva:
        try:
            return _LIBRES.get_nowait()
        except queue.Empty:
            pass
    return http.client.HTTPSConnection(HOST, timeout=20, context=_TLS)


def calentar():
    """Abre la conexión segura por adelantado para que la primera pregunta no pague el saludo."""
    try:
        conexion = _tomar(nueva=True)
        conexion.connect()
        _LIBRES.put(conexion)
    except OSError:
        pass  # sin red ahora mismo: se abrirá con la primera pregunta


def preguntar(key, estado, preguntas, modelo="jev-latest", intentos=5):
    """Una llamada a Jev. Devuelve la respuesta con `ms` = latencia medida de esa llamada."""
    body = json.dumps({"model": modelo, "state": estado, "questions": preguntas}).encode()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for intento in range(intentos):
        inicio = time.perf_counter()
        conexion = _tomar(nueva=intento > 0)
        try:
            conexion.request("POST", RUTA, body=body, headers=headers)
            respuesta = conexion.getresponse()
            texto = respuesta.read()
            _LIBRES.put(conexion)
        except ssl.SSLCertVerificationError as error:
            raise RuntimeError(f"No se pudo verificar el certificado de TypeSafe: {error}") from None
        except (http.client.HTTPException, OSError) as error:  # conexión caída o vencida: se reabre
            conexion.close()
            if intento < intentos - 1:
                time.sleep(0.3 * 2**intento if intento else 0)
                continue
            raise RuntimeError(f"Sin conexión con TypeSafe: {error}") from None
        if respuesta.status == 200:
            data = json.loads(texto)
            data["ms"] = round((time.perf_counter() - inicio) * 1000)
            return data
        if respuesta.status in (429, 503, 529) and intento < intentos - 1:
            time.sleep(0.6 * 2**intento)
            continue
        raise RuntimeError(f"Jev respondió HTTP {respuesta.status}: {texto.decode('utf-8', 'replace')[:300]}")


# ---------------------------------------------------------------- torneo
def cargar_animales(ruta=AQUI / "animales.csv"):
    with open(ruta, encoding="utf-8") as handle:
        return [{"nombre": r["nombre"], "tipo": r["tipo"], "clase": r["clase"]} for r in csv.DictReader(handle)]


def _ficha(animal):
    # La clase evita la lectura literal de nombres ambiguos («Avión zapador» es un ave, no un avión).
    return f"{animal['nombre']} ({animal['clase']}; animal {animal['tipo']})"


def _pregunta(a, b, arena, mixto, rng):
    """Una pelea = un `choice` entre los dos nombres. El orden se baraja porque Jev favorece
    levemente (~0.1) a la opción que aparece primero."""
    primero, segundo = (a, b) if rng.random() < 0.5 else (b, a)
    donde = (
        f"La pelea ocurre en `arenas.{arena}.arena` y sigue `arenas.{arena}.reglas`. ¿Qué animal gana?"
        if mixto
        else "Según `reglas` y `arena`, ¿qué animal gana esta pelea?"
    )
    return {
        "type": "choice",
        "instructions": {"pregunta": donde, "animal_1": _ficha(primero), "animal_2": _ficha(segundo)},
        "criteria": {primero["nombre"]: None, segundo["nombre"]: None},
    }


def torneo(animales, n=None, arena="tierra", modo="turbo", azar=False, semilla=None, tipos=None,
           modelo="jev-latest", cancelar=None, guardar=True, por_tipo=None):
    """Generador de eventos del torneo «el ganador se queda».

    modo «turbo»: fan-out especulativo — en UNA llamada se pregunta «campeón contra cada uno de los
    próximos K retadores»; se recorren en orden y, si el campeón cae, las respuestas que sobran se
    descartan (eran contra el campeón viejo). modo «una»: una llamada por pelea, para ver la
    latencia real de cada respuesta.
    """
    if arena != ARENA_SORTEO and arena not in ARENAS:
        raise ValueError("Arena desconocida")
    semilla = semilla if semilla is not None else random.randrange(10**6)
    rng = random.Random(semilla)
    if por_tipo:
        # Cupo por tipo (terrestre / volador / marino): el total del torneo es la suma.
        cola = []
        for tipo, cuantos in por_tipo.items():
            grupo = [a for a in animales if a["tipo"] == tipo]
            if not 0 <= cuantos <= len(grupo):
                raise ValueError(f"De tipo {tipo} hay {len(grupo)} animales; pediste {cuantos}")
            cola += rng.sample(grupo, cuantos)
        rng.shuffle(cola)
        n = len(cola)
        if n < 2:
            raise ValueError("Hacen falta al menos 2 animales en total")
    else:
        if tipos:
            animales = [a for a in animales if a["tipo"] in tipos]
        if n is None or not 2 <= n <= len(animales):
            raise ValueError(f"El número de animales debe estar entre 2 y {len(animales)}")
        cola = rng.sample(animales, n)
    campeon, cola = cola[0], cola[1:]
    mixto = arena == ARENA_SORTEO
    estado = {"arenas": {k: {"arena": v["arena"], "reglas": v["reglas"]} for k, v in ARENAS.items()}} if mixto \
        else {"arena": ARENAS[arena]["arena"], "reglas": ARENAS[arena]["reglas"]}
    key = llave()
    yield {"t": "inicio", "n": n, "semilla": semilla, "arena": arena, "modo": modo, "azar": azar, "campeon": campeon}

    peleas, racha, llamadas, tokens, ms_jev, inicio = [], 0, 0, 0, 0, time.perf_counter()
    while cola and not (cancelar and cancelar.is_set()):
        # El lote crece con la racha: un campeón recién coronado puede caer pronto (y lo que sobra del
        # lote se descarta); uno con racha larga suele seguir ganando, así que conviene preguntar más.
        lote = cola[: 1 if modo == "una" else min(50, max(2, racha + 1))]
        arenas_lote = [rng.choice(list(ARENAS)) if mixto else arena for _ in lote]
        preguntas = {f"p{i}": _pregunta(campeon, r, arenas_lote[i], mixto, rng) for i, r in enumerate(lote)}
        data = preguntar(key, estado, preguntas, modelo)
        llamadas += 1
        tokens += data.get("usage", {}).get("input_tokens", 0)
        ms_jev += data["ms"]
        yield {"t": "llamada", "ms": data["ms"], "preguntas": len(lote), "llamadas": llamadas,
               "tokens": tokens, "ms_jev": ms_jev, "modelo": data.get("model")}
        for i, retador in enumerate(lote):
            r = data["answers"][f"p{i}"]
            p_campeon = r["probabilities"][campeon["nombre"]]
            gana_campeon = (rng.random() < p_campeon) if azar else (r["choice"] == campeon["nombre"])
            ganador = campeon if gana_campeon else retador
            p_ganador = p_campeon if gana_campeon else 1 - p_campeon
            cola.pop(0)
            racha = racha + 1 if gana_campeon else 0
            pelea = {"pelea": len(peleas) + 1, "arena": arenas_lote[i], "campeon": campeon["nombre"],
                     "retador": retador["nombre"], "ganador": ganador["nombre"], "prob_ganador": round(p_ganador, 3),
                     "confianza": r["confidence"], "sorpresa": p_ganador < 0.5}
            peleas.append(pelea)
            yield {"t": "pelea", **pelea, "ficha_campeon": campeon, "ficha_retador": retador,
                   "destrona": not gana_campeon, "racha": racha, "restantes": len(cola)}
            if not gana_campeon:
                campeon = retador
                break  # el resto del lote se preguntó contra el campeón viejo: se descarta

    segundos = time.perf_counter() - inicio
    reinados, actual = [], None
    for p in peleas:
        if actual is None or actual["nombre"] != p["campeon"]:
            actual = {"nombre": p["campeon"], "victorias": 0}
            reinados.append(actual)
        if p["ganador"] == p["campeon"]:
            actual["victorias"] += 1
    if peleas and peleas[-1]["ganador"] != peleas[-1]["campeon"]:
        reinados.append({"nombre": peleas[-1]["ganador"], "victorias": 0})
    archivo = None
    if guardar and peleas:
        archivo = AQUI / "resultados" / f"torneo_{datetime.now():%Y%m%d_%H%M%S}_n{n}_{arena}_s{semilla}.csv"
        archivo.parent.mkdir(exist_ok=True)
        with open(archivo, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(peleas[0]))
            writer.writeheader()
            writer.writerows(peleas)
    yield {"t": "fin", "cancelado": bool(cancelar and cancelar.is_set()), "campeon": campeon, "racha": racha,
           "peleas": len(peleas), "llamadas": llamadas, "segundos": round(segundos, 2), "ms_jev": ms_jev,
           "tokens": tokens, "costo": round(tokens * PRECIO_POR_MTOK / 1e6, 6), "semilla": semilla,
           "reinados": sorted(reinados, key=lambda x: -x["victorias"])[:10], "campeones": len(reinados),
           "cerradas": sorted(peleas, key=lambda x: abs(x["prob_ganador"] - 0.5))[:8],
           "sorpresas": [p for p in peleas if p["sorpresa"]][:8],
           "archivo": str(archivo) if archivo else None}


def duelo(a, b, modelo="jev-latest"):
    """Pelea individual entre dos animales elegidos. En UNA llamada se pregunta por las tres arenas
    y en los dos órdenes (6 decisiones); promediar ambos órdenes cancela el sesgo de posición."""
    estado = {"arenas": {k: {"arena": v["arena"], "reglas": v["reglas"]} for k, v in ARENAS.items()}}
    preguntas = {}
    for arena in ARENAS:
        for orden, (x, y) in (("ab", (a, b)), ("ba", (b, a))):
            preguntas[f"{arena}_{orden}"] = {
                "type": "choice",
                "instructions": {"pregunta": f"La pelea ocurre en `arenas.{arena}.arena` y sigue "
                                 f"`arenas.{arena}.reglas`. ¿Qué animal gana?",
                                 "animal_1": _ficha(x), "animal_2": _ficha(y)},
                "criteria": {x["nombre"]: None, y["nombre"]: None},
            }
    data = preguntar(llave(), estado, preguntas, modelo)
    veredictos = {}
    for arena in ARENAS:
        r1, r2 = data["answers"][f"{arena}_ab"], data["answers"][f"{arena}_ba"]
        p_a = (r1["probabilities"][a["nombre"]] + r2["probabilities"][a["nombre"]]) / 2
        gana_a = p_a >= 0.5
        veredictos[arena] = {"ganador": (a if gana_a else b)["nombre"], "prob_ganador": round(p_a if gana_a else 1 - p_a, 3),
                             "prob_a": round(p_a, 3), "confianza": round((r1["confidence"] + r2["confidence"]) / 2, 3)}
    tokens = data.get("usage", {}).get("input_tokens", 0)
    return {"a": a, "b": b, "arenas": veredictos, "ms": data["ms"], "preguntas": len(preguntas), "tokens": tokens,
            "costo": round(tokens * PRECIO_POR_MTOK / 1e6, 6), "modelo": data.get("model")}
