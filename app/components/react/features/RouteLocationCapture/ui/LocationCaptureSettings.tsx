import { useCallback, useEffect, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import {
    Button, Checkbox, Input, Label,
} from '@/shared/ui/shadcn/new-york';
import { PERIODIC_CAPTURE_NOTICE } from '@/shared/lib/location';
import {
    fetchCaptureSetting, updateCaptureSetting, type CaptureSetting,
} from '@/entities/RouteLocationCapture';

function mensajeDeError(error: unknown): string {
    const estado = (error as { response?: { status?: number } })?.response?.status;
    if (estado === 409) return 'Someone else changed this setting. Reload it and apply your change again.';
    if (estado === 422) return 'The interval is out of the allowed range.';
    return 'The setting could not be saved.';
}

/**
 * Periodic Location Capture (RTE-LOC-02): encender, apagar y el intervalo, por
 * compañía. Lo guarda el servidor, que comprueba el permiso, el rango y la
 * versión, y lo audita. Los dispositivos lo aplican al volver a primer plano o
 * en el siguiente ciclo, sin recargar.
 *
 * No toca la captura por evento: con esto apagado, Start Work, Start Trip,
 * Arrived y End Work siguen registrando su punto igual que siempre.
 */
export function LocationCaptureSettings() {
    const [actual, setActual] = useState<CaptureSetting | null>(null);
    const [activa, setActiva] = useState(false);
    const [intervalo, setIntervalo] = useState('300');
    const [guardando, setGuardando] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [aviso, setAviso] = useState<string | null>(null);

    const aplicar = (s: CaptureSetting) => {
        setActual(s);
        setActiva(s.enabled);
        setIntervalo(String(s.interval_seconds));
    };

    const cargar = useCallback(async () => {
        setError(null);
        try {
            aplicar(await fetchCaptureSetting());
        } catch {
            setError('The setting could not be loaded.');
        }
    }, []);

    useEffect(() => {
        cargar();
    }, [cargar]);

    if (!actual) {
        return error
            ? <p role="alert" className="text-sm text-destructive">{error}</p>
            : <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />;
    }

    const segundos = Number(intervalo);
    const valido = Number.isInteger(segundos)
        && segundos >= actual.min_interval_seconds
        && segundos <= actual.max_interval_seconds;
    const cambiado = activa !== actual.enabled || segundos !== actual.interval_seconds;

    const guardar = async () => {
        setGuardando(true);
        setError(null);
        setAviso(null);
        try {
            aplicar(await updateCaptureSetting({
                enabled: activa, interval_seconds: segundos, version: actual.version,
            }));
            setAviso('Saved. Devices apply it the next time they check, without reloading.');
        } catch (err) {
            setError(mensajeDeError(err));
        } finally {
            setGuardando(false);
        }
    };

    return (
        <section aria-label="Periodic Location Capture" className="max-w-xl space-y-5 rounded-lg border bg-card p-5">
            <div className="flex items-start gap-2">
                <MapPin className="mt-0.5 size-4 shrink-0 text-primary" />
                <div className="space-y-1">
                    <h2 className="text-base font-semibold">Periodic Location Capture</h2>
                    <p className="text-sm text-muted-foreground">
                        Records one location point every interval during an active workday, while CER Route is
                        open. Event points (Start Work, Start Trip, Arrived, activities, End Work) are recorded
                        either way. Not guaranteed with the screen locked or the app closed.
                    </p>
                </div>
            </div>

            <p role="status" className="rounded-md border bg-muted/40 p-3 text-sm">
                <span className="font-medium">Current status: </span>
                {actual.enabled ? `On — every ${actual.interval_seconds} s` : 'Off'}
                {actual.updated_at && (
                    <span className="text-muted-foreground">
                        {` · last changed ${new Date(actual.updated_at).toLocaleString()}`}
                    </span>
                )}
            </p>

            <div className="flex items-center gap-3">
                <Checkbox
                    id="capture-enabled"
                    checked={activa}
                    onCheckedChange={(v) => setActiva(v === true)}
                    disabled={guardando}
                />
                <Label htmlFor="capture-enabled">Enable periodic capture</Label>
            </div>

            <div className="space-y-1.5">
                <Label htmlFor="capture-interval">Interval (seconds)</Label>
                <Input
                    id="capture-interval"
                    type="number"
                    inputMode="numeric"
                    className="w-40"
                    min={actual.min_interval_seconds}
                    max={actual.max_interval_seconds}
                    value={intervalo}
                    disabled={guardando}
                    onChange={(e) => setIntervalo(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                    {`Between ${actual.min_interval_seconds} and ${actual.max_interval_seconds} seconds. `}
                    Default 300 (5 minutes).
                </p>
            </div>

            {activa && (
                <p className="text-xs text-muted-foreground">
                    {`Shown to people on My Route while it is on: "${PERIODIC_CAPTURE_NOTICE}"`}
                </p>
            )}

            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            {aviso && <p className="text-sm text-muted-foreground">{aviso}</p>}

            <Button type="button" disabled={!valido || !cambiado || guardando} onClick={guardar}>
                {guardando && <Loader2 className="mr-2 size-4 animate-spin" />}
                Save
            </Button>
        </section>
    );
}
