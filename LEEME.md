# Torneo de animales arbitrado por Jev

Ejercicio para aprender **Jev** (el modelo System One de TypeSafe) y *ver* lo rápido que decide.
Se sortean N animales (voladores, terrestres y marinos); pelean uno contra uno y **el ganador se queda**
para enfrentar al siguiente, hasta que queda un solo campeón: N − 1 peleas, cada una decidida por Jev.

## Usarlo

- **Con pantalla:** doble clic en `Torneo Jev.command` (o `python3 app.py`) → abre http://127.0.0.1:8777
- **En Terminal:** `python3 torneo.py --n 300 --arena agua --semilla 7`

**Torneo:** cupo de participantes por tipo (terrestres, voladores, marinos) — el total es la suma, hasta 2,569;
atajos para repartir 100 / 500 / 1,000 / 2,000 / todos. Arena (**tierra**, **agua**, **aire** o sorteo por pelea),
velocidad (turbo por lotes, o pelea por pelea para ver la latencia real de cada respuesta) y
resultado (gana el favorito, o sorteado con la probabilidad de Jev).

**Pelea individual:** eliges los dos animales (con búsqueda o al azar) y Jev responde, en UNA llamada,
quién gana en tierra, en agua y en aire (6 decisiones: 3 lugares × 2 órdenes, promediados para cancelar el sesgo de posición).

Referencia medida: 2,000 animales en tierra = 1,999 peleas en ~17 s, 64 llamadas, ~8 ms por decisión, US$ 0.01.
Una pelea individual: ~200–300 ms.

## Cómo funciona

- `motor.py` — reglas de cada arena, cliente de Jev y el torneo como generador de eventos.
  Cada pelea es una pregunta `choice` entre dos nombres. En modo turbo usa *fan-out especulativo*:
  en UNA llamada pregunta «campeón contra los próximos K retadores», recorre las respuestas en orden y,
  si el campeón cae, descarta las que sobran. K crece con la racha del campeón.
- `app.py` — servidor local (solo 127.0.0.1) que sirve `web/index.html` y transmite las peleas en vivo (SSE).
- `animales.csv` — 2,569 animales con tipo y clase; se puede editar a mano.
- `resultados/` — un CSV por torneo (no se sube a GitHub).

## La llave

No está en este repositorio. Se lee de la variable `TYPESAFE_API_KEY` o de `~/jev-ultrafast/.env`.
Por eso el juego corre en localhost y no como página pública: el API de TypeSafe no acepta llamadas
directas desde un navegador y la llave debe quedarse del lado del servidor.

## Lecciones que dejó el ejercicio

- Jev lee **literal**: «Avión zapador» (un ave) confundía al modelo hasta que cada animal llevó su clase.
- Leve **sesgo de posición** (~0.1 a favor de la opción listada primero): el orden se baraja en cada pelea.
- Las reglas de la arena van en el `state`; cambiar de tierra a agua invierte resultados (león vs. tiburón).
- La **conexión se reutiliza** (y se abre por adelantado al arrancar): el saludo TLS costaba ~0.3 s por llamada y
  escondía la velocidad real de Jev (una llamada con 6 decisiones baja de ~500 ms a ~200 ms).
- El sorteo lo hace el código, no Jev: a igual entrada, Jev responde igual. La semilla hace repetible el torneo.
