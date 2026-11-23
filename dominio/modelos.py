from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Kit:
    id: int
    nombre: str
    contenido: str
    revision_min: int


@dataclass(frozen=True)
class Reserva:
    id: int | None
    kit_id: int
    fecha: date
    inicio: int
    fin: int
    libre: int
    actividad: str
    responsable: str
    aula: str
    version: int = 1


@dataclass(frozen=True)
class AgendaDia:
    fecha: date
    kits: list[Kit]
    kit_seleccionado: int | None
    reservas: list[Reserva]

    @property
    def minutos_clase(self) -> int:
        return sum(r.fin - r.inicio for r in self.reservas)

    @property
    def minutos_revision(self) -> int:
        return sum(r.libre - r.fin for r in self.reservas)
