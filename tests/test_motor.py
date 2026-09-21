"""Pruebas sin red: Jev se sustituye por un árbitro falso y determinista.

    python3 -m unittest discover -s tests -v

Fallan si se rompe la lógica del torneo (el ganador se queda, descarte de respuestas
especulativas, cupos por tipo, barajado del orden) o el promedio de órdenes del duelo.
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import motor  # noqa: E402

ANIMALES = [{"nombre": f"{tipo[:3]}-{i:03d}", "tipo": tipo, "clase": "prueba"}
            for tipo in ("terrestre", "volador", "marino") for i in range(60)]
FUERZA = {a["nombre"]: (i * 37) % 181 for i, a in enumerate(ANIMALES)}  # fuerzas distintas y revueltas


class ArbitroFalso:
    """Imita la respuesta de Jev a preguntas `choice` de dos opciones."""

    def __init__(self, sesgo_primero=0.0, pendiente=1.0):
        self.sesgo, self.pendiente, self.llamadas = sesgo_primero, pendiente, []

    def __call__(self, key, estado, preguntas, modelo="jev-latest", intentos=5):
        self.llamadas.append(preguntas)
        respuestas = {}
        for qid, q in preguntas.items():
            primero, segundo = list(q["criteria"])
            p = 1 / (1 + math.exp(-(FUERZA[primero] - FUERZA[segundo]) * self.pendiente))
            p = min(1.0, max(0.0, p + self.sesgo))
            respuestas[qid] = {"type": "choice", "choice": primero if p >= 0.5 else segundo,
                               "probabilities": {primero: p, segundo: 1 - p}, "confidence": abs(2 * p - 1)}
        return {"answers": respuestas, "usage": {"input_tokens": 10 * len(preguntas)}, "ms": 1, "model": "falso"}


class Torneo(unittest.TestCase):
    def setUp(self):
        self.arbitro = ArbitroFalso()
        self._reales = motor.preguntar, motor.llave
        motor.preguntar, motor.llave = self.arbitro, lambda: "llave-de-prueba"

    def tearDown(self):
        motor.preguntar, motor.llave = self._reales

    def jugar(self, **kw):
        eventos = list(motor.torneo(ANIMALES, guardar=False, **kw))
        return [e for e in eventos if e["t"] == "pelea"], eventos[-1], eventos[0]

    def test_gana_el_mas_fuerte_y_todos_pelean_una_vez(self):
        peleas, fin, inicio = self.jugar(n=120, semilla=5)
        participantes = [inicio["campeon"]["nombre"]] + [p["retador"] for p in peleas]
        self.assertEqual(len(peleas), 119)
        self.assertEqual(len(set(participantes)), 120, "cada animal entra exactamente una vez")
        self.assertEqual(fin["campeon"]["nombre"], max(participantes, key=FUERZA.get))
        self.assertFalse(any(p["sorpresa"] for p in peleas), "sin azar nunca gana el menos probable")

    def test_el_ganador_de_cada_pelea_es_el_campeon_de_la_siguiente(self):
        # Si las respuestas especulativas no se descartaran al caer el campeón, esta cadena se rompería.
        peleas, _, _ = self.jugar(n=150, semilla=9)
        for anterior, siguiente in zip(peleas, peleas[1:]):
            self.assertEqual(anterior["ganador"], siguiente["campeon"])
        self.assertLess(len(self.arbitro.llamadas), 149, "turbo debe agrupar peleas en menos llamadas")

    def test_modo_una_pregunta_por_llamada(self):
        peleas, fin, _ = self.jugar(n=25, semilla=2, modo="una")
        self.assertTrue(all(len(q) == 1 for q in self.arbitro.llamadas))
        self.assertEqual(fin["llamadas"], len(peleas))

    def test_cupos_por_tipo(self):
        peleas, _, inicio = self.jugar(por_tipo={"terrestre": 10, "volador": 7, "marino": 4}, semilla=3)
        fichas = [inicio["campeon"]] + [p["ficha_retador"] for p in peleas]
        conteo = {t: sum(f["tipo"] == t for f in fichas) for t in ("terrestre", "volador", "marino")}
        self.assertEqual(conteo, {"terrestre": 10, "volador": 7, "marino": 4})
        with self.assertRaises(ValueError):
            self.jugar(por_tipo={"terrestre": 61, "volador": 0, "marino": 0})
        with self.assertRaises(ValueError):
            self.jugar(por_tipo={"terrestre": 1, "volador": 0, "marino": 0})

    def test_misma_semilla_mismo_torneo(self):
        a, _, _ = self.jugar(n=80, semilla=11, azar=True)
        b, _, _ = self.jugar(n=80, semilla=11, azar=True)
        self.assertEqual([p["ganador"] for p in a], [p["ganador"] for p in b])

    def test_con_azar_hay_sorpresas_y_son_los_menos_probables(self):
        self.arbitro.pendiente = 0.01  # peleas parejas: probabilidades cerca de 0.5
        peleas, _, _ = self.jugar(n=180, semilla=4, azar=True)
        sorpresas = [p for p in peleas if p["sorpresa"]]
        self.assertGreater(len(sorpresas), 10)
        self.assertTrue(all(p["prob_ganador"] < 0.5 for p in sorpresas))

    def test_el_orden_de_las_opciones_se_baraja(self):
        self.jugar(n=100, semilla=6)
        campeon_primero = [list(q["criteria"])[0] == q["instructions"]["animal_1"].split(" (")[0]
                           for llamada in self.arbitro.llamadas for q in llamada.values()]
        self.assertTrue(all(campeon_primero), "animal_1 debe coincidir con la primera opción")
        posiciones = set()
        for llamada in self.arbitro.llamadas:
            nombres = [list(q["criteria"]) for q in llamada.values()]
            comun = set(nombres[0]).intersection(*map(set, nombres[1:])) if len(nombres) > 1 else set()
            for par in nombres:
                posiciones.update(par.index(c) for c in comun)
        self.assertEqual(posiciones, {0, 1}, "el campeón debe aparecer a veces primero y a veces segundo")

    def test_arena_desconocida(self):
        with self.assertRaises(ValueError):
            self.jugar(n=10, arena="luna")


class Duelo(unittest.TestCase):
    def test_promediar_los_dos_ordenes_cancela_el_sesgo_de_posicion(self):
        reales = motor.preguntar, motor.llave
        arbitro = ArbitroFalso(sesgo_primero=0.1, pendiente=0.0)  # fuerzas iguales; ventaja solo por ir primero
        motor.preguntar, motor.llave = arbitro, lambda: "llave-de-prueba"
        try:
            r = motor.duelo(ANIMALES[0], ANIMALES[1])
        finally:
            motor.preguntar, motor.llave = reales
        self.assertEqual(len(arbitro.llamadas), 1, "las tres arenas y los dos órdenes van en UNA llamada")
        self.assertEqual(r["preguntas"], 6)
        for arena in motor.ARENAS:
            self.assertAlmostEqual(r["arenas"][arena]["prob_a"], 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
