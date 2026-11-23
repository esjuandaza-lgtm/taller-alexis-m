from collections.abc import Callable, Iterator
from contextlib import contextmanager, closing
from dataclasses import replace
from datetime import date
from pathlib import Path
import sqlite3

from dominio.agenda import AlmacenOcupado
from dominio.modelos import Kit, Reserva
from dominio.repositorio import Repositorio


TABLAS = (
    """CREATE TABLE IF NOT EXISTS kits (
        id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL UNIQUE,
        contenido TEXT NOT NULL,
        revision_min INTEGER NOT NULL CHECK (revision_min BETWEEN 0 AND 120)
    )""",
    """CREATE TABLE IF NOT EXISTS reservas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kit_id INTEGER NOT NULL REFERENCES kits(id) ON DELETE RESTRICT,
        fecha TEXT NOT NULL,
        inicio INTEGER NOT NULL,
        fin INTEGER NOT NULL,
        libre INTEGER NOT NULL,
        actividad TEXT NOT NULL CHECK (length(actividad) BETWEEN 2 AND 80),
        responsable TEXT NOT NULL CHECK (length(responsable) BETWEEN 2 AND 60),
        aula TEXT NOT NULL CHECK (length(aula) BETWEEN 2 AND 40),
        version INTEGER NOT NULL CHECK (version >= 1),
        CHECK (420 <= inicio AND inicio < fin AND fin <= libre AND libre <= 1080)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_reservas_dia_kit ON reservas(fecha, kit_id, inicio)",
)

KITS_INICIALES = (
    (1, "Kit de proyección", "Videoproyector, cable HDMI y adaptador USB-C.", 20),
    (2, "Kit de redes", "Conmutador, cables de práctica y probador de red.", 15),
    (3, "Kit de audio", "Parlante portátil, micrófono y cable auxiliar.", 10),
)


def entidad_reserva(fila: sqlite3.Row) -> Reserva:
    campos = dict(fila)
    campos["fecha"] = date.fromisoformat(campos["fecha"])
    return Reserva(**campos)


class RepositorioSQLite:
    def __init__(self, conexion: sqlite3.Connection):
        self.conexion = conexion

    def kits(self) -> list[Kit]:
        filas = self.conexion.execute("SELECT * FROM kits ORDER BY id")
        return [Kit(**dict(fila)) for fila in filas]

    def kit(self, kit_id: int) -> Kit | None:
        fila = self.conexion.execute("SELECT * FROM kits WHERE id = ?", (kit_id,)).fetchone()
        return Kit(**dict(fila)) if fila is not None else None

    def reservas(self, fecha: date, kit_id: int | None) -> list[Reserva]:
        consulta = "SELECT * FROM reservas WHERE fecha = ?"
        parametros = [fecha.isoformat()]
        if kit_id is not None:
            consulta += " AND kit_id = ?"
            parametros.append(kit_id)
        filas = self.conexion.execute(consulta + " ORDER BY inicio, kit_id, id", parametros)
        return [entidad_reserva(fila) for fila in filas]

    def reserva(self, reserva_id: int) -> Reserva | None:
        fila = self.conexion.execute("SELECT * FROM reservas WHERE id = ?", (reserva_id,)).fetchone()
        return entidad_reserva(fila) if fila is not None else None

    @staticmethod
    def valores(r: Reserva) -> tuple:
        return (r.kit_id, r.fecha.isoformat(), r.inicio, r.fin, r.libre,
                r.actividad, r.responsable, r.aula, r.version)

    def insertar(self, reserva: Reserva) -> Reserva:
        cursor = self.conexion.execute(
            """INSERT INTO reservas (kit_id, fecha, inicio, fin, libre, actividad, responsable, aula, version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", self.valores(reserva))
        return replace(reserva, id=cursor.lastrowid)

    def actualizar(self, reserva: Reserva) -> None:
        self.conexion.execute(
            """UPDATE reservas SET kit_id=?, fecha=?, inicio=?, fin=?, libre=?, actividad=?,
               responsable=?, aula=?, version=? WHERE id=?""",
            (*self.valores(reserva), reserva.id))

    def eliminar(self, reserva_id: int) -> None:
        self.conexion.execute("DELETE FROM reservas WHERE id = ?", (reserva_id,))


class BaseSQLite:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)

    @contextmanager
    def abrir(self, escritura: bool) -> Iterator[RepositorioSQLite]:
        with closing(sqlite3.connect(self.ruta, timeout=5, isolation_level=None)) as conexion:
            conexion.row_factory = sqlite3.Row
            conexion.execute("PRAGMA foreign_keys = ON")
            try:
                # La consulta de cruces y la escritura se protegen con el mismo bloqueo.
                conexion.execute("BEGIN IMMEDIATE" if escritura else "BEGIN")
                yield RepositorioSQLite(conexion)
                conexion.commit()
            except sqlite3.OperationalError as error:
                conexion.rollback()
                codigo = getattr(error, "sqlite_errorcode", 0) & 255
                if codigo in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise AlmacenOcupado("La agenda está atendiendo otro cambio. Intenta guardar de nuevo.") from error
                raise
            except Exception:
                conexion.rollback()
                raise

    def inicializar(self, al_crear: Callable[[Repositorio], None] | None = None) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.abrir(True) as repo:
            conexion = repo.conexion
            nueva = conexion.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'kits'"
            ).fetchone() is None
            for sentencia in TABLAS:
                conexion.execute(sentencia)
            if nueva:
                conexion.executemany(
                    "INSERT INTO kits (id, nombre, contenido, revision_min) VALUES (?, ?, ?, ?)",
                    KITS_INICIALES)
                if al_crear is not None:
                    al_crear(repo)
