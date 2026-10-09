import { Card } from '@/shared/ui/shadcn/new-york';
import {
    formatClock,
    formatMiles,
    spanBetween,
    TRIP_PURPOSE_LABEL,
    type ExplorerActivity,
} from '@/entities/RouteActivityExplorer';

/**
 * Las tarjetas de parada del día, como `activityCards()` de la línea base.
 *
 * La estructura del mockup, respetada: cabecera con el propósito y su
 * referencia más el tramo horario a la izquierda y el resumen
 * `span · trip miles` a la derecha; cuerpo con las líneas `Travel`,
 * `At destination`, `Reason`, `Outcome` y `Note` —ésta a dos columnas.
 *
 * Una parada es un hecho, no varios
 * ----------------------------------
 * Si en la parada se seleccionaron tres actividades, se enseñan las tres en la
 * **misma** tarjeta, compartiendo horas, resultado y nota. Es la adaptación
 * mínima que §5 autoriza: el modelo certificado tiene un bloque de ejecución
 * por viaje, y partirlo en tres tarjetas fabricaría tres visitas donde hubo
 * una. PR-03 lo prohíbe de forma explícita.
 *
 * `Reason`, y por qué no mezcla propósito con actividad
 * -----------------------------------------------------
 * El dominio certificado parte los contextos en dos conjuntos **disjuntos**:
 * Client Visit, Recruiting y Other eligen actividades **al llegar**; Employee
 * Visit, Office y Check Delivery traen su valor **desde el plan**. Nunca los
 * dos. Así que esta línea enseña lo que cualificó la parada en cada caso, y el
 * propósito sigue en la cabecera: eso es mantenerlos distintos (PR-04), no
 * colapsarlos.
 */
interface ExplorerActivityCardsProps {
    activities: ExplorerActivity[];
}

export function ExplorerActivityCards({ activities }: ExplorerActivityCardsProps) {
    if (activities.length === 0) {
        return (
            <Card className="p-5">
                <p className="py-8 text-center text-sm text-muted-foreground">
                    No recorded activity on this day.
                </p>
            </Card>
        );
    }

    return (
        <div className="flex flex-col gap-2.5 xl:gap-3">
            {activities.map((a) => {
                const razon = a.activity_labels.length > 0
                    ? a.activity_labels.join(', ')
                    : (a.purpose_detail || '—');
                // Las horas, en la zona de la jornada de esta parada (T-2).
                const zona = {
                    timeZone: a.time_zone,
                    utcOffsetMinutes: a.utc_offset_minutes,
                };
                return (
                    /* `trip_id` y no `activity_execution_id`: desde R-1 la
                       lista incluye viajes que no abrieron parada, y en ésos
                       el identificador de actividad es nulo. El del viaje
                       siempre existe y no se repite —hay como mucho una parada
                       por viaje—, así que es la clave estable. */
                    <Card key={a.trip_id} className="overflow-hidden p-0">
                        <div className="flex items-center justify-between gap-3.5 border-b border-border bg-muted/40 px-3 py-2.5 xl:px-4 xl:py-3.5">
                            <div>
                                <h4 className="text-sm font-semibold text-foreground">
                                    {TRIP_PURPOSE_LABEL[a.purpose] ?? a.purpose}
                                </h4>
                                <div className="text-xs text-muted-foreground">
                                    {/*
                                      * `formatClock(null)` dice `In progress`,
                                      * y para una parada abierta es verdad. Un
                                      * viaje que nunca abrió ninguna no tiene
                                      * nada en curso, así que ahí el extremo
                                      * del rango es un hueco y no una promesa
                                      * de que algo va a cerrarse (AC3).
                                      */}
                                    {a.context_reference || '—'} ·{' '}
                                    {formatClock(a.trip_started_at, zona)}
                                    –
                                    {a.has_activity ? formatClock(a.ended_at, zona) : '—'}
                                </div>
                            </div>
                            <div className="text-right">
                                <b className="block text-sm font-semibold text-foreground">
                                    {spanBetween(a.trip_started_at, a.ended_at)} ·{' '}
                                    {formatMiles(a.official_miles)} mi
                                    {a.mileage_pending && (
                                        <span className="ml-1 text-xs font-normal text-muted-foreground">
                                            + pending
                                        </span>
                                    )}
                                </b>
                                <span className="text-xs text-muted-foreground">
                                    activity span · trip miles
                                </span>
                            </div>
                        </div>
                        <div className="grid grid-cols-2 gap-3 px-3 py-2.5 xl:grid-cols-3 xl:px-4 xl:py-3.5">
                            <div className="text-xs">
                                <span className="block text-muted-foreground">Travel</span>
                                <b className="font-medium text-foreground">
                                    {spanBetween(a.trip_started_at, a.arrived_at)}
                                </b>
                            </div>
                            <div className="text-xs">
                                <span className="block text-muted-foreground">
                                    At destination
                                </span>
                                <b className="font-medium text-foreground">
                                    {spanBetween(a.started_at, a.ended_at)}
                                </b>
                            </div>
                            <div className="text-xs">
                                <span className="block text-muted-foreground">Reason</span>
                                <b className="font-medium text-foreground">{razon}</b>
                            </div>
                            <div className="text-xs">
                                <span className="block text-muted-foreground">Outcome</span>
                                <b className="font-medium text-foreground">
                                    {/*
                                      * Sin parada no hay resultado **ni lo
                                      * habrá**, así que no es `In progress`:
                                      * eso afirmaría que hay algo abierto
                                      * esperando a que alguien lo cierre. Un
                                      * regreso a casa no abre nada.
                                      */}
                                    {a.has_activity
                                        ? (a.outcome_label || 'In progress')
                                        : '—'}
                                </b>
                            </div>
                            {/*
                              * `Note` ocupa **dos** columnas, no las tres: en
                              * la línea base queda a la derecha de `Outcome` en
                              * la segunda fila (`grid-column: span 2` sobre una
                              * rejilla de tres). Dejarla a ancho completo la
                              * empujaba a una tercera fila y cambiaba la
                              * jerarquía visual aprobada.
                              */}
                            <div className="col-span-2 text-xs">
                                <span className="block text-muted-foreground">Note</span>
                                <b className="font-medium text-foreground">
                                    {a.notes || '—'}
                                </b>
                            </div>
                        </div>
                    </Card>
                );
            })}
        </div>
    );
}
