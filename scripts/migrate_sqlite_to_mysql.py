#!/usr/bin/env python3
"""Copia os dados legados do SQLite para um banco MySQL vazio."""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, delete, func, inspect, insert, select, text
from sqlalchemy.exc import OperationalError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "smart_home.db"
TABLE_ORDER = (
    "rooms",
    "devices",
    "automations",
    "presence",
    "energy_readings",
    "automation_logs",
    "action_logs",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=f"sqlite:///{DEFAULT_SQLITE_PATH}", help="URL SQLAlchemy do SQLite de origem.")
    parser.add_argument("--target", default=os.getenv("MYSQL_DATABASE_URL", ""), help="URL SQLAlchemy MySQL de destino.")
    parser.add_argument("--replace", action="store_true", help="Apaga dados existentes no destino antes de copiar.")
    return parser.parse_args()


def fail(message):
    raise SystemExit(message)


def count_rows(connection, table):
    return connection.scalar(select(func.count()).select_from(table))


def main():
    args = parse_args()
    if not args.target.startswith("mysql+pymysql://"):
        fail("Informe --target mysql+pymysql://usuario:senha@host:3306/banco?charset=utf8mb4")
    if args.source.startswith("sqlite:///"):
        source_path = Path(args.source.removeprefix("sqlite:///"))
        if not source_path.is_file():
            fail(f"SQLite não encontrado: {source_path}")
        if not os.access(source_path, os.R_OK):
            fail(f"Sem acesso de leitura ao SQLite: {source_path}")

    os.environ["DATABASE_URL"] = args.target
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from app.database import Base
        import app.models  # noqa: F401
    except PermissionError:
        fail("Sem acesso ao .env. Corrija o proprietário antes da migração.")

    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target, pool_pre_ping=True)
    try:
        with target_engine.begin() as target:
            target.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=target_engine)
    except OperationalError as exc:
        fail(f"Não foi possível conectar ao MySQL: {exc.orig}")

    tables = Base.metadata.tables
    with source_engine.connect() as source, target_engine.begin() as target:
        source_table_names = set(inspect(source_engine).get_table_names())
        if args.replace:
            target.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for name in reversed(TABLE_ORDER):
                target.execute(delete(tables[name]))
            target.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        else:
            populated = [name for name in TABLE_ORDER if count_rows(target, tables[name])]
            if populated:
                fail(f"Destino não está vazio ({', '.join(populated)}). Use --replace somente após revisar o destino.")

        for name in TABLE_ORDER:
            table = tables[name]
            rows = [dict(row) for row in source.execute(select(table)).mappings()] if name in source_table_names else []
            if rows:
                target.execute(insert(table), rows)
            print(f"{name}: {len(rows)} registro(s) copiado(s)")

    with source_engine.connect() as source, target_engine.connect() as target:
        for name in TABLE_ORDER:
            source_count = count_rows(source, tables[name]) if name in source_table_names else 0
            target_count = count_rows(target, tables[name])
            if source_count != target_count:
                fail(f"Validação falhou em {name}: SQLite={source_count}, MySQL={target_count}")
    print("Migração concluída e validada.")


if __name__ == "__main__":
    main()
