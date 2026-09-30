import { useEffect, useState } from 'react';
import { captureFor } from '@/shared/lib/location';
import {
    Button, Checkbox, Label, Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue, Textarea,
} from '@/shared/ui/shadcn/new-york';
import { normalizeApiError } from '@/shared/api';
import { fetchStandardValues, type StandardValue } from '@/entities/RouteStandardValues';
import { type Trip } from '@/entities/RouteTrips';
import {
    OUTCOME_LIST,
    POSTARRIVAL_ACTIVITY_LIST,
    RECEIVED_BY_LIST,
    queueStartActivity,
    queueTerminalizeActivity,
    requiereActividades,
    registraReceptor,
    exigeReceptor,
    type ActivityExecution,
    type TerminalAction,
} from '@/entities/RouteActivities';

/**
 * Lo que se hace al llegar, y cómo se cierra la parada.
 *
 * Dos momentos, una sola parada
 * ------------------------------
 * Antes de empezar se elige **qué** se va a hacer, donde el contexto lo pide.
 * Después sólo hay dos salidas: terminar o marcharse, y las dos exigen decir
 * cómo fue. No hay una tercera que cierre sola, y no hay un botón de "salir sin
 * más": marcharse es una decisión que se registra, no un abandono.
 *
 * Un bloque, aunque se hayan elegido tres cosas
 * ----------------------------------------------
 * Las actividades seleccionadas son etiquetas de esta parada. Hay un solo
 * cronómetro, un solo resultado y una sola nota — quien atiende a un cliente
 * hace tres cosas en la misma visita, no tres visitas.
 *
 * Qué pide cada contexto sale de la matriz aprobada, no de un `if` aquí. Employee
 * Visit y Office ya trajeron su dato al planificar y no vuelven a preguntarlo;
 * Check Delivery añade quién recibió, que sólo se sabe al llegar.
 */

interface ActivityStopProps {
    trip: Trip;
    /** El bloque en marcha, si ya se arrancó. */
    execution: ActivityExecution | null;
    /** Se llama tras cada cambio para releer el estado autoritativo. */
    onChanged: () => void | Promise<void>;
}

function formatearHora(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, {
        hour: 'numeric',
        minute: '2-digit',
    });
}

/**
 * Cuánto lleva abierta la parada, en la unidad que se lee de un vistazo.
 *
 * Minutos y horas, nunca segundos: nadie mira un cronómetro al segundo mientras
 * atiende a un cliente, y un número que cambia sin parar sólo distrae. Por
 * debajo del minuto se dice con palabras, porque "0m" parece un fallo.
 */
function transcurrido(desde: string, ahora: number): string {
    const minutos = Math.floor((ahora - new Date(desde).getTime()) / 60_000);
    if (minutos < 1) return 'just started';
    if (minutos < 60) return `${minutos}m`;
    return `${Math.floor(minutos / 60)}h ${minutos % 60}m`;
}

export function ActivityStop({ trip, execution, onChanged }: ActivityStopProps) {
    const purpose = trip.current_purpose;
    const listaActividades = POSTARRIVAL_ACTIVITY_LIST[purpose];

    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [opciones, setOpciones] = useState<StandardValue[]>([]);
    const [elegidas, setElegidas] = useState<number[]>([]);

    const [resultados, setResultados] = useState<StandardValue[]>([]);
    const [receptores, setReceptores] = useState<StandardValue[]>([]);
    const [resultado, setResultado] = useState('');
    const [receptor, setReceptor] = useState('');
    const [nota, setNota] = useState('');
    // La salida elegida, mientras se rellena el resultado. `null` = sin elegir.
    const [saliendo, setSaliendo] = useState<TerminalAction | null>(null);
    // El reloj de pared, para que el transcurrido avance sin recargar.
    const [ahora, setAhora] = useState(() => Date.now());

    const enMarcha = execution?.status === 'in_progress';

    useEffect(() => {
        if (!enMarcha) return undefined;
        // Cada medio minuto: el texto sólo cambia por minutos, y un intervalo
        // de un segundo despertaría la pantalla sesenta veces para nada.
        const reloj = window.setInterval(() => setAhora(Date.now()), 30_000);
        return () => window.clearInterval(reloj);
    }, [enMarcha]);

    useEffect(() => {
        if (!listaActividades || enMarcha) return;
        fetchStandardValues(listaActividades)
            .then(setOpciones)
            .catch(() => setOpciones([]));
    }, [listaActividades, enMarcha]);

    useEffect(() => {
        if (!saliendo) return;
        fetchStandardValues(OUTCOME_LIST).then(setResultados).catch(() => setResultados([]));
        if (registraReceptor(purpose)) {
            fetchStandardValues(RECEIVED_BY_LIST)
                .then(setReceptores)
                .catch(() => setReceptores([]));
        }
    }, [saliendo, purpose]);

    const fallo = (err: unknown) => setError(normalizeApiError(err).message);

    const alternar = (id: number) => {
        setElegidas((actuales) => (
            actuales.includes(id)
                ? actuales.filter((x) => x !== id)
                : [...actuales, id]
        ));
    };

    const empezar = async () => {
        setBusy(true);
        setError(null);
        try {
            await queueStartActivity(trip.id, elegidas);
            await onChanged();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    const terminar = async () => {
        // `execution` se comprueba aquí y no sólo en el render: esta función la
        // captura el closure, así que el `if (!execution)` de más abajo no le
        // dice nada al tipo. Sin bloque no hay nada que terminar ni nada a lo
        // que atar la ubicación.
        if (!saliendo || !resultado || !execution) return;
        setBusy(true);
        setError(null);
        try {
            await queueTerminalizeActivity(trip.id, {
                action: saliendo,
                outcomeId: Number(resultado),
                notes: nota,
                receivedById: receptor ? Number(receptor) : null,
            });
            // El evento tiene que ser el que de verdad pasó: completar y dejar
            // son dos hechos distintos y el servidor los comprueba contra la
            // acción terminal guardada, así que mandar el otro se rechaza.
            captureFor(
                saliendo === 'complete' ? 'activity_complete' : 'activity_leave',
                { subjectId: execution.id },
            );
            await onChanged();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    // Al marcharse el receptor no bloquea, pero si se eligió se conserva y
    // viaja igual: opcional no es lo mismo que descartable.
    const faltaAlgo = !resultado
        || (saliendo !== null && exigeReceptor(purpose, saliendo) && !receptor);

    /**
     * Sólo el reloj de la parada: quién es el destino ya lo dice la pantalla
     * que envuelve a este componente, y repetirlo daría dos cabeceras que
     * pueden discrepar.
     */
    const cabecera = (inicio: string) => (
        <div className="text-center">
            {/* El transcurrido y la hora de inicio, en dos líneas separadas: la
                primera cambia cada minuto y la segunda no cambia nunca. */}
            <p className="text-lg font-semibold text-foreground">
                {transcurrido(inicio, ahora)}
            </p>
            <p className="text-sm text-muted-foreground">
                {`Working here since ${formatearHora(inicio)}`}
            </p>
        </div>
    );

    // ── Antes de empezar ────────────────────────────────────────────────────
    if (!execution) {
        // Aquí no va `cabecera`: sin bloque no hay reloj que enseñar.
        return (
            <div className="flex flex-col gap-4" data-testid="ActivityStopSetup">
                {listaActividades && (
                    <section className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5">
                        <p className="text-sm font-medium text-foreground">
                            What are you doing here?
                        </p>
                        {/* Varias a la vez: es una parada con varias etiquetas,
                            no varias paradas. */}
                        {opciones.map((opcion) => (
                            <label
                                key={opcion.id}
                                className="flex items-center gap-3 text-sm text-foreground"
                            >
                                <Checkbox
                                    checked={elegidas.includes(opcion.id)}
                                    onCheckedChange={() => alternar(opcion.id)}
                                />
                                {opcion.label}
                            </label>
                        ))}
                        {opciones.length === 0 && (
                            <p className="text-sm text-muted-foreground">
                                No activities are configured yet. Ask an
                                administrator to add one.
                            </p>
                        )}
                    </section>
                )}

                {error && (
                    <p className="text-center text-sm text-destructive">{error}</p>
                )}

                <Button
                    size="lg"
                    className="h-16 w-full text-lg"
                    disabled={
                        busy
                        || (requiereActividades(purpose) && elegidas.length === 0)
                    }
                    onClick={empezar}
                >
                    Start Activity
                </Button>
            </div>
        );
    }

    // ── En marcha, eligiendo cómo salir ─────────────────────────────────────
    if (saliendo) {
        return (
            <div className="flex flex-col gap-4" data-testid="ActivityStopFinish">
                {cabecera(execution.started_at)}

                <section className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5">
                    <p className="text-base font-medium text-foreground">
                        {saliendo === 'complete' ? 'Finish here' : 'Leave this stop'}
                    </p>

                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="activity-outcome">How did it go?</Label>
                        <Select value={resultado} onValueChange={setResultado}>
                            <SelectTrigger id="activity-outcome" className="h-12">
                                <SelectValue placeholder="Choose one" />
                            </SelectTrigger>
                            <SelectContent>
                                {resultados.map((o) => (
                                    <SelectItem key={o.id} value={String(o.id)}>
                                        {o.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {registraReceptor(purpose) && (
                        <div className="flex flex-col gap-1.5">
                            <Label htmlFor="activity-received-by">
                                Received by
                                {/* Sólo se marca donde de verdad es opcional:
                                    al marcharse. Al completar va sin marca,
                                    como el resultado, porque lo obligatorio es
                                    el caso normal. */}
                                {saliendo === 'leave' && (
                                    <span className="ml-1 text-muted-foreground">
                                        (optional)
                                    </span>
                                )}
                            </Label>
                            <Select value={receptor} onValueChange={setReceptor}>
                                <SelectTrigger id="activity-received-by" className="h-12">
                                    <SelectValue placeholder="Choose one" />
                                </SelectTrigger>
                                <SelectContent>
                                    {receptores.map((r) => (
                                        <SelectItem key={r.id} value={String(r.id)}>
                                            {r.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}

                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="activity-notes">
                            Notes
                            <span className="ml-1 text-muted-foreground">(optional)</span>
                        </Label>
                        <Textarea
                            id="activity-notes"
                            rows={3}
                            value={nota}
                            onChange={(e) => setNota(e.target.value)}
                        />
                    </div>

                    {error && (
                        <p className="text-center text-sm text-destructive">{error}</p>
                    )}

                    <Button
                        size="lg"
                        className="h-14 w-full text-lg"
                        disabled={busy || faltaAlgo}
                        onClick={terminar}
                    >
                        {saliendo === 'complete' ? 'Complete Activity' : 'Leave'}
                    </Button>
                    <Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => { setSaliendo(null); setError(null); }}
                    >
                        Back
                    </Button>
                </section>
            </div>
        );
    }

    // ── En marcha ───────────────────────────────────────────────────────────
    return (
        <div className="flex flex-col gap-4" data-testid="ActivityStopRunning">
            {cabecera(execution.started_at)}

            {execution.activities.length > 0 && (
                <section className="rounded-lg border border-border bg-card p-5">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                        Doing
                    </p>
                    <ul className="mt-2 flex flex-col gap-1">
                        {execution.activities.map((a) => (
                            <li key={a.standard_value_id} className="text-sm text-foreground">
                                {a.label}
                            </li>
                        ))}
                    </ul>
                </section>
            )}

            {error && <p className="text-center text-sm text-destructive">{error}</p>}

            <Button
                size="lg"
                className="h-16 w-full text-lg"
                disabled={busy}
                onClick={() => setSaliendo('complete')}
            >
                Complete Activity
            </Button>
            <Button
                variant="outline"
                size="lg"
                className="h-14 w-full"
                disabled={busy}
                onClick={() => setSaliendo('leave')}
            >
                Leave
            </Button>
        </div>
    );
}
