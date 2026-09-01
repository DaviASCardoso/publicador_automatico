"""Estado mínimo: quais horários de publicação já foram atendidos hoje.

Existe só para não publicar duas vezes no mesmo horário mesmo que o tick de 1
minuto encontre esse horário mais de uma vez (por exemplo, se a primeira
tentativa falhou e o horário atual segue igual ou maior que o configurado).
O estado de dias anteriores é descartado assim que a data muda.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def _carregar(state_path: Path, hoje: date) -> dict:
    try:
        dados = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"data": hoje.isoformat(), "horarios_publicados": []}
    if dados.get("data") != hoje.isoformat():
        return {"data": hoje.isoformat(), "horarios_publicados": []}
    return dados


def ja_publicou_neste_horario(state_path: Path, hoje: date, horario: str) -> bool:
    dados = _carregar(state_path, hoje)
    return horario in dados.get("horarios_publicados", [])


def marcar_publicado(state_path: Path, hoje: date, horario: str) -> None:
    dados = _carregar(state_path, hoje)
    horarios = dados.setdefault("horarios_publicados", [])
    if horario not in horarios:
        horarios.append(horario)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(dados), encoding="utf-8")
