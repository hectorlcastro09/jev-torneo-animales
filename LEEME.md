# Torneo de animales arbitrado por Jev

Juego local para *ver* lo rápido que decide **Jev**, el modelo System One de TypeSafe.
Hasta 2,569 animales (terrestres, voladores y marinos) pelean uno contra uno; **el ganador se queda** y enfrenta
al siguiente hasta que queda un solo campeón. Cada pelea la decide Jev. *(English: [README.md](README.md))*

Medido en una laptop: 2,000 animales → **1,999 peleas en ~16 s**, 64 llamadas, **~7.6 ms por decisión**, ~US$ 0.01.
Una pelea individual responde en ~220 ms, y esa sola llamada ya dice quién gana en tierra, en agua y en aire.

## Para usarlo

Sin dependencias: basta Python 3.10 o superior. Hace falta una llave propia de TypeSafe
([console.typesafe.ai](https://console.typesafe.ai/settings/keys), acceso anticipado).

    git clone https://github.com/hectorlcastro09/jev-torneo-animales.git
    cd jev-torneo-animales
    cp .env.example .env      # y pega tu llave dentro de .env   (Windows: copy .env.example .env)
    python3 app.py            # abre http://127.0.0.1:8777        (Windows: python app.py)

En macOS también sirve el doble clic en `Torneo Jev.command`. En Terminal: `python3 torneo.py --n 300 --arena agua --semilla 7`.

La llave nunca sale de tu computadora salvo para llamar a TypeSafe: un servidor mínimo (solo 127.0.0.1) la guarda y habla
con Jev, porque el API de TypeSafe no acepta llamadas directas desde un navegador y una llave no debe vivir en una página web.

## Qué se puede hacer

- **Torneo:** cupo de participantes por tipo (el total es la suma), arena (**tierra**, **agua**, **aire** o sorteo por pelea),
  velocidad (turbo por lotes, o pelea por pelea para ver la latencia real) y resultado (gana el favorito, o *con azar*:
  el juego tira un dado cargado con la probabilidad de Jev, y entonces hay sorpresas).
- **Pelea individual:** eliges los dos animales y una sola llamada responde las tres arenas en ambos órdenes (6 decisiones).

## Cómo funciona

- `motor.py` — reglas de cada arena, cliente de Jev y el torneo como generador de eventos. Cada pelea es una pregunta
  `choice` entre dos nombres. En turbo usa *fan-out especulativo*: en UNA llamada pregunta «campeón contra los próximos K
  retadores», recorre las respuestas en orden y, si el campeón cae, descarta las que sobran. K crece con la racha.
- `app.py` — servidor local que transmite cada pelea en vivo (SSE). `web/index.html` es toda la pantalla.
- `animales.csv` — 2,569 animales con tipo y clase; se puede editar. `resultados/` — un CSV por torneo (no se sube a GitHub).
- Pruebas sin red: `python3 -m unittest discover -s tests -v`

## Lecciones sobre Jev

- Lee **literal**: «Avión zapador» (un ave) confundía al modelo hasta que cada animal llevó su clase (0.56 → 0.75).
- Leve **sesgo de posición** (~0.1 a favor de la opción listada primero): el orden se baraja; el duelo promedia ambos órdenes.
- Las reglas van en el `state` y cambian el resultado: león vs. tiburón blanco → león en tierra, tiburón en agua.
- Sus probabilidades se comportan como probabilidades: con azar hubo 23 sorpresas donde se esperaban 20.7; sin azar, ninguna.
- **Reutilizar la conexión:** el saludo TLS por llamada (~0.3 s) escondía la velocidad real (6 decisiones: ~500 → ~200 ms).

## Cómo se hizo

Con ayuda de IA, y se dice abiertamente: la idea, las reglas, los pedidos y las pruebas de juego son de Héctor Castro;
el código lo escribió Claude (Claude Code, de Anthropic) bajo su dirección. Se agradecen mejoras y *pull requests*.

Licencia: [MIT](LICENSE).
