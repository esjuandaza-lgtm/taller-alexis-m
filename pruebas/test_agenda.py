import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from datos.sqlite import BaseSQLite
from dominio.agenda import CruceHorario, EdicionAnterior, EntradaInvalida, NoEncontrado, ServicioAgenda


class PruebasAgenda(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.TemporaryDirectory()
        self.addCleanup(self.directorio.cleanup)
        self.ruta = Path(self.directorio.name) / "prueba.sqlite3"
        self.base = BaseSQLite(self.ruta)
        self.base.inicializar()
        self.agenda = ServicioAgenda(self.base.abrir)
        self.datos = dict(kit="1", fecha="2026-11-24", inicio="09:00", fin="10:00",
                          actividad="Taller de multimedia", responsable="Equipo O'Neill", aula="Aula 2")

    def guardar(self, **cambios):
        return self.agenda.guardar(**(self.datos | cambios))

    def test_revision_limita_el_siguiente_prestamo(self):
        primera = self.guardar()
        self.assertEqual(primera.libre, 10 * 60 + 20)
        with self.assertRaises(CruceHorario) as caso:
            self.guardar(inicio="10:05", fin="11:05")
        self.assertEqual(caso.exception.alternativa, (620, 680))
        segunda = self.guardar(inicio="10:20", fin="11:20")
        self.assertEqual(segunda.libre, 700)

    def test_la_revision_nueva_tambien_puede_chocar(self):
        self.guardar(inicio="10:00", fin="11:00")
        with self.assertRaises(CruceHorario) as caso:
            self.guardar(inicio="09:00", fin="09:50")
        self.assertEqual(caso.exception.alternativa, (680, 730))

    def test_sugerencia_salta_huecos_insuficientes(self):
        self.guardar()
        self.guardar(inicio="10:45", fin="11:30")
        with self.assertRaises(CruceHorario) as caso:
            self.guardar(inicio="10:05", fin="11:05")
        self.assertEqual(caso.exception.alternativa, (710, 770))

    def test_frontera_de_cierre_y_dia_lleno(self):
        self.guardar(inicio="07:00", fin="17:40")
        with self.assertRaises(CruceHorario) as caso:
            self.guardar(inicio="16:00", fin="17:00")
        self.assertIsNone(caso.exception.alternativa)
        with self.assertRaises(EntradaInvalida):
            self.guardar(inicio="16:00", fin="17:41")

    def test_otro_kit_u_otra_fecha_permiten_la_misma_hora(self):
        self.guardar()
        self.guardar(kit="3")
        self.guardar(fecha="2026-11-25")
        resumen = self.agenda.consultar("2026-11-24")
        self.assertEqual((len(resumen.reservas), resumen.minutos_clase, resumen.minutos_revision),
                         (2, 120, 30))
        self.assertEqual(len(self.agenda.consultar("2026-11-24", "3").reservas), 1)

    def test_valida_entradas_antes_de_escribir(self):
        for campo, valor in [("fecha", "2026-02-30"), ("inicio", "08:70"), ("fin", "08:55"),
                             ("inicio", "06:55"), ("kit", "95"), ("actividad", " "), ("aula", "x"),
                             ("responsable", "a" * 61)]:
            with self.subTest(campo=campo, valor=valor), self.assertRaises(EntradaInvalida):
                self.guardar(**{campo: valor})
        self.assertEqual(self.agenda.consultar("2026-11-24").reservas, [])

    def test_edicion_eliminacion_y_persistencia(self):
        r = self.guardar()
        editada = self.guardar(reserva_id=r.id, version="1", aula="Aula 5")
        otra_instancia = ServicioAgenda(BaseSQLite(self.ruta).abrir)
        self.assertEqual((otra_instancia.obtener(r.id).aula, editada.version), ("Aula 5", 2))
        self.assertEqual(otra_instancia.obtener(r.id).responsable, "Equipo O'Neill")
        with self.assertRaises(EdicionAnterior):
            self.guardar(reserva_id=r.id, version="1", aula="Aula 8")
        with self.assertRaises(EdicionAnterior):
            otra_instancia.eliminar(r.id, "1")
        otra_instancia.eliminar(r.id, "2")
        with self.assertRaises(NoEncontrado):
            self.agenda.obtener(r.id)
        self.assertNotEqual(self.guardar().id, r.id)

    def test_editar_con_cruce_conserva_la_reserva_original(self):
        original = self.guardar()
        self.guardar(inicio="11:00", fin="12:00")
        with self.assertRaises(CruceHorario):
            self.guardar(reserva_id=original.id, version="1", inicio="10:45", fin="11:30")
        self.assertEqual(self.agenda.obtener(original.id), original)

    def test_dos_solicitudes_simultaneas_solo_guardan_una(self):
        barrera = Barrier(2)

        def solicitar():
            barrera.wait(timeout=5)
            try:
                self.guardar()
                return "guardada"
            except CruceHorario:
                return "cruce"

        with ThreadPoolExecutor(max_workers=2) as grupo:
            tareas = [grupo.submit(solicitar) for _ in range(2)]
            self.assertCountEqual([t.result(timeout=8) for t in tareas], ["guardada", "cruce"])
        self.assertEqual(len(self.agenda.consultar("2026-11-24").reservas), 1)


if __name__ == "__main__":
    unittest.main()
