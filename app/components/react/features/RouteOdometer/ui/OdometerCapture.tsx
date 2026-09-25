import { useRef, useState } from 'react';
import {
    Button, Input, Label, Select, SelectContent, SelectItem,
    SelectTrigger, SelectValue, Textarea,
} from '@/shared/ui/shadcn/new-york';
import { normalizeApiError } from '@/shared/api';
import {
    confirmOdometerReading,
    ODOMETER_EXCEPTION_REASONS,
    ODOMETER_REASON_LABELS,
    readingAsNumber,
    requestOdometerException,
    uploadOdometerPhoto,
    type OdometerEnd,
    type OdometerEvidence,
    type OdometerExceptionReason,
} from '@/entities/RouteOdometer';

/**
 * Capturar la lectura del cuentakilómetros.
 *
 * Se renderiza **debajo** del contexto del viaje que el supervisor ya eligió,
 * no encima de él: el plan sigue a la vista mientras resuelve la foto, y al
 * terminar vuelve exactamente a ese mismo flujo sin volver a elegir nada.
 *
 * El camino normal es foto y confirmación
 * ----------------------------------------
 * Si el OCR sugiere algo, se ofrece como borrador editable. Si no sugiere nada
 * —que es lo que hace el despliegue por defecto— el supervisor teclea lo que
 * ve, y **eso sigue siendo evidencia fotográfica**: no pide permiso a nadie.
 * Esta pantalla no llama "manual" a ese caso, porque llamarlo así empujaría a
 * la gente hacia la excepción sin necesitarla.
 *
 * Teclear sin foto es otra cosa
 * ------------------------------
 * No hay botón de "escribir a mano" suelto. Hay "no puedo hacer la foto", que
 * abre una solicitud con motivo y espera a un administrador. Mientras espera,
 * el supervisor puede seguir trabajando en lo que no sea conducir — pero no
 * puede salir, y la pantalla lo dice con esas palabras.
 */

interface OdometerCaptureProps {
    sessionId: number;
    end: OdometerEnd;
    evidence: OdometerEvidence;
    /** Se llama cuando el extremo queda resuelto y el flujo puede continuar. */
    onResolved: () => void | Promise<void>;
    /** Se llama al pedir la excepción, para que la pantalla se recargue. */
    onChanged?: () => void | Promise<void>;
    onCancel?: () => void;
}

const TITULOS: Record<OdometerEnd, string> = {
    start: 'Starting odometer',
    end: 'Ending odometer',
};

export function OdometerCapture(props: OdometerCaptureProps) {
    const {
        sessionId, end, evidence, onResolved, onChanged, onCancel,
    } = props;

    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lectura, setLectura] = useState('');
    const [sugerencia, setSugerencia] = useState<number | null>(
        readingAsNumber(evidence.ocr_detected_reading),
    );
    const [tieneFoto, setTieneFoto] = useState(
        evidence.captured_at !== null && evidence.captured_at !== undefined,
    );
    const [pidiendoExcepcion, setPidiendoExcepcion] = useState(false);
    const [motivo, setMotivo] = useState<OdometerExceptionReason | ''>('');
    const [nota, setNota] = useState('');
    const archivo = useRef<HTMLInputElement>(null);

    const fallo = (err: unknown) => setError(normalizeApiError(err).message);

    const subirFoto = async (foto: File) => {
        setBusy(true);
        setError(null);
        try {
            const resultado = await uploadOdometerPhoto(sessionId, end, foto);
            const sugerido = readingAsNumber(resultado.ocr_suggestion);
            setSugerencia(sugerido);
            // La sugerencia se ofrece como borrador editable, nunca como hecho:
            // quien confirma es la persona que está mirando el salpicadero.
            if (sugerido !== null) setLectura(String(sugerido));
            setTieneFoto(true);
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    const confirmar = async () => {
        setBusy(true);
        setError(null);
        try {
            await confirmOdometerReading(sessionId, end, lectura.trim());
            await onResolved();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    const pedirExcepcion = async () => {
        if (!motivo) return;
        setBusy(true);
        setError(null);
        try {
            await requestOdometerException(sessionId, end, motivo, nota);
            setPidiendoExcepcion(false);
            await onChanged?.();
        } catch (err) {
            fallo(err);
        } finally {
            setBusy(false);
        }
    };

    const aprobada = evidence.status === 'exception_approved';
    const esperando = evidence.status === 'exception_requested';
    const puedeConfirmar = (tieneFoto || aprobada)
        && lectura.trim() !== ''
        && Number.isFinite(Number(lectura));

    const aviso = (
        <p className="text-center text-xs text-muted-foreground">
            You can keep doing work that does not involve driving, but you cannot
            start a trip until this reading is recorded.
        </p>
    );

    const entradaDeFoto = (
        <input
            ref={archivo}
            type="file"
            accept="image/*"
            // Abre la cámara trasera en el móvil, que es donde se usa esto. En
            // escritorio degrada a un selector de archivo normal.
            capture="environment"
            className="hidden"
            data-testid="OdometerPhotoInput"
            onChange={(e) => {
                const foto = e.target.files?.[0];
                if (foto) subirFoto(foto);
                e.target.value = '';
            }}
        />
    );

    // ── Esperando a que un administrador decida ─────────────────────────────
    if (esperando) {
        return (
            <section
                data-testid="OdometerCapture"
                className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5"
            >
                <p className="text-center text-base font-medium text-foreground">
                    {TITULOS[end]}
                </p>
                <p className="text-center text-sm text-foreground">
                    Your request to enter the reading without a photo is waiting
                    for review.
                </p>
                {aviso}
                <Button
                    variant="outline"
                    className="h-12 w-full"
                    disabled={busy}
                    onClick={() => archivo.current?.click()}
                >
                    Take the photo after all
                </Button>
                {entradaDeFoto}
                {error && (
                    <p className="text-center text-sm text-destructive">{error}</p>
                )}
                {onCancel && (
                    <Button variant="ghost" disabled={busy} onClick={onCancel}>
                        Not now
                    </Button>
                )}
            </section>
        );
    }

    // ── Pidiendo la excepción ───────────────────────────────────────────────
    if (pidiendoExcepcion) {
        return (
            <section
                data-testid="OdometerExceptionRequest"
                className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
            >
                <p className="text-base font-medium text-foreground">
                    Why can&apos;t you take the photo?
                </p>
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-reason">Reason</Label>
                    <Select
                        value={motivo}
                        onValueChange={(v) => setMotivo(v as OdometerExceptionReason)}
                    >
                        <SelectTrigger id="odometer-reason" className="h-12">
                            <SelectValue placeholder="Choose one" />
                        </SelectTrigger>
                        <SelectContent>
                            {ODOMETER_EXCEPTION_REASONS.map((codigo) => (
                                <SelectItem key={codigo} value={codigo}>
                                    {ODOMETER_REASON_LABELS[codigo]}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-note">
                        Anything to add
                        <span className="ml-1 text-muted-foreground">(optional)</span>
                    </Label>
                    <Textarea
                        id="odometer-note"
                        value={nota}
                        rows={2}
                        onChange={(e) => setNota(e.target.value)}
                    />
                </div>
                <p className="text-xs text-muted-foreground">
                    Someone with admin access reviews this. Until it is approved
                    and you enter the reading, you cannot start a trip.
                </p>
                {error && (
                    <p className="text-center text-sm text-destructive">{error}</p>
                )}
                <Button
                    size="lg"
                    className="h-14 w-full"
                    disabled={busy || !motivo}
                    onClick={pedirExcepcion}
                >
                    Send request
                </Button>
                <Button
                    variant="ghost"
                    disabled={busy}
                    onClick={() => setPidiendoExcepcion(false)}
                >
                    Back
                </Button>
            </section>
        );
    }

    // ── Camino normal, y la entrada manual ya autorizada ────────────────────
    return (
        <section
            data-testid="OdometerCapture"
            className="flex flex-col gap-4 rounded-lg border border-border bg-card p-5"
        >
            <div className="text-center">
                <p className="text-base font-medium text-foreground">
                    {TITULOS[end]}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                    {aprobada
                        ? 'Approved: enter the reading you can see on the vehicle.'
                        : 'Take a photo of the odometer, then confirm the reading.'}
                </p>
            </div>

            {!aprobada && (
                <>
                    <Button
                        size="lg"
                        variant={tieneFoto ? 'outline' : 'default'}
                        className="h-14 w-full text-base"
                        disabled={busy}
                        onClick={() => archivo.current?.click()}
                    >
                        {tieneFoto ? 'Retake photo' : 'Take photo'}
                    </Button>
                    {entradaDeFoto}
                </>
            )}

            {(tieneFoto || aprobada) && (
                <div className="flex flex-col gap-1.5">
                    <Label htmlFor="odometer-reading">
                        {aprobada ? 'Reading (no photo)' : 'Reading on the photo'}
                    </Label>
                    <Input
                        id="odometer-reading"
                        data-testid="OdometerReadingInput"
                        className="h-14 text-center text-2xl"
                        // `decimal` levanta el teclado numérico del móvil sin
                        // impedir el punto de las décimas.
                        inputMode="decimal"
                        value={lectura}
                        onChange={(e) => setLectura(e.target.value)}
                        placeholder="0"
                    />
                    {sugerencia !== null && (
                        <p className="text-xs text-muted-foreground">
                            {`Suggested from the photo: ${sugerencia} — check it against the vehicle before confirming.`}
                        </p>
                    )}
                </div>
            )}

            {error && (
                <p className="text-center text-sm text-destructive">{error}</p>
            )}

            {(tieneFoto || aprobada) && (
                <Button
                    size="lg"
                    className="h-14 w-full text-lg"
                    disabled={busy || !puedeConfirmar}
                    onClick={confirmar}
                >
                    Confirm reading
                </Button>
            )}

            {!aprobada && !tieneFoto && (
                <>
                    {aviso}
                    <Button
                        variant="ghost"
                        className="h-12 w-full"
                        disabled={busy}
                        onClick={() => setPidiendoExcepcion(true)}
                    >
                        I can&apos;t take a photo
                    </Button>
                </>
            )}

            {onCancel && (
                <Button variant="ghost" disabled={busy} onClick={onCancel}>
                    Not now
                </Button>
            )}
        </section>
    );
}
