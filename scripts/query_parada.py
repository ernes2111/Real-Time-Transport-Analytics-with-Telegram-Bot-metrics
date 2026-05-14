"""
scripts/query_parada.py — Script CLI para consultar una parada directamente desde la terminal.

Uso:
    python scripts/query_parada.py 5742
    python scripts/query_parada.py 5742 --linea 122
"""

import sys
import argparse
from pathlib import Path

# Aseguramos acceso al root del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.consulta_service import ConsultaService
from src.api.client import APIError, ParadaNoEncontrada
from src.formatters.text_formatter import formato_consola, formato_sin_paradas


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consulta los arribos de colectivos a una parada de Rosario."
    )
    parser.add_argument("parada", help="Número de parada (ej: 5742)")
    parser.add_argument("--linea", help="Filtrar por número de línea (ej: 122)", default=None)
    args = parser.parse_args()

    try:
        with ConsultaService() as service:
            resultado = service.consultar_parada(args.parada)

            if args.linea:
                resultado = service.filtrar_por_linea(resultado, args.linea)

        print(formato_consola(resultado))

    except ParadaNoEncontrada:
        print(f"❌ No se encontró la parada {args.parada}.")
        sys.exit(1)
    except APIError as e:
        print(f"⚠️  Error de conexión: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
