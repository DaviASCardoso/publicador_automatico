"""Estado mínimo: qual foi o último dia em que o daemon publicou algo.

Existe só para não publicar duas vezes no mesmo dia mesmo que o tick de 1 minuto
encontre o horário configurado mais de uma vez (por exemplo, se a primeira
tentativa falhou e o horário atual segue igual ou maior que o configurado).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def ja_publicou_hoje(state_path: Path, hoje: date) -> bool:
    try:
        dados = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return dados.get("ultima_publicacao") == hoje.isoformat()


def marcar_publicado_hoje(state_path: Path, hoje: date) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"ultima_publicacao": hoje.isoformat()}), encoding="utf-8"
    )
