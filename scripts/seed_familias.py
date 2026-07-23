#!/usr/bin/env python3
"""Siembra inicial de familias en Postgres (una sola vez).

Crea las familias y asigna `socios.familia_id`. Después de esto, la fuente de
verdad es la base: la app de escritorio podrá editar familias y esos cambios se
reflejan en el bot. Por eso este script es un bootstrap de una sola pasada — NO
se corre en cada deploy (si no, pisaría lo que edite la app).

Requisitos: el esquema ya debe tener la tabla `familias` y la columna
`socios.familia_id` (las crea/migra la API al arrancar).

Uso:
    uv run python scripts/seed_familias.py \\
        --postgres "postgresql://user:pass@host:puerto/dbname"

Mapeo: cada entrada de FAMILIAS es (nombre_familia, [ids de socios]). Los IDs
corresponden a la BGC-software.db (preservados en el seed inicial).
"""

from __future__ import annotations

import argparse
import sys

# (nombre de la familia, lista de IDs de socios que la componen)
FAMILIAS: list[tuple[str, list[int]]] = [
    ("Alvaro y Maritza", [1, 2]),
    ("Nathalia", [3, 4, 5]),
    ("Karoll", [6, 7, 8]),
    ("Mabel", [13, 14]),
    ("Magally", [17, 15, 16, 18]),
    ("Efraín", [21, 22]),
    ("Ayda", [25, 26, 27]),
    ("Harvey", [35, 36, 37, 38, 39]),
    ("Magceider", [46, 47, 48, 49]),
    ("Noe", [52, 54]),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed de familias → Postgres")
    parser.add_argument("--postgres", required=True, help="Connection string de Postgres")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borra las familias existentes antes de sembrar (usar solo en el bootstrap).",
    )
    args = parser.parse_args()

    try:
        import psycopg
    except ImportError:
        sys.exit("Error: psycopg no instalado. Corre: uv sync --all-packages")

    todos_ids = [sid for _, ids in FAMILIAS for sid in ids]
    if len(todos_ids) != len(set(todos_ids)):
        sys.exit("[ABORT] Hay un socio repetido en dos familias. Revisa el mapeo.")

    with psycopg.connect(args.postgres) as pg:
        if args.reset:
            print("[seed] Reset: limpiando familia_id y tabla familias...")
            pg.execute("UPDATE socios SET familia_id = NULL")
            pg.execute("DELETE FROM familias")

        ya = pg.execute("SELECT COUNT(*) FROM familias").fetchone()[0]
        if ya > 0 and not args.reset:
            sys.exit(
                f"[ABORT] Ya hay {ya} familias. Usa --reset para rehacer el bootstrap, "
                "o edítalas desde la app."
            )

        print(f"[seed] Sembrando {len(FAMILIAS)} familias...")
        for nombre, ids in FAMILIAS:
            row = pg.execute(
                "INSERT INTO familias (nombre) VALUES (%s) RETURNING id", (nombre,)
            ).fetchone()
            familia_id = int(row[0])
            with pg.cursor() as cur:
                cur.executemany(
                    "UPDATE socios SET familia_id = %s WHERE id = %s",
                    [(familia_id, sid) for sid in ids],
                )
            print(f"[seed]   {nombre}: socios {ids} -> familia {familia_id}")

        asignados = pg.execute(
            "SELECT COUNT(*) FROM socios WHERE familia_id IS NOT NULL"
        ).fetchone()[0]
        pg.commit()

    print(f"\n[OK] Familias sembradas. Socios con familia: {asignados}.")
    print("     Los socios sin familia quedan libres para asignarse desde la app.")


if __name__ == "__main__":
    main()
