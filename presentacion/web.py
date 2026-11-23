from datetime import date, timedelta
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from dominio.agenda import (
    APERTURA, CIERRE, AlmacenOcupado, CruceHorario, EdicionAnterior, EntradaInvalida,
    ErrorAgenda, NoEncontrado, ServicioAgenda,
)


DIRECTORIO = Path(__file__).resolve().parent
CAMPOS = ("kit", "fecha", "inicio", "fin", "actividad", "responsable", "aula", "version")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")
AVISOS = {
    "creada": "La reserva quedó registrada.",
    "actualizada": "Los cambios quedaron guardados.",
    "eliminada": "Reserva eliminada. El horario volvió a quedar disponible.",
}


def reloj(minutos: int) -> str:
    horas, resto = divmod(minutos, 60)
    return f"{horas:02d}:{resto:02d}"


def duracion(minutos: int) -> str:
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def fecha_larga(dia: date) -> str:
    return f"{DIAS[dia.weekday()].capitalize()}, {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def estado_error(error: ErrorAgenda) -> int:
    if isinstance(error, NoEncontrado):
        return 404
    if isinstance(error, (EdicionAnterior, CruceHorario)):
        return 409
    if isinstance(error, AlmacenOcupado):
        return 503
    return 400


def crear_web(servicio: ServicioAgenda, fecha_demo: date | None = None) -> FastAPI:
    app = FastAPI(title="TurnoLab", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/estaticos", StaticFiles(directory=DIRECTORIO / "estaticos"), name="estaticos")
    plantillas = Jinja2Templates(directory=DIRECTORIO / "plantillas")
    plantillas.env.filters.update(reloj=reloj, duracion=duracion, fecha_larga=fecha_larga)
    clave = token_urlsafe(32)
    plantillas.env.globals.update(token=clave, es_demo=bool(fecha_demo),
                                 apertura=APERTURA, cierre=CIERRE)

    def pagina(request, nombre, estado=200, **contexto):
        return plantillas.TemplateResponse(request=request, name=nombre,
                                          context=contexto, status_code=estado)

    def vuelta(fecha: date, aviso: str):
        return RedirectResponse("/?" + urlencode({"fecha": fecha.isoformat(), "aviso": aviso}), 303)

    def comprobar_token(formulario):
        recibido = str(formulario.get("token", "")).encode()
        if not compare_digest(recibido, clave.encode()):
            raise EntradaInvalida("Vuelve a abrir la página para enviar el formulario.")

    @app.exception_handler(ErrorAgenda)
    async def error_agenda(request: Request, error: ErrorAgenda):
        return pagina(request, "error.html", estado_error(error), error=str(error))

    @app.get("/")
    def agenda(request: Request, fecha: str = "", kit: str = "", aviso: str = ""):
        seleccion = fecha or (fecha_demo or date.today()).isoformat()
        dia = servicio.consultar(seleccion, kit)
        anterior = dia.fecha - timedelta(days=1) if dia.fecha > date.min else None
        siguiente = dia.fecha + timedelta(days=1) if dia.fecha < date.max else None
        equipos = {k.id: k for k in dia.kits}
        visibles = [k for k in dia.kits if not dia.kit_seleccionado or k.id == dia.kit_seleccionado]
        por_kit = {k.id: [] for k in visibles}
        for reserva in dia.reservas:
            por_kit[reserva.kit_id].append(reserva)
        return pagina(request, "agenda.html", dia=dia, equipos=equipos, visibles=visibles,
                      por_kit=por_kit, anterior=anterior, siguiente=siguiente, aviso=AVISOS.get(aviso))

    @app.get("/kits")
    def catalogo(request: Request):
        return pagina(request, "kits.html", kits=servicio.catalogo(),
                      fecha=(fecha_demo or date.today()).isoformat())

    def formulario(request, valores, reserva_id=None, error=None):
        alternativa = error.alternativa if isinstance(error, CruceHorario) else None
        return pagina(request, "formulario.html", estado_error(error) if error else 200,
                      valores=valores, kits=servicio.catalogo(), reserva_id=reserva_id,
                      error=str(error) if error else "", cruce=isinstance(error, CruceHorario),
                      alternativa=alternativa, desactualizada=isinstance(error, EdicionAnterior))

    @app.get("/reservas/nueva")
    def nueva(request: Request, fecha: str = "", kit: str = ""):
        dia = servicio.consultar(fecha or (fecha_demo or date.today()).isoformat(), kit)
        valores = dict.fromkeys(CAMPOS, "")
        valores.update(fecha=dia.fecha.isoformat(), inicio="09:00", fin="10:00", kit=kit or str(dia.kits[0].id))
        return formulario(request, valores)

    @app.get("/reservas/{reserva_id:int}/editar")
    def editar(request: Request, reserva_id: int):
        r = servicio.obtener(reserva_id)
        valores = dict(kit=str(r.kit_id), fecha=r.fecha.isoformat(), inicio=reloj(r.inicio),
                       fin=reloj(r.fin), actividad=r.actividad, responsable=r.responsable,
                       aula=r.aula, version=str(r.version))
        return formulario(request, valores, r.id)

    async def procesar(request: Request, reserva_id: int | None = None):
        async with request.form(max_files=0, max_fields=16) as campos:
            comprobar_token(campos)
            valores = {k: str(campos.get(k, "")) for k in CAMPOS}
            propuesta = str(campos.get("usar_franja", ""))
        if propuesta:
            partes = propuesta.split("/")
            if len(partes) != 2:
                raise EntradaInvalida("Vuelve a consultar la franja disponible.")
            valores.update(inicio=partes[0], fin=partes[1])
        try:
            guardada = await run_in_threadpool(servicio.guardar, **valores, reserva_id=reserva_id)
        except (EntradaInvalida, CruceHorario, EdicionAnterior) as error:
            return await run_in_threadpool(formulario, request, valores, reserva_id, error)
        return vuelta(guardada.fecha, "actualizada" if reserva_id else "creada")

    @app.post("/reservas")
    async def crear(request: Request):
        return await procesar(request)

    @app.post("/reservas/{reserva_id:int}/editar")
    async def modificar(request: Request, reserva_id: int):
        return await procesar(request, reserva_id)

    @app.get("/reservas/{reserva_id:int}/eliminar")
    def confirmar(request: Request, reserva_id: int):
        r = servicio.obtener(reserva_id)
        kit = next(k for k in servicio.catalogo() if k.id == r.kit_id)
        return pagina(request, "eliminar.html", reserva=r, kit=kit)

    @app.post("/reservas/{reserva_id:int}/eliminar")
    async def eliminar(request: Request, reserva_id: int):
        async with request.form(max_files=0, max_fields=4) as campos:
            comprobar_token(campos)
            version = str(campos.get("version", ""))
        r = await run_in_threadpool(servicio.eliminar, reserva_id, version)
        return vuelta(r.fecha, "eliminada")

    return app
