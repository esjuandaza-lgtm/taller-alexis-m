# TurnoLab

Agenda de préstamos de equipos para un laboratorio simulado de INFOTEP en San Juan del Cesar. Proyecto final de Laboratorio de Programación por Capas y Componentes (LPPC-1525).

Un proyector puede terminar una clase a las 10:00 y seguir ocupado mientras soporte revisa sus cables. TurnoLab calcula a qué hora puede entregarse de nuevo. Si dos grupos piden el mismo kit, propone la primera franja del día que conserva la duración de la clase y el tiempo de revisión.

## Instalación y primera ejecución

Necesitas Python 3.11 o posterior y un navegador. La primera instalación descarga las dependencias. Después puedes ejecutar la demostración sin conexión. Si descargaste el ZIP, extráelo y abre una terminal en la carpeta `TurnoLab`, donde se encuentra `app.py`.

**Windows (PowerShell o símbolo del sistema)**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py --demo
```

**macOS o Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py --demo
```

Con la terminal abierta, visita [la agenda local](http://127.0.0.1:8000). Para detener el programa, presiona `Ctrl+C`. Si el puerto 8000 está ocupado, añade `--puerto 8001` al comando de arranque y abre `http://127.0.0.1:8001`.

| Modo | Primera pantalla | Archivo de datos |
| --- | --- | --- |
| `app.py --demo` | Agenda del 24 de noviembre de 2026 con tres clases de ejemplo | `instancia/demo.sqlite3` |
| `app.py` | Agenda del día con el catálogo de kits, lista para la primera reserva | `instancia/turnolab.sqlite3` |

Cada modo conserva sus cambios al cerrar el programa. Los ejemplos de práctica se cargan una sola vez, durante la creación de su base.

## Demostración en vivo

El ensayo dura unos cinco minutos. Abre el archivo [Sustentacion_TurnoLab.pdf](docs/Sustentacion_TurnoLab.pdf) para proyectar las doce diapositivas. Mantén la agenda abierta en otra ventana.

| Paso | Acción en la aplicación | Resultado que verá el grupo |
| --- | --- | --- |
| 1 | Inicia el modo de práctica. Busca la clase de multimedia. | El proyector está en clase de 09:00 a 10:00 y en revisión hasta las 10:20. |
| 2 | Pulsa **Nueva reserva**. Para el **Kit de proyección**, usa el 24/11/2026 de 10:05 a 11:05. Escribe **Edición de video**, **Grupo de práctica** y **Aula 3**. Pulsa **Crear reserva**. | La aplicación explica el cruce y conserva los datos del formulario. Propone la primera hora completa disponible, de 10:20 a 11:20. |
| 3 | Pulsa **Guardar de 10:20 a 11:20**. | La nueva clase aparece en la agenda. El proyector vuelve a quedar libre a las 11:40. |
| 4 | Pulsa **Editar** en la fila de Edición de video. Cambia el aula a **Aula 5** y guarda. | La misma reserva muestra el nuevo espacio. |
| 5 | Detén el servidor con `Ctrl+C`, vuelve a ejecutar el comando con `--demo` y recarga la página. | La clase de 10:20 sigue en Aula 5. Así se demuestra la persistencia en disco. |
| 6 | Abre esa reserva, pulsa **Eliminar reserva** y **Confirmar eliminación**. | Desaparece la clase creada durante el ensayo y el turno vuelve a estar disponible. Las tres reservas iniciales permiten repetir la demostración. |

## Reglas que conviene explicar

- El proyector requiere 20 minutos de revisión, el kit de redes 15 y el de audio 10. Son valores definidos para este caso académico.
- La ocupación de un kit comienza al iniciar la clase y termina al finalizar su revisión. Un préstamo puede empezar en el minuto exacto en que termina la revisión anterior.
- La clase y la revisión deben caber entre las 07:00 y las 18:00 del día seleccionado. Pueden coincidir dos clases que utilicen equipos distintos.
- Ante un cruce, el servicio busca a partir de la hora pedida, en la misma fecha y para el mismo kit. Comprueba que toda la franja cabe, incluso si hay otra clase más adelante. La persona decide si acepta.
- Si dos solicitudes llegan al mismo tiempo, la comprobación y la escritura ocurren en una sola transacción. Si dos personas editan la misma reserva, el número de versión permite detectar un formulario desactualizado.

## Arquitectura y datos

| Componente | Archivo de entrada | Responsabilidad |
| --- | --- | --- |
| Presentación | `presentacion/web.py` | FastAPI recibe peticiones. Jinja2 produce la agenda y los formularios. Esta capa llama al servicio de dominio. |
| Dominio | `dominio/agenda.py` | Valida fechas, campos y horarios. Calcula la liberación y encuentra la primera franja disponible. |
| Contrato del repositorio | `dominio/repositorio.py` | Define las operaciones sobre entidades `Kit` y `Reserva` que necesita el servicio. |
| Acceso a datos | `datos/sqlite.py` | Implementa el repositorio con SQLite, traduce filas a entidades y ejecuta las escrituras en una transacción. |
| Arranque | `app.py` | Conecta las capas y elige la base normal o la de práctica. |

**Por qué FastAPI y Jinja2.** El proyecto necesita formularios y una agenda que funcione en el navegador del aula. FastAPI enruta las peticiones y Jinja2 reutiliza la plantilla de navegación. El HTML y el CSS se sirven con la aplicación.

**Modelo relacional.** Un kit físico admite muchas reservas a lo largo del tiempo. `kits.id` y `reservas.id` son llaves primarias. `reservas.kit_id` es una llave foránea que referencia `kits.id`. El repositorio usa marcadores `?` al enviar los datos de las operaciones SQL.

| Tabla | Campos principales | Uso |
| --- | --- | --- |
| `kits` | `id`, `nombre`, `contenido`, `revision_min` | Catálogo inicial de tres equipos y sus tiempos de revisión. |
| `reservas` | `id`, `kit_id`, `fecha`, `inicio`, `fin`, `libre`, `actividad`, `responsable`, `aula`, `version` | Registro de cada clase. Las tres horas se guardan como minutos desde medianoche. |

Para seguir una operación en el código, abre `procesar` en `presentacion/web.py`, `ServicioAgenda.guardar` en `dominio/agenda.py` e `insertar` en `datos/sqlite.py`. Para la actualización y la eliminación, revisa los métodos `actualizar` y `eliminar` del repositorio.

## Pruebas

Desde la carpeta del proyecto, ejecuta las pruebas con Python.

```sh
python -m unittest discover -s pruebas -v
```

En Windows también puedes usar `py -3` y en macOS o Linux, `python3`. Las nueve pruebas crean bases temporales. Comprueban el límite exacto de entrega, las revisiones que se cruzan, las sugerencias con varias reservas, el cierre, el filtro por fecha y equipo, la validación, la persistencia, la edición y las solicitudes simultáneas.

## GitHub y participación del grupo

Para trabajar con el historial, clona la rama de la entrega.

```sh
git clone --branch turnolab-propuesta https://github.com/esjuandaza-lgtm/taller-alexis-m.git
cd taller-alexis-m
git log --oneline
```

La base del proyecto se preparó con asistencia de Codex. Cada integrante debe hacer cambios propios, registrarlos con su cuenta y poder explicarlos. Para la inspección del docente, abran el historial de la rama del grupo, seleccionen un commit de cada integrante y muestren qué líneas cambió y cómo comprobaron su efecto.

Si van a trabajar sin conexión, el ZIP incluye el archivo `historial-turnolab.bundle` junto a la carpeta del código. Desde el directorio donde se encuentra ese archivo, `git clone -b main historial-turnolab.bundle TurnoLab-local` recupera el historial de construcción de la base.

## Preparación para la sustentación

La guía fija revisiones de avance el 3, 10 y 17 de noviembre y la sustentación el 24 de noviembre. Para las evidencias de avance, el grupo debe usar las versiones y los aportes que realmente presentó en cada encuentro.

Como el docente puede elegir a dos integrantes, conviene que todos puedan hacer ambas partes. Una persona puede explicar el préstamo de las 10:05, provocar el cruce y aceptar la propuesta. La otra puede seguir esa reserva por las tres capas, reiniciar el programa, comprobar el cambio de aula y mostrar el historial de GitHub.

## Referencias técnicas

- [FastAPI y las plantillas HTML](https://fastapi.tiangolo.com/advanced/templates/)
- [Jinja y la herencia de plantillas](https://jinja.palletsprojects.com/en/stable/intro/)
- [SQLite desde Python y parámetros en las consultas](https://docs.python.org/es/3/library/sqlite3.html)
- [Transacciones de SQLite](https://www.sqlite.org/lang_transaction.html)
