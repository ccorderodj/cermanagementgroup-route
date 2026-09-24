import { useCallback, useEffect, useState } from 'react';
import {
    Badge,
    Button,
    Input,
    Checkbox,
    Label,
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
import {
    createVehicle,
    deleteVehicle,
    fetchVehiclesForAdmin,
    setVehicleActive,
    updateVehicle,
    FUEL_GRADES,
    FUEL_GRADE_LABELS,
    type FuelGrade,
    type Vehicle,
} from '@/entities/RouteVehicles';

/**
 * Administración de vehículos.
 *
 * Un vehículo **no se borra**: se retira. Por eso la acción de la fila dice
 * "Retire" y no "Delete", y por eso el listado puede mostrar los retirados —un
 * administrador necesita verlos para reactivarlos, y las jornadas históricas
 * siguen apuntando a ellos.
 *
 * El formulario manda `version` al editar: si otro administrador guardó
 * entretanto, el servidor responde 409 y aquí se enseña el conflicto en vez de
 * pisar su trabajo en silencio.
 */

type FormState = {
    make: string;
    model: string;
    year: string;
    unit: string;
    fuel_grade: FuelGrade;
    operational_mpg: string;
};

const FORM_VACIO: FormState = {
    make: '',
    model: '',
    year: String(new Date().getFullYear()),
    unit: '',
    fuel_grade: 'regular',
    operational_mpg: '',
};

export function VehiclesPanel() {
    const [vehicles, setVehicles] = useState<Vehicle[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [form, setForm] = useState<FormState>(FORM_VACIO);
    const [editing, setEditing] = useState<Vehicle | null>(null);
    const [saving, setSaving] = useState(false);
    const [includeInactive, setIncludeInactive] = useState(false);
    // El vehículo cuyo borrado espera confirmación. `null` = diálogo cerrado.
    const [porBorrar, setPorBorrar] = useState<Vehicle | null>(null);
    const [borrando, setBorrando] = useState(false);
    // Motivo por el que el servidor rechazó el borrado, para explicarlo.
    const [bloqueo, setBloqueo] = useState<string | null>(null);

    const cargar = useCallback(async () => {
        setLoading(true);
        try {
            setVehicles(await fetchVehiclesForAdmin(includeInactive));
            setError(null);
        } catch {
            setError('Vehicles could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, [includeInactive]);

    useEffect(() => {
        cargar();
    }, [cargar]);

    const limpiar = () => { setForm(FORM_VACIO); setEditing(null); };

    const guardar = async () => {
        setSaving(true);
        setError(null);
        try {
            const datos = {
                make: form.make.trim(),
                model: form.model.trim(),
                year: Number(form.year),
                unit: form.unit.trim(),
                fuel_grade: form.fuel_grade,
                operational_mpg: form.operational_mpg,
            };

            if (editing) {
                // `version` viaja para el control de concurrencia.
                await updateVehicle(editing.id, { ...datos, version: editing.version });
            } else {
                await createVehicle(datos);
            }
            limpiar();
            await cargar();
        } catch (err) {
            const estado = (err as { response?: { status?: number } })?.response?.status;
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(
                estado === 409
                    ? detalle ?? 'That vehicle was changed by someone else. Reload and try again.'
                    : detalle ?? 'The vehicle could not be saved.',
            );
        } finally {
            setSaving(false);
        }
    };

    const alternarEstado = async (vehicle: Vehicle) => {
        setError(null);
        try {
            await setVehicleActive(vehicle.id, !vehicle.is_active, vehicle.version);
            await cargar();
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The vehicle status could not be changed.');
        }
    };

    /**
     * Confirma el borrado. Un 409 no es un fallo: es el servidor diciendo que
     * hay una asignación vigente, y su explicación se enseña tal cual en el
     * mismo diálogo en vez de como un error suelto.
     */
    const confirmarBorrado = async () => {
        if (!porBorrar) return;
        setError(null);
        setBorrando(true);
        try {
            await deleteVehicle(porBorrar.id, porBorrar.version);
            setPorBorrar(null);
            await cargar();
        } catch (err) {
            const estado = (err as { response?: { status?: number } })?.response?.status;
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            if (estado === 409) {
                setBloqueo(detalle ?? 'This vehicle cannot be deleted right now.');
            } else {
                setPorBorrar(null);
                setError(detalle ?? 'The vehicle could not be deleted.');
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

    const editar = (vehicle: Vehicle) => {
        setEditing(vehicle);
        setForm({
            make: vehicle.make,
            model: vehicle.model,
            year: String(vehicle.year),
            unit: vehicle.unit,
            fuel_grade: (vehicle.fuel_grade as FuelGrade) ?? 'regular',
            operational_mpg: String(vehicle.operational_mpg),
        });
    };

    const completo = form.make.trim() && form.model.trim() && form.unit.trim()
        && form.operational_mpg.trim() && form.year.trim();

    return (
        <div className="flex flex-col gap-6" data-testid="VehiclesPanel">
            <section className="rounded-lg border border-border bg-card p-4">
                <h3 className="text-sm font-semibold text-foreground">
                    {editing ? `Edit vehicle ${editing.unit}` : 'Add a vehicle'}
                </h3>

                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-unit">Unit</Label>
                        <Input
                            id="vehicle-unit"
                            value={form.unit}
                            placeholder="V-014"
                            onChange={(e) => setForm({ ...form, unit: e.target.value })}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-make">Make</Label>
                        <Input
                            id="vehicle-make"
                            value={form.make}
                            onChange={(e) => setForm({ ...form, make: e.target.value })}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-model">Model</Label>
                        <Input
                            id="vehicle-model"
                            value={form.model}
                            onChange={(e) => setForm({ ...form, model: e.target.value })}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-year">Year</Label>
                        <Input
                            id="vehicle-year"
                            type="number"
                            value={form.year}
                            onChange={(e) => setForm({ ...form, year: e.target.value })}
                        />
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-fuel">Fuel grade</Label>
                        <Select
                            value={form.fuel_grade}
                            onValueChange={(v) => setForm({ ...form, fuel_grade: v as FuelGrade })}
                        >
                            <SelectTrigger id="vehicle-fuel">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {FUEL_GRADES.map((grade) => (
                                    <SelectItem key={grade} value={grade}>
                                        {FUEL_GRADE_LABELS[grade]}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="flex flex-col gap-1.5">
                        <Label htmlFor="vehicle-mpg">Operational MPG</Label>
                        <Input
                            id="vehicle-mpg"
                            type="number"
                            step="0.01"
                            value={form.operational_mpg}
                            placeholder="27.00"
                            onChange={(e) => setForm({ ...form, operational_mpg: e.target.value })}
                        />
                    </div>
                </div>

                <div className="mt-4 flex gap-2">
                    <Button onClick={guardar} disabled={saving || !completo}>
                        {editing ? 'Save changes' : 'Add vehicle'}
                    </Button>
                    {editing && (
                        <Button variant="outline" onClick={limpiar} disabled={saving}>
                            Cancel
                        </Button>
                    )}
                </div>

                {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
            </section>

            <div className="flex items-center gap-2">
                <Checkbox
                    id="show-inactive-vehicles"
                    checked={includeInactive}
                    onCheckedChange={(v) => setIncludeInactive(v === true)}
                />
                <Label
                    htmlFor="show-inactive-vehicles"
                    className="text-sm text-muted-foreground"
                >
                    Show inactive vehicles
                </Label>
            </div>

            <section className="rounded-lg border border-border bg-card">
                {loading && (
                    <p className="p-4 text-sm text-muted-foreground">Loading…</p>
                )}

                {!loading && vehicles.length === 0 && (
                    <p className="p-4 text-sm text-muted-foreground">
                        No vehicles yet. Add the first one above.
                    </p>
                )}

                {!loading && vehicles.length > 0 && (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Unit</TableHead>
                                <TableHead>Vehicle</TableHead>
                                <TableHead>Fuel</TableHead>
                                <TableHead>MPG</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead className="text-right">Actions</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {vehicles.map((vehicle) => (
                                <TableRow key={vehicle.id}>
                                    <TableCell className="font-medium">{vehicle.unit}</TableCell>
                                    <TableCell>
                                        {vehicle.year}
                                        {' '}
                                        {vehicle.make}
                                        {' '}
                                        {vehicle.model}
                                    </TableCell>
                                    <TableCell>
                                        {FUEL_GRADE_LABELS[vehicle.fuel_grade as FuelGrade]
                                            ?? vehicle.fuel_grade}
                                    </TableCell>
                                    <TableCell>{vehicle.operational_mpg}</TableCell>
                                    <TableCell>
                                        <Badge variant={vehicle.is_active ? 'default' : 'secondary'}>
                                            {vehicle.is_active ? 'Active' : 'Inactive'}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-right">
                                        <LifecycleRowActions
                                            isActive={vehicle.is_active}
                                            onEdit={() => editar(vehicle)}
                                            onDeactivate={() => alternarEstado(vehicle)}
                                            onReactivate={() => alternarEstado(vehicle)}
                                            onDelete={() => setPorBorrar(vehicle)}
                                        />
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                )}
            </section>

            <ConfirmDestructiveDialog
                open={porBorrar !== null}
                onOpenChange={cerrarBorrado}
                title={`Delete ${porBorrar?.unit ?? ''}?`}
                description={(
                    <>
                        It will no longer appear in this list or when assigning a
                        vehicle. Past assignments and work sessions that used it stay
                        readable.
                        {' '}
                        To take it out of use but keep it here, deactivate it instead.
                    </>
                )}
                blockedReason={bloqueo}
                busy={borrando}
                onConfirm={confirmarBorrado}
            />
        </div>
    );
}
