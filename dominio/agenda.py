from datetime import date
import re

from .modelos import AgendaDia, Kit, Reserva
from .repositorio import AbrirRepositorio, Repositorio


APERTURA = 7 * 60
CIERRE = 18 * 60


class ErrorAgenda(Exception):
    """El servicio rechazó la operación."""


class EntradaInvalida(ErrorAgenda):
    pass


class NoEncontrado(ErrorAgenda):
    pass


class EdicionAnterior(ErrorAgenda):
    pass


class AlmacenOcupado(ErrorAgenda):
    pass


class CruceHorario(ErrorAgenda):
    def __init__(self, alternativa: tuple[int, int] | None):
        super().__init__("Este kit ya está reservado o en revisión durante ese horario.")
        self.alternativa = alternativa


def fecha_valida(valor: str) -> date:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise EntradaInvalida("Selecciona una fecha válida.")


def minutos(valor: str) -> int:
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", valor):
        raise EntradaInvalida("Escribe las horas en formato de 24 horas, por ejemplo 09:30.")
    hora, minuto = map(int, valor.split(":"))
    return 60 * hora + minuto


def identificador(valor: str | int, mensaje: str) -> int:
    texto = str(valor)
    if re.fullmatch(r"[1-9][0-9]{0,18}", texto):
        numero = int(texto)
        if numero <= 2**63 - 1:
            return numero
    raise EntradaInvalida(mensaje)


def texto_requerido(valor: str, campo: str, limite: int) -> str:
    texto = " ".join(valor.split())
    if not 2 <= len(texto) <= limite:
        raise EntradaInvalida(f"El campo «{campo}» debe tener entre 2 y {limite} caracteres.")
    return texto


def primer_inicio_disponible(inicio: int, duracion_total: int, ocupadas: list[Reserva]) -> int | None:
    """Busca en el mismo día el primer hueco suficiente, desde la hora solicitada."""
    candidato = inicio
    for reserva in sorted(ocupadas, key=lambda r: r.inicio):
        if candidato + duracion_total <= reserva.inicio:
            break
        candidato = max(candidato, reserva.libre)
    return candidato if candidato + duracion_total <= CIERRE else None


def reserva_existente(repo: Repositorio, reserva_id: int) -> Reserva:
    reserva = repo.reserva(identificador(reserva_id, "El número de reserva es inválido."))
    if reserva is None:
        raise NoEncontrado("La reserva ya no está en la agenda.")
    return reserva


def comprobar_version(reserva: Reserva, version: str) -> None:
    if reserva.version != identificador(version, "Vuelve a abrir la reserva antes de modificarla."):
        raise EdicionAnterior("La reserva cambió desde que abriste el formulario. Vuelve a abrirla para ver la última versión.")


class ServicioAgenda:
    def __init__(self, abrir_repositorio: AbrirRepositorio):
        self._abrir = abrir_repositorio

    def catalogo(self) -> list[Kit]:
        with self._abrir(False) as repo:
            return repo.kits()

    def consultar(self, fecha: str, kit: str = "") -> AgendaDia:
        dia = fecha_valida(fecha)
        kit_id = identificador(kit, "Selecciona un kit del catálogo.") if kit else None
        with self._abrir(False) as repo:
            if kit_id is not None and repo.kit(kit_id) is None:
                raise NoEncontrado("El kit seleccionado no está en el catálogo.")
            return AgendaDia(dia, repo.kits(), kit_id, repo.reservas(dia, kit_id))

    def obtener(self, reserva_id: int) -> Reserva:
        with self._abrir(False) as repo:
            return reserva_existente(repo, reserva_id)

    def guardar(self, *, kit: str, fecha: str, inicio: str, fin: str, actividad: str,
                responsable: str, aula: str, reserva_id: int | None = None, version: str = "") -> Reserva:
        dia = fecha_valida(fecha)
        desde, hasta = minutos(inicio), minutos(fin)
        kit_id = identificador(kit, "Selecciona un kit del catálogo.")
        actividad = texto_requerido(actividad, "Actividad", 80)
        responsable = texto_requerido(responsable, "Responsable", 60)
        aula = texto_requerido(aula, "Aula o espacio", 40)
        if hasta <= desde:
            raise EntradaInvalida("La clase debe terminar después de la hora de inicio.")
        if desde < APERTURA or hasta > CIERRE:
            raise EntradaInvalida("El horario del laboratorio es de 07:00 a 18:00.")

        with self._abrir(True) as repo:
            anterior = None
            if reserva_id is not None:
                anterior = reserva_existente(repo, reserva_id)
                comprobar_version(anterior, version)
            equipo = repo.kit(kit_id)
            if equipo is None:
                raise EntradaInvalida("Selecciona un kit del catálogo.")
            libre = hasta + equipo.revision_min
            if libre > CIERRE:
                raise EntradaInvalida(f"Los {equipo.revision_min} minutos de revisión deben terminar a más tardar a las 18:00.")

            otras = [r for r in repo.reservas(dia, kit_id) if r.id != reserva_id]
            candidato = primer_inicio_disponible(desde, libre - desde, otras)
            if candidato != desde:
                alternativa = (candidato, candidato + hasta - desde) if candidato is not None else None
                raise CruceHorario(alternativa)

            nueva = Reserva(reserva_id, kit_id, dia, desde, hasta, libre, actividad, responsable,
                            aula, anterior.version + 1 if anterior else 1)
            if anterior is None:
                return repo.insertar(nueva)
            repo.actualizar(nueva)
            return nueva

    def eliminar(self, reserva_id: int, version: str) -> Reserva:
        with self._abrir(True) as repo:
            reserva = reserva_existente(repo, reserva_id)
            comprobar_version(reserva, version)
            repo.eliminar(reserva_id)
            return reserva
