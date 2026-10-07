"""La regla autoritativa de lectura del kilometraje. Una sola, para todos.

Por qué existe este módulo
---------------------------
El kilometraje oficial es **un hecho**: los metros enrutados que `TripMileage`
guarda por viaje. Pero hasta ahora cada superficie decidía por su cuenta dos
cosas sobre ese hecho:

* **qué suma** — sólo `calculated`, porque un pendiente no aporta cero;
* **cómo se convierte a millas** para enseñarlo.

Lo primero estaba escrito dos veces, una en `live/dao.py` y otra en
`activityexplorer/dao.py`. Lo segundo estaba escrito **tres** veces y, peor, con
dos fórmulas distintas:

    exacta       metros / 1609.344            <- `miles_from_meters`, 2 decimales
    aproximada   metros * 0.000621371         <- las dos pantallas, 1 decimal

`1/1609.344 = 0.000621371192237…`, así que la segunda es la primera truncada.
El error relativo es 3,1e-7 y suena despreciable hasta que se mide: a 57 695 m
—57,7 km, una jornada corriente de campo— la exacta publica **35,9** millas y la
aproximada **35,8**. El mismo viaje, dos cifras, según por qué pantalla se mire.

Por eso la conversión vive aquí y es una. Las pantallas siguen eligiendo con
cuántos decimales la enseñan, que es presentación; la conversión no lo es.

Lo que este módulo **no** hace
-------------------------------
No calcula kilometraje. Eso es del motor (`service.py`), ocurre una vez y se
persiste. Aquí sólo se **lee** lo ya calculado, y por eso no hay ninguna
distancia que derivar: ni odómetro, ni línea recta, ni acumulación de la traza.

El contrato que reutiliza Reports
----------------------------------
Lo que cualquier consumidor necesita del kilometraje es esto, y nada más:

    supervisor · periodo · work_session · trip
        -> official_miles        (millas de los viajes `calculated`)
        -> mileage_pending       (si queda algo sin resolver)

Reports consumirá estas mismas piezas cuando exista. No debe traer otra
fórmula: si aparece una tercera, vuelve el problema que este módulo cierra.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case

from app.routers_api.mileage.models import MileageState, TripMileage

#: Metros por milla. Exacto por definición internacional de la milla terrestre.
#: Se divide por él en vez de multiplicar por su inverso: el inverso no tiene
#: representación decimal finita, y truncarlo es justo el defecto que este
#: módulo corrige.
METROS_POR_MILLA = Decimal("1609.344")

#: Lo que enseñan las pantallas de administración, según la línea base aprobada.
UNA_DECIMA = Decimal("0.1")

#: Lo que devuelve la API de kilometraje, donde se mira un viaje concreto.
DOS_DECIMALES = Decimal("0.01")


def millas_oficiales(
    metros: Decimal | int | None, *, precision: Decimal = UNA_DECIMA
) -> Decimal:
    """Millas oficiales de una cantidad de metros ya calculada.

    `None` y cero son el mismo cero **presentable**: quien llama ya decidió que
    aquí no hay kilometraje pendiente que distinguir. Para esa distinción está
    `hay_pendiente()`, que es una pregunta distinta y se responde aparte —
    confundirlas es lo que convierte un pendiente en un cero final.
    """
    if metros is None:
        return Decimal("0").quantize(precision)
    return (Decimal(metros) / METROS_POR_MILLA).quantize(precision)


def metros_calculados():
    """Expresión SQL: los metros que ya están calculados, y sólo ésos.

    Un viaje `pending_calculation`, `not_calculable` o `calculation_failed`
    aporta 0 **a esta suma**, que no es lo mismo que decir que recorrió cero:
    que quede algo sin resolver se informa por separado con `pendientes()`.
    """
    return case(
        (TripMileage.state == MileageState.CALCULATED.value, TripMileage.total_meters),
        else_=0,
    )


def pendientes():
    """Expresión SQL: 1 por cada viaje cuyo kilometraje sigue sin resolverse.

    Sólo `pending_calculation`. Un estado terminal —`not_calculable` o
    `calculation_failed`— ya no está pendiente de nada: su respuesta es
    definitiva aunque no sea un número, y presentarla como «todavía calculando»
    sería prometer una cifra que no va a llegar. Ésos los cuenta
    `sin_resolver()`, que es una pregunta distinta.
    """
    return case(
        (TripMileage.state == MileageState.PENDING_CALCULATION.value, 1),
        else_=0,
    )


#: Terminales **sin** cifra. `calculated` no está porque sí la tiene.
TERMINALES_SIN_CIFRA = (
    MileageState.NOT_CALCULABLE.value,
    MileageState.CALCULATION_FAILED.value,
)


def sin_resolver():
    """Expresión SQL: 1 por cada viaje que terminó **sin** kilometraje.

    Por qué esto hace falta
    -----------------------
    Hasta ahora las pantallas publicaban dos datos: las millas y si quedaba algo
    pendiente. Con eso, tres realidades distintas se dibujaban idénticas:

        no hubo ningún viaje            -> 0.0 mi
        faltó evidencia de ubicación    -> 0.0 mi      <- `not_calculable`
        el routing agotó el reintento   -> 0.0 mi      <- `calculation_failed`

    Un supervisor que condujo 60 km y perdió el GPS se veía exactamente igual
    que uno que no salió de la oficina. El cero era veraz —esos viajes no tienen
    kilometraje y no se les va a inventar uno— pero **mudo**, y un cero mudo
    obliga a abrir una consola para saber qué pasó.

    Esto no cambia ninguna cifra. Añade la pregunta que faltaba: *¿el cero es
    porque no hubo recorrido, o porque no se pudo medir?*

    Lo que sigue estando prohibido
    ------------------------------
    Que estos viajes aporten una distancia estimada de donde sea. Siguen sumando
    cero a `metros_calculados()`; lo único que cambia es que ahora se pueden
    contar y decir.
    """
    return case((TripMileage.state.in_(TERMINALES_SIN_CIFRA), 1), else_=0)
