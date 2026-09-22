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
import { fetchVehicles, type Vehicle } from '@/entities/RouteVehicles';
import {
    assignVehicle,
    endAssignment,
    fetchAssignmentHistory,
    fetchSupervisors,
    type SupervisorProfile,
    type VehicleAssignment,
} from '@/entities/RouteSupervisors';

/**
 * Asignación de vehículo a supervisor, con su historial.
 *
 * El vehículo actual de cada fila **no** se guarda en el perfil: lo deriva el
 * servidor de la asignación abierta. Reasignar cierra la anterior e inserta
 * una nueva, así que el historial crece y no se sobrescribe — que es lo que
 * permitirá a una jornada de marzo saber con qué vehículo se hizo.
 */

function formatearFecha(valor: string | null | undefined): string {
    if (!valor) return '—';
    return new Date(valor).toLocaleDateString(undefined, {
        year: 'numeric', month: 'short', day: 'numeric',
    });
}

export function SupervisorAssignmentsPanel() {
    const [supervisors, setSupervisors] = useState<SupervisorProfile[]>([]);
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState<number | null>(null);
    const [history, setHistory] = useState<VehicleAssignment[]>([]);
    const [seleccion, setSeleccion] = useState<Record<number, string>>({});

    const cargar = useCallback(async () => {
        setLoading(true);
        try {
            const [sups, vehs] = await Promise.all([fetchSupervisors(), fetchVehicles()]);
            setSupervisors(sups);
            setVehicles(vehs);
            setError(null);
        } catch {
            setError('Supervisors could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        cargar();
    }, [cargar]);

    const verHistorial = async (supervisor: SupervisorProfile) => {
        if (expanded === supervisor.id) {
            setExpanded(null);
            return;
        }
        try {
            setHistory(await fetchAssignmentHistory(supervisor.id));
            setExpanded(supervisor.id);
        } catch {
            setError('The assignment history could not be loaded.');
        }
    };

    const asignar = async (supervisor: SupervisorProfile) => {
        const vehicleId = seleccion[supervisor.id];
        if (!vehicleId) return;

        setError(null);
        try {
            await assignVehicle(supervisor.id, Number(vehicleId));
            setSeleccion({ ...seleccion, [supervisor.id]: '' });
            await cargar();
            if (expanded === supervisor.id) {
                setHistory(await fetchAssignmentHistory(supervisor.id));
            }
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The vehicle could not be assigned.');
        }
    };

    const terminar = async (assignmentId: number, supervisorId: number) => {
        setError(null);
        try {
            await endAssignment(assignmentId);
            await cargar();
            setHistory(await fetchAssignmentHistory(supervisorId));
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The assignment could not be ended.');
        }
    };

    if (loading) {
        return <p className="text-sm text-muted-foreground">Loading…</p>;
    }

    return (
        <div className="flex flex-col gap-4" data-testid="SupervisorAssignmentsPanel">
            {error && <p className="text-sm text-destructive">{error}</p>}

            {supervisors.length === 0 ? (
                <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
                    No Route supervisors yet. A user of this company becomes a
                    supervisor from the Users screen once the Supervisor role is
                    assigned.
                </p>
            ) : (
                <div className="rounded-lg border border-border bg-card">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Supervisor</TableHead>
                                <TableHead>Current vehicle</TableHead>
                                <TableHead>Assign</TableHead>
                                <TableHead className="text-right">History</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {supervisors.map((supervisor) => (
                                <TableRow key={supervisor.id}>
                                    <TableCell>
                                        <span className="font-medium">
                                            {supervisor.first_name}
                                            {' '}
                                            {supervisor.last_name}
                                        </span>
                                        <span className="block text-xs text-muted-foreground">
                                            {supervisor.email}
                                        </span>
                                    </TableCell>
                                    <TableCell>
                                        {supervisor.current_vehicle ? (
                                            <Badge>{supervisor.current_vehicle.unit}</Badge>
                                        ) : (
                                            <span className="text-sm text-muted-foreground">
                                                None
                                            </span>
                                        )}
                                    </TableCell>
                                    <TableCell>
                                        <div className="flex items-center gap-2">
                                            <Select
                                                value={seleccion[supervisor.id] ?? ''}
                                                onValueChange={(v) => setSeleccion({
                                                    ...seleccion, [supervisor.id]: v,
                                                })}
                                            >
                                                <SelectTrigger className="w-40">
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
                                                disabled={!seleccion[supervisor.id]}
                                                onClick={() => asignar(supervisor)}
                                            >
                                                Assign
                                            </Button>
                                        </div>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => verHistorial(supervisor)}
                                        >
                                            {expanded === supervisor.id ? 'Hide' : 'Show'}
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}

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
        </div>
    );
}
