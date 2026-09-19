#!/usr/bin/env python3
"""Torneo de animales con Jev — versión de Terminal (la versión con pantalla es `app.py`).

  python3 torneo.py                          # 1,000 animales en tierra
  python3 torneo.py --n 300 --arena agua     # tierra | agua | aire | sorteo
  python3 torneo.py --semilla 7 --azar       # sorteo repetible; resultado sorteado con la probabilidad
  python3 torneo.py --modo una --n 30        # una llamada por pelea, para ver la latencia real
  python3 torneo.py --terrestres 800 --voladores 700 --marinos 500   # cupo por tipo: total 2,000
"""
import argparse

import motor


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=1000, help="cuántos animales participan")
    parser.add_argument("--arena", default="tierra", choices=[*motor.ARENAS, motor.ARENA_SORTEO])
    parser.add_argument("--modo", default="turbo", choices=["turbo", "una"])
    parser.add_argument("--azar", action="store_true", help="sortear cada resultado según la probabilidad")
    parser.add_argument("--semilla", type=int, help="fija el sorteo para poder repetirlo")
    parser.add_argument("--tipos", help="terrestre, volador, marino (separados por coma)")
    for tipo in ("terrestres", "voladores", "marinos"):
        parser.add_argument(f"--{tipo}", type=int, help=f"cupo de {tipo}; si das algún cupo, el total es la suma")
    args = parser.parse_args()
    tipos = [t.strip() for t in args.tipos.split(",")] if args.tipos else None
    cupos = {"terrestre": args.terrestres, "volador": args.voladores, "marino": args.marinos}
    por_tipo = {t: c or 0 for t, c in cupos.items()} if any(c is not None for c in cupos.values()) else None
    try:
        for ev in motor.torneo(motor.cargar_animales(), args.n, args.arena, args.modo, args.azar, args.semilla, tipos,
                               por_tipo=por_tipo):
            if ev["t"] == "inicio":
                print(f"TORNEO · {ev['n']} animales · arena {ev['arena']} · semilla {ev['semilla']}\n"
                      f"Abre el combate: {ev['campeon']['nombre']}\n")
            elif ev["t"] == "pelea" and ev["destrona"]:
                print(f"  pelea {ev['pelea']:>4}: {ev['retador']} destrona a {ev['campeon']} · prob "
                      f"{ev['prob_ganador']:.2f}{'  ¡SORPRESA!' if ev['sorpresa'] else ''}")
            elif ev["t"] == "fin":
                print(f"\nCAMPEÓN: {ev['campeon']['nombre']} — cerró con {ev['racha']} victorias seguidas "
                      f"({ev['campeones']} campeones en total)")
                for r in ev["reinados"][:6]:
                    print(f"   {r['victorias']:>4} victorias · {r['nombre']}")
                decision = ev["ms_jev"] / max(1, ev["peleas"])
                print(f"\n{ev['peleas']} peleas · {ev['llamadas']} llamadas · {ev['segundos']} s · "
                      f"{decision:.0f} ms por pelea · {ev['tokens']:,} tokens ≈ US$ {ev['costo']:.4f}\n{ev['archivo']}")
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error))


if __name__ == "__main__":
    main()
