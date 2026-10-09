import { useCallback, useEffect, useState } from 'react';
import {
    Badge,
    Button,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog, LifecycleRowActions } from '@/features/Common';
import { fetchVehicles, type Vehicle } from '@/entities/RouteVehicles';
import {
    assignVehicle,
    deleteSupervisorProfile,
    designateSupervisor,
    endAssignment,
    fetchAssignmentHistory,
    fetchSupervisorCandidates,
    setSupervisorDesignation,
    setSupervisorTimeZone,
    type SupervisorCandidate,
    type VehicleAssignment,
} from '@/entities/RouteSupervisors';

/**
 * Configuración de supervisores: la cadena completa en una sola pantalla.
 *
 *     usuario del tenant  ->  designación de supervisor  ->  vehículo asignado
 *
 * Los tres son conceptos distintos y se administran como tales: la identidad
 * es del núcleo y se edita en Users; la designación es de Route; el vehículo
 * sale de la asignación vigente. Lo que esta pantalla evita es que el
 * administrador tenga que cruzarlos a mano — o, como ocurría antes de este
 * cierre, tener que llamar a la API para designar a alguien.
 *
 * Nada aquí borra: retirar la designación la desactiva, y terminar una
 * asignación la cierra con su fecha. La historia se conserva.
 */

/**
 * Zona horaria del supervisor (T-1/T-2): **opcional y para excepciones**.
 *
 * Por defecto es automática —cada jornada toma la del dispositivo— y nadie
 * tiene que configurar nada. Fijar una aquí es un override explícito para un
 * caso concreto: prevalece sobre la del teléfono en las jornadas que empiecen
 * después, y no cambia ninguna anterior.
 *
 * Las de Estados Unidos, que es donde trabaja la flota. El servidor acepta
 * cualquier zona IANA válida; si un perfil ya tiene otra, se añade a la lista
 * para no ocultarla.
 */
const AUTOMATICA = 'automatic';
const ZONAS_HABITUALES = [
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Phoenix',
    'America/Los_Angeles',
    'America/Anchorage',
    'Pacific/Honolulu',
    'America/Puerto_Rico',
];

function opcionesDeZona(actual: string | null | undefined): string[] {
    return actual && !ZONAS_HABITUALES.includes(actual)
        ? [...ZONAS_HABITUALES, actual]
        : ZONAS_HABITUALES;
}

function formatearFecha(valor: string | null | undefined): string {
    if (!valor) return '—';
    return new Date(valor).toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
    });
}

function detalleDeError(err: unknown, porDefecto: string): string {
    const detalle = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
    return detalle ?? porDefecto;
}

export function SupervisorSetupPanel() {
    const [candidates, setCandidates] = useState<SupervisorCandidate[]>([]);
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState<number | null>(null);
    const [history, setHistory] = useState<VehicleAssignment[]>([]);
    const [seleccion, setSeleccion] = useState<Record<number, string>>({});
    const [busy, setBusy] = useState(false);
    // La designación cuyo borrado espera confirmación.
    const [porBorrar, setPorBorrar] = useState<SupervisorCandidate | null>(null);
    const [borrando, setBorrando] = useState(false);
    // Motivo por el que el servidor rechazó el borrado.
    const [bloqueo, setBloqueo] = useState<string | null>(null);

    const cargar = useCallback(async () => {
        try {
            const [gente, vehs] = await Promise.all([
                fetchSupervisorCandidates(),
                fetchVehicles(),
            ]);
            setCandidates(gente);
            setVehicles(vehs);
            setError(null);
        } catch {
            setError('The supervisor setup could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        cargar();
    }, [cargar]);

    const designar = async (candidato: SupervisorCandidate) => {
        setBusy(true);
        setError(null);
        try {
            await designateSupervisor(candidato.user_id);
            await cargar();
        } catch (err) {
            setError(detalleDeError(err, 'The supervisor could not be designated.'));
        } finally {
            setBusy(false);
        }
    };

    const cambiarDesignacion = async (
        candidato: SupervisorCandidate,
        isActive: boolean,
    ) => {
        if (!candidato.supervisor_profile_id) return;
        setBusy(true);
        setError(null);
        try {
            await setSupervisorDesignation(
                candidato.supervisor_profile_id,
                isActive,
                candidato.supervisor_version ?? undefined,
            );
            await cargar();
        } catch (err) {
            setError(detalleDeError(err, 'The designation could not be changed.'));
        } finally {
            setBusy(false);
        }
    };

    const cambiarZona = async (candidato: SupervisorCandidate, valor: string) => {
        if (!candidato.supervisor_profile_id) return;
        setBusy(true);
        setError(null);
        try {
            await setSupervisorTimeZone(
                candidato.supervisor_profile_id,
                valor === AUTOMATICA ? null : valor,
                candidato.supervisor_version ?? undefined,
            );
            await cargar();
        } catch (err) {
            setError(detalleDeError(err, 'The time zone could not be changed.'));
        } finally {
            setBusy(false);
        }
    };

    /**
     * Confirma el borrado de la designación. Un 409 significa que todavía
     * conduce un vehículo: se explica en el propio diálogo en vez de como un
     * error suelto, porque el administrador puede resolverlo ahí mismo.
     */
    const confirmarBorrado = async () => {
        if (!porBorrar?.supervisor_profile_id) return;
        setError(null);
        setBorrando(true);
        try {
            await deleteSupervisorProfile(
                porBorrar.supervisor_profile_id,
                porBorrar.supervisor_version ?? undefined,
            );
            setPorBorrar(null);
            await cargar();
        } catch (err) {
            const estado = (err as { response?: { status?: number } })?.response?.status;
            if (estado === 409) {
                setBloqueo(detalleDeError(err, 'This designation cannot be deleted right now.'));
            } else {
                setPorBorrar(null);
                setError(detalleDeError(err, 'The designation could not be deleted.'));
            }
        } finally {
            setBorrando(false);
        }
    };

    const cerrarBorrado = (abierto: boolean) => {
        if (!abierto) {
            setPorBorrar(null);
            setBloqueo(null);
        }
    };

    const asignar = async (candidato: SupervisorCandidate) => {
        const profileId = candidato.supervisor_profile_id;
        const vehicleId = seleccion[candidato.user_id];
        if (!profileId || !vehicleId) return;

        setBusy(true);
        setError(null);
        try {
            await assignVehicle(profileId, Number(vehicleId));
            setSeleccion({ ...seleccion, [candidato.user_id]: '' });
            await cargar();
            if (expanded === profileId) {
                setHistory(await fetchAssignmentHistory(profileId));
            }
        } catch (err) {
            setError(detalleDeError(err, 'The vehicle could not be assigned.'));
        } finally {
            setBusy(false);
        }
    };

    const verHistorial = async (profileId: number) => {
        if (expanded === profileId) {
            setExpanded(null);
            return;
        }
        try {
            setHistory(await fetchAssignmentHistory(profileId));
            setExpanded(profileId);
        } catch {
            setError('The assignment history could not be loaded.');
        }
    };

    const terminar = async (assignmentId: number, profileId: number) => {
        setBusy(true);
        setError(null);
        try {
            await endAssignment(assignmentId);
            await cargar();
            setHistory(await fetchAssignmentHistory(profileId));
        } catch (err) {
            setError(detalleDeError(err, 'The assignment could not be ended.'));
        } finally {
            setBusy(false);
        }
    };

    if (loading) {
        return <p className="text-sm text-muted-foreground">Loading…</p>;
    }

    return (
        <div className="flex flex-col gap-4" data-testid="SupervisorSetupPanel">
            {error && <p className="text-sm text-destructive">{error}</p>}

            <p className="text-sm text-muted-foreground">
                A user becomes a Route supervisor when you designate them here.
                Identity itself is managed in Users.
            </p>

            <div className="rounded-lg border border-border bg-card">
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>User</TableHead>
                            <TableHead>Tenant role</TableHead>
                            <TableHead>Route supervisor</TableHead>
                            <TableHead>Current vehicle</TableHead>
                            <TableHead>Assign vehicle</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {candidates.map((candidato) => {
                            const esSupervisor = candidato.supervisor_profile_id !== null
                                && candidato.supervisor_profile_id !== undefined;
                            const activo = esSupervisor && candidato.supervisor_active;

                            return (
                                <TableRow key={candidato.user_id}>
                                    <TableCell>
                                        <span className="font-medium">
                                            {candidato.first_name}
                                            {' '}
                                            {candidato.last_name}
                                        </span>
                                        <span className="block text-xs text-muted-foreground">
                                            {candidato.email}
                                        </span>
                                        {!candidato.membership_active && (
                                            <Badge variant="secondary" className="mt-1">
                                                Access suspended
                                            </Badge>
                                        )}
                                    </TableCell>

                                    <TableCell className="text-sm text-muted-foreground">
                                        {candidato.role_name ?? '—'}
                                    </TableCell>

                                    <TableCell>
                                        {!esSupervisor && (
                                            <span className="text-sm text-muted-foreground">
                                                No
                                            </span>
                                        )}
                                        {esSupervisor && activo && (
                                            <>
                                                <Badge>Yes</Badge>
                                                <Select
                                                    value={candidato.supervisor_time_zone ?? AUTOMATICA}
                                                    onValueChange={(v) => cambiarZona(candidato, v)}
                                                    disabled={busy}
                                                >
                                                    <SelectTrigger
                                                        className="mt-2 h-8 w-44 text-xs"
                                                        aria-label="Time zone"
                                                    >
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value={AUTOMATICA}>
                                                            Time zone: automatic
                                                        </SelectItem>
                                                        {opcionesDeZona(
                                                            candidato.supervisor_time_zone,
                                                        ).map((zona) => (
                                                            <SelectItem key={zona} value={zona}>
                                                                {zona}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </>
                                        )}
                                        {esSupervisor && !activo && (
                                            <Badge variant="secondary">Removed</Badge>
                                        )}
                                    </TableCell>

                                    <TableCell>
                                        {candidato.current_vehicle ? (
                                            <Badge>{candidato.current_vehicle.unit}</Badge>
                                        ) : (
                                            <span className="text-sm text-muted-foreground">
                                                None
                                            </span>
                                        )}
                                    </TableCell>

                                    <TableCell>
                                        {activo ? (
                                            <div className="flex items-center gap-2">
                                                <Select
                                                    value={seleccion[candidato.user_id] ?? ''}
                                                    onValueChange={(v) => setSeleccion({
                                                        ...seleccion, [candidato.user_id]: v,
                                                    })}
                                                >
                                                    <SelectTrigger className="w-36">
                                                        <SelectValue placeholder="Vehicle" />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {vehicles.map((vehicle) => (
                                                            <SelectItem
                                                                key={vehicle.id}
                                                                value={String(vehicle.id)}
                                                            >
                                                                {vehicle.unit}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                                <Button
                                                    size="sm"
                                                    disabled={busy || !seleccion[candidato.user_id]}
                                                    onClick={() => asignar(candidato)}
                                                >
                                                    Assign
                                                </Button>
                                            </div>
                                        ) : (
                                            <span className="text-sm text-muted-foreground">—</span>
                                        )}
                                    </TableCell>

                                    <TableCell className="text-right">
                                        {!esSupervisor && (
                                            <Button
                                                size="sm"
                                                disabled={busy}
                                                onClick={() => designar(candidato)}
                                            >
                                                Designate
                                            </Button>
                                        )}
                                        {esSupervisor && (
                                            <>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => verHistorial(
                                                        candidato.supervisor_profile_id as number,
                                                    )}
                                                >
                                                    History
                                                </Button>
                                                {/* Sin `onEdit`: el perfil de
                                                    Route no tiene campos que
                                                    editar todavía. Lo que se
                                                    edita es la persona, y eso
                                                    vive en la pantalla de
                                                    usuarios, que es su dueña. */}
                                                <LifecycleRowActions
                                                    isActive={activo === true}
                                                    disabled={busy}
                                                    labels={{
                                                        deactivate: 'Remove designation',
                                                        reactivate: 'Restore designation',
                                                        delete: 'Delete designation',
                                                    }}
                                                    onDeactivate={
                                                        () => cambiarDesignacion(candidato, false)
                                                    }
                                                    onReactivate={
                                                        () => cambiarDesignacion(candidato, true)
                                                    }
                                                    onDelete={() => setPorBorrar(candidato)}
                                                />
                                            </>
                                        )}
                                    </TableCell>
                                </TableRow>
                            );
                        })}
                    </TableBody>
                </Table>
            </div>

            {expanded !== null && (
                <section className="rounded-lg border border-border bg-card p-4">
                    <h4 className="text-sm font-semibold text-foreground">
                        Assignment history
                    </h4>
                    {history.length === 0 ? (
                        <p className="mt-2 text-sm text-muted-foreground">
                            This supervisor has never had a vehicle assigned.
                        </p>
                    ) : (
                        <Table className="mt-2">
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Vehicle</TableHead>
                                    <TableHead>From</TableHead>
                                    <TableHead>To</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {history.map((row) => (
                                    <TableRow key={row.id}>
                                        <TableCell>
                                            {row.vehicle_unit}
                                            <span className="block text-xs text-muted-foreground">
                                                {row.vehicle_year}
                                                {' '}
                                                {row.vehicle_make}
                                                {' '}
                                                {row.vehicle_model}
                                            </span>
                                        </TableCell>
                                        <TableCell>{formatearFecha(row.effective_from)}</TableCell>
                                        <TableCell>
                                            {row.effective_to
                                                ? formatearFecha(row.effective_to)
                                                : <Badge>Current</Badge>}
                                        </TableCell>
                                        <TableCell className="text-right">
                                            {!row.effective_to && (
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    disabled={busy}
                                                    onClick={() => terminar(row.id, expanded)}
                                                >
                                                    End
                                                </Button>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </section>
            )}
            <ConfirmDestructiveDialog
                open={porBorrar !== null}
                onOpenChange={cerrarBorrado}
                title="Delete this Route designation?"
                description={(
                    <>
                        The person stays in this company with their role and access
                        untouched — only their Route supervisor designation is
                        removed. Past vehicle assignments stay readable, and they can
                        be designated again later.
                    </>
                )}
                blockedReason={bloqueo}
                busy={borrando}
                onConfirm={confirmarBorrado}
            />
        </div>
    );
}
