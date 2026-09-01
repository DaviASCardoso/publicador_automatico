"""Seleção do próximo vídeo a publicar e checagem de cópia completa pela rede."""

from __future__ import annotations

import time
from pathlib import Path

_INTERVALO_ESTABILIDADE_SEGUNDOS = 5


def _e_temporario(nome: str) -> bool:
    return nome.startswith(".") or nome.startswith("~")


def proximo_video(pasta: Path) -> Path | None:
    """Retorna o vídeo .mp4 mais antigo (por mtime) em `pasta`, ou None."""
    if not pasta.exists():
        return None
    candidatos = sorted(
        (p for p in pasta.glob("*.mp4") if p.is_file() and not _e_temporario(p.name)),
        key=lambda p: p.stat().st_mtime,
    )
    return candidatos[0] if candidatos else None


def arquivo_esta_estavel(path: Path) -> bool:
    """Compara o tamanho do arquivo com 5s de intervalo para detectar cópia
    em andamento."""
    try:
        tamanho_inicial = path.stat().st_size
    except OSError:
        return False

    time.sleep(_INTERVALO_ESTABILIDADE_SEGUNDOS)

    try:
        tamanho_final = path.stat().st_size
    except OSError:
        return False

    return tamanho_inicial == tamanho_final
