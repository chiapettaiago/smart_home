#!/usr/bin/env python3
"""Atualiza AUTH_PASSWORD_HASH no .env sem expor a senha no terminal."""

import getpass
import re
from pathlib import Path

from werkzeug.security import generate_password_hash

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
MIN_PASSWORD_LENGTH = 14


def main() -> None:
    if not ENV_PATH.is_file():
        raise SystemExit(f"Arquivo não encontrado: {ENV_PATH}")
    if not ENV_PATH.stat().st_mode & 0o400:
        raise SystemExit(f"Sem permissão de leitura em {ENV_PATH}. Corrija o proprietário do arquivo.")
    try:
        content = ENV_PATH.read_text(encoding="utf-8")
    except PermissionError:
        raise SystemExit(
            f"Sem acesso a {ENV_PATH}. Execute: sudo chown $(id -u):$(id -g) .env smart_home.db"
        ) from None

    password = getpass.getpass("Nova senha: ")
    confirmation = getpass.getpass("Confirme a nova senha: ")
    if password != confirmation:
        raise SystemExit("As senhas não conferem.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Use uma senha com pelo menos {MIN_PASSWORD_LENGTH} caracteres.")

    hash_line = f"AUTH_PASSWORD_HASH={generate_password_hash(password)}"
    if re.search(r"^AUTH_PASSWORD_HASH=.*$", content, flags=re.MULTILINE):
        content = re.sub(r"^AUTH_PASSWORD_HASH=.*$", hash_line, content, flags=re.MULTILINE)
    else:
        content = f"{content.rstrip()}\n{hash_line}\n"
    content = re.sub(r"^AUTH_PASSWORD=.*\n?", "", content, flags=re.MULTILINE)
    try:
        ENV_PATH.write_text(content, encoding="utf-8")
    except PermissionError:
        raise SystemExit(
            f"Sem acesso de escrita a {ENV_PATH}. Execute: sudo chown $(id -u):$(id -g) .env smart_home.db"
        ) from None
    print("Senha atualizada. Reinicie o servidor para aplicar a alteração.")


if __name__ == "__main__":
    main()
