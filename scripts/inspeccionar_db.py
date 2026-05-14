"""
scripts/inspeccionar_db.py — Inspección rápida del estado de la base de datos.

Uso:
    python scripts/inspeccionar_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from config import config


def main():
    db = Path(config.DB_PATH)
    if not db.exists():
        print(f"❌ No existe la DB en: {db}")
        return

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    print(f"\n📂 Base de datos: {db.resolve()}")
    print(f"   Tamaño: {db.stat().st_size / 1024:.1f} KB\n")

    # ── Favoritos ────────────────────────────────────────────────────────────
    fav = conn.execute("SELECT COUNT(*) as n FROM favoritos").fetchone()
    print(f"🔖 Favoritos guardados:        {fav['n']}")

    # ── Consultas ────────────────────────────────────────────────────────────
    c = conn.execute("SELECT COUNT(*) as n FROM consultas").fetchone()
    print(f"\n📊 Consultas totales:          {c['n']}")

    origenes = conn.execute(
        "SELECT origen, COUNT(*) as n FROM consultas GROUP BY origen ORDER BY n DESC"
    ).fetchall()
    for o in origenes:
        print(f"   • {o['origen']:<15} {o['n']:>6}")

    # ── Arrivals ─────────────────────────────────────────────────────────────
    a = conn.execute("SELECT COUNT(*) as n FROM arribos_historico").fetchone()
    primer = conn.execute(
        "SELECT COUNT(*) as n FROM arribos_historico WHERE es_primer_avistamiento=1"
    ).fetchone()
    print(f"\n🚌 Arrivals totales:           {a['n']}")
    print(f"   • Primeros avistamientos:  {primer['n']}")
    print(f"   • Repeticiones:            {a['n'] - primer['n']}")

    # ── Por línea (top 10) ───────────────────────────────────────────────────
    lineas = conn.execute("""
        SELECT cartel,
               COUNT(*) as total,
               SUM(es_primer_avistamiento) as unicos,
               ROUND(AVG(CASE WHEN es_primer_avistamiento=1 AND minutos_estimados > 0
                              THEN minutos_estimados END), 1) as espera_prom
        FROM arribos_historico
        GROUP BY cartel
        ORDER BY unicos DESC
        LIMIT 10
    """).fetchall()

    if lineas:
        print(f"\n📈 Top líneas registradas:")
        print(f"   {'Línea':<15} {'Total':>6} {'Únicos':>7} {'Espera prom':>12}")
        print(f"   {'-'*15} {'-'*6} {'-'*7} {'-'*12}")
        for l in lineas:
            espera = f"{l['espera_prom']} min" if l['espera_prom'] else "  —"
            print(f"   {l['cartel']:<15} {l['total']:>6} {l['unicos']:>7} {espera:>12}")

    # ── Rango temporal ───────────────────────────────────────────────────────
    rango = conn.execute("""
        SELECT MIN(timestamp) as desde, MAX(timestamp) as hasta
        FROM consultas
    """).fetchone()
    if rango["desde"]:
        print(f"\n📅 Período registrado:")
        print(f"   Desde: {rango['desde'][:19].replace('T', ' ')}")
        print(f"   Hasta: {rango['hasta'][:19].replace('T', ' ')}")

    # ── Usuarios únicos ──────────────────────────────────────────────────────
    usuarios = conn.execute("""
        SELECT COUNT(DISTINCT user_id_hash) as n
        FROM consultas WHERE user_id_hash IS NOT NULL
    """).fetchone()
    print(f"\n👤 Usuarios únicos del bot:    {usuarios['n']}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
