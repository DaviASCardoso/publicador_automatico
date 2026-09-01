"""Ledger permanente (JSONL) de tudo que já foi publicado, para deduplicação.

O hash é calculado sobre o primeiro e o último MiB do arquivo (não o arquivo
inteiro) porque o CPU do notebook é fraco e o Opus Clip pode gerar o mesmo
corte em execuções diferentes — não queremos gastar CPU nem republicar.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from publicador.providers.base import PublishResult

logger = logging.getLogger(__name__)

_TZ_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_MIB = 1024 * 1024


def calcular_hash(path: Path) -> str:
    tamanho = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as f:
        if tamanho <= 2 * _MIB:
            digest.update(f.read())
        else:
            digest.update(f.read(_MIB))
            f.seek(tamanho - _MIB)
            digest.update(f.read(_MIB))
    return digest.hexdigest()


def buscar_publicacao(ledger_path: Path, hash_arquivo: str) -> dict | None:
    if not ledger_path.exists():
        return None
    with ledger_path.open("r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                entrada = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if entrada.get("hash") == hash_arquivo:
                return entrada
    return None


def ja_publicado_com_sucesso(entrada: dict | None, plataformas: list[str]) -> bool:
    """Já publicado com sucesso em TODAS as plataformas atualmente ativas.

    Só considera `plataformas` (a lista atual de plataformas_ativas), não as
    chaves que porventura existam na entrada do ledger — assim, ativar uma
    plataforma nova depois não é confundido com "já publicado".
    """
    if entrada is None:
        return False
    return all(entrada.get(p, {}).get("status") == "sucesso" for p in plataformas)


def registrar(
    ledger_path: Path,
    arquivo: str,
    hash_arquivo: str,
    resultados: dict[str, PublishResult],
) -> None:
    """Registra só as plataformas em `resultados` — ou seja, só as que
    realmente foram tentadas nesse ciclo (plataformas desativadas não
    entram)."""
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    plataformas_dump = {p: r.model_dump() for p, r in resultados.items()}
    entrada = {
        "arquivo": arquivo,
        "hash": hash_arquivo,
        "timestamp": datetime.now(_TZ_SAO_PAULO).isoformat(),
        **plataformas_dump,
    }
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    logger.info(
        "Registrado no ledger: %s (hash=%s, plataformas=%s)",
        arquivo,
        hash_arquivo,
        list(resultados),
    )
