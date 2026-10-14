from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OrgAssignmentRead(BaseModel):
    """El cargo vigente de una persona."""

    user_id: int
    name: str
    position: str
    position_label: str
    superior_user_id: Optional[int] = None
    superior_name: Optional[str] = None
    version: int


class OrgPositionOption(BaseModel):
    code: str
    label: str
    level: int


class OrgSuperiorOption(BaseModel):
    user_id: int
    name: str
    position: str
    level: int


class OrgOptions(BaseModel):
    """Lo que **este actor** puede asignar a **esta persona** (o a una nueva).

    Es experiencia: el servidor vuelve a validar todo al guardar.
    """

    positions: list[OrgPositionOption]
    #: Candidatos a superior con su nivel; la pantalla ofrece los de nivel mayor
    #: que el cargo elegido.
    superiors: list[OrgSuperiorOption]
    #: `True` para un manager: la persona tiene que quedar bajo él o su rama.
    superior_required: bool = False
    #: V1.3: el cargo de cada rol (por código de rol) y de qué cargos puede
    #: depender cada cargo. La pantalla filtra con esto; el servidor revalida.
    role_positions: dict[str, str] = {}
    allowed_parents: dict[str, list[str]] = {}
    current: Optional[OrgAssignmentRead] = None


class OrgAssignmentWrite(BaseModel):
    position: str
    superior_user_id: Optional[int] = None
    #: La versión vista de la asignación vigente (0 si no tenía). Con ella, un
    #: cambio concurrente responde 409 en vez de pisarse.
    version: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")
