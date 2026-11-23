"""Arranque local y conexión entre las tres capas de TurnoLab."""
import argparse
from contextlib import nullcontext
from datetime import date
from pathlib import Path

import uvicorn

from datos.sqlite import BaseSQLite
from dominio.agenda import ServicioAgenda
from dominio.repositorio import Repositorio
from presentacion.web import crear_web


DIRECTORIO = Path(__file__).resolve().parent / "instancia"
DIA_DEMO = date(2026, 11, 24)


def cargar_ejemplo(repo: Repositorio) -> None:
    # Se usan las mismas reglas que al reservar desde el navegador.
    servicio = ServicioAgenda(lambda escritura: nullcontext(repo))
    ejemplos = [
        ("1", "09:00", "10:00", "Clase de multimedia", "Equipo de audiovisuales", "Aula 2"),
        ("2", "10:00", "11:15", "Práctica de cableado", "Grupo de redes", "Laboratorio 1"),
        ("3", "14:00", "15:00", "Taller de grabación", "Grupo de sonido", "Aula 4"),
    ]
    for kit, inicio, fin, actividad, responsable, aula in ejemplos:
        servicio.guardar(kit=kit, fecha=DIA_DEMO.isoformat(), inicio=inicio, fin=fin,
                         actividad=actividad, responsable=responsable, aula=aula)


def crear_aplicacion(*, demo: bool = False, ruta: Path | None = None):
    base = BaseSQLite(ruta or DIRECTORIO / ("demo.sqlite3" if demo else "turnolab.sqlite3"))
    base.inicializar(cargar_ejemplo if demo else None)
    return crear_web(ServicioAgenda(base.abrir), DIA_DEMO if demo else None)


if __name__ == "__main__":
    argumentos = argparse.ArgumentParser(description="Agenda local de kits de laboratorio")
    argumentos.add_argument("--demo", action="store_true", help="Usar la base de práctica del 24 de noviembre")
    argumentos.add_argument("--puerto", type=int, default=8000, help="Puerto local (por defecto 8000)")
    opciones = argumentos.parse_args()
    uvicorn.run(crear_aplicacion(demo=opciones.demo), host="127.0.0.1", port=opciones.puerto)
