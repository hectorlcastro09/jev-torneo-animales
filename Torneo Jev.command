#!/bin/bash
# Doble clic para abrir el torneo en el navegador. Cierra esta ventana (o Ctrl+C) para apagarlo.
cd "$(dirname "$0")" && exec python3 app.py
