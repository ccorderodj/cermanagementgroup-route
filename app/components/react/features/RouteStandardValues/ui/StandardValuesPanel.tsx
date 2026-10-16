import { useCallback, useEffect, useState } from 'react';
import {
    Badge,
    Button,
    Checkbox,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    Input,
    Label,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import { ConfirmDestructiveDialog, LifecycleRowActions } from '@/features/Common';
import {
    createStandardValue,
    deleteStandardValue,
    fetchStandardValueLists,
    fetchStandardValues,
    reorderStandardValues,
    updateStandardValue,
    type StandardValue,
    type StandardValueListSummary,
} from '@/entities/RouteStandardValues';

/**
 * Administración de las ocho listas configurables.
 *
 * Las listas son del producto y no se pueden crear ni borrar desde aquí; lo que
 * el tenant configura son los **valores** de dentro.
 *
 * Tres estados, no dos (RTE02-A01)
 * ---------------------------------
 * * **Desactivar** retira el valor del uso operativo y lo deja aquí, visible al
 *   marcar "Show inactive values", para poder reactivarlo.
 * * **Borrar** lo saca también de esa vista. Es lo que se hace con un valor
 *   creado por error, que antes se quedaba para siempre entre los retirados.
 *
 * En los dos casos la fila sobrevive en el servidor: una actividad de marzo
 * guardó su identificador y tiene que poder resolverlo. Lo que cambia es dónde
 * se ofrece, no si existe.
 *
 * Crear en contexto (A02-FC4)
 * ----------------------------
 * El alta era un campo permanente encima de la tabla. Ocupaba sitio en la
 * pantalla de las ocho listas cuando lo habitual es venir a mirar o a reordenar,
 * y obligaba a recordar cuál estaba seleccionada mientras se escribía.
 *
 * Ahora `Add Value` abre un diálogo que **ya sabe** a qué lista se está
 * añadiendo y lo dice en su cabecera. Al guardar se cierra, se recarga esa lista
 * y su contador, y la selección no se mueve: quien añade tres valores seguidos no
 * vuelve a elegir la lista tres veces.
 */
export function StandardValuesPanel() {
    const [lists, setLists] = useState<StandardValueListSummary[]>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [values, setValues] = useState<StandardValue[]>([]);
    const [includeInactive, setIncludeInactive] = useState(false);
    const [nuevo, setNuevo] = useState('');
    // El diálogo de alta. Sabe a qué lista añade porque `selected` no cambia.
    const [altaAbierta, setAltaAbierta] = useState(false);
    const [editing, setEditing] = useState<StandardValue | null>(null);
    const [editLabel, setEditLabel] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    // El valor cuyo borrado espera confirmación. `null` = diálogo cerrado.
    const [porBorrar, setPorBorrar] = useState<StandardValue | null>(null);
    const [borrando, setBorrando] = useState(false);

    const cargarListas = useCallback(async () => {
        try {
            const data = await fetchStandardValueLists();
            setLists(data);
            setSelected((actual) => actual ?? data[0]?.code ?? null);
        } catch {
            setError('The lists could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, []);

    const cargarValores = useCallback(async () => {
        if (!selected) return;
        try {
            setValues(await fetchStandardValues(selected, includeInactive));
            setError(null);
        } catch {
            setError('The values could not be loaded.');
        }
    }, [selected, includeInactive]);

    useEffect(() => {
        cargarListas();
    }, [cargarListas]);

    useEffect(() => {
        cargarValores();
    }, [cargarValores]);

    const anadir = async () => {
        if (!selected || !nuevo.trim()) return;
        setError(null);
        try {
            await createStandardValue(selected, nuevo.trim());
            setNuevo('');
            setAltaAbierta(false);
            // Los dos: la tabla de la lista y el contador del grupo. La selección
            // se queda donde estaba.
            await Promise.all([cargarValores(), cargarListas()]);
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The value could not be added.');
        }
    };

    const empezarEdicion = (valor: StandardValue) => {
        setEditing(valor);
        setEditLabel(valor.label);
    };

    /** Guarda la etiqueta editada. `version` viaja para el control de concurrencia. */
    const guardarEdicion = async () => {
        if (!editing || !editLabel.trim()) return;
        setError(null);
        try {
            await updateStandardValue(editing.id, {
                label: editLabel.trim(),
                version: editing.version,
            });
            setEditing(null);
            setEditLabel('');
            await cargarValores();
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The value could not be renamed.');
        }
    };

    const alternarEstado = async (valor: StandardValue) => {
        setError(null);
        try {
            await updateStandardValue(valor.id, {
                is_active: !valor.is_active,
                version: valor.version,
            });
            await Promise.all([cargarValores(), cargarListas()]);
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The value status could not be changed.');
        }
    };

    /** Confirma el borrado. El servidor es quien decide si se puede. */
    const confirmarBorrado = async () => {
        if (!porBorrar) return;
        setError(null);
        setBorrando(true);
        try {
            await deleteStandardValue(porBorrar.id, porBorrar.version);
            setPorBorrar(null);
            await Promise.all([cargarValores(), cargarListas()]);
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The value could not be deleted.');
            setPorBorrar(null);
        } finally {
            setBorrando(false);
        }
    };

    /** Mueve un valor una posición y reenvía el orden completo de la lista. */
    const mover = async (indice: number, direccion: -1 | 1) => {
        const destino = indice + direccion;
        if (!selected || destino < 0 || destino >= values.length) return;

        const orden = values.map((v) => v.id);
        [orden[indice], orden[destino]] = [orden[destino], orden[indice]];

        setError(null);
        try {
            // El servidor exige el conjunto exacto de la lista, así que se
            // reenvía completo aunque sólo cambien dos posiciones.
            const todos = includeInactive
                ? orden
                : (await fetchStandardValues(selected, true))
                    .map((v) => v.id)
                    .sort((a, b) => {
                        const ia = orden.indexOf(a);
                        const ib = orden.indexOf(b);
                        return (ia === -1 ? Number.MAX_SAFE_INTEGER : ia)
                            - (ib === -1 ? Number.MAX_SAFE_INTEGER : ib);
                    });

            await reorderStandardValues(selected, todos);
            await cargarValores();
        } catch (err) {
            const detalle = (err as { response?: { data?: { detail?: string } } })
                ?.response?.data?.detail;
            setError(detalle ?? 'The list could not be reordered.');
        }
    };

    if (loading) {
        return <p className="text-sm text-muted-foreground">Loading…</p>;
    }

    return (
        <div className="flex flex-col gap-6 lg:flex-row" data-testid="StandardValuesPanel">
            <nav
                className="flex shrink-0 flex-col gap-1 self-start rounded-lg border border-border bg-card p-2 lg:w-64"
                aria-label="Value lists"
            >
                {lists.map((list) => (
                    <button
                        key={list.code}
                        type="button"
                        onClick={() => setSelected(list.code)}
                        className={[
                            'flex items-center justify-between rounded-md px-3 py-2 text-left text-sm',
                            list.code === selected
                                ? 'bg-primary/10 font-medium text-primary'
                                : 'text-muted-foreground hover:bg-muted',
                        ].join(' ')}
                    >
                        {list.label}
                        <Badge variant="secondary">{list.active_values}</Badge>
                    </button>
                ))}
            </nav>

            <div className="flex flex-1 flex-col gap-4">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    <div className="flex items-center gap-2">
                        <Checkbox
                            id="show-retired"
                            checked={includeInactive}
                            onCheckedChange={(v) => setIncludeInactive(v === true)}
                        />
                        <Label
                            htmlFor="show-retired"
                            className="text-sm text-muted-foreground"
                        >
                            Show inactive values
                        </Label>
                    </div>
                    <Button
                        disabled={!selected}
                        onClick={() => { setNuevo(''); setError(null); setAltaAbierta(true); }}
                    >
                        Add Value
                    </Button>
                </div>

                {error && !altaAbierta && (
                    <p className="text-sm text-destructive">{error}</p>
                )}

                <Dialog
                    open={altaAbierta}
                    onOpenChange={(abierto) => {
                        setAltaAbierta(abierto);
                        if (!abierto) { setNuevo(''); setError(null); }
                    }}
                >
                    <DialogContent className="sm:max-w-[520px]">
                        <DialogHeader>
                            {/* La lista seleccionada, en la cabecera: el diálogo ya
                                sabe dónde añade y no lo vuelve a preguntar. */}
                            <DialogTitle>
                                Add value to
                                {' '}
                                {lists.find((l) => l.code === selected)?.label ?? ''}
                            </DialogTitle>
                            <DialogDescription>
                                It becomes selectable for supervisors as soon as you
                                save it.
                            </DialogDescription>
                        </DialogHeader>

                        <div className="flex flex-col gap-1.5">
                            <Label htmlFor="new-value">Label</Label>
                            <Input
                                id="new-value"
                                value={nuevo}
                                onChange={(e) => setNuevo(e.target.value)}
                                placeholder="New value"
                            />
                        </div>

                        {error && <p className="text-sm text-destructive">{error}</p>}

                        <DialogFooter>
                            <Button
                                variant="outline"
                                onClick={() => setAltaAbierta(false)}
                            >
                                Cancel
                            </Button>
                            <Button onClick={anadir} disabled={!nuevo.trim()}>
                                Add
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>

                <section className="rounded-lg border border-border bg-card">
                    {values.length === 0 ? (
                        <p className="p-4 text-sm text-muted-foreground">
                            This list has no values yet.
                        </p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-28">Order</TableHead>
                                    <TableHead>Label</TableHead>
                                    <TableHead>Status</TableHead>
                                    {/* Sin cabecera: la columna sólo lleva el menú
                                        contextual de la fila, y titularla
                                        "Actions" nombra un control que ya se
                                        explica solo. */}
                                    <TableHead className="w-12" />
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {values.map((valor, indice) => (
                                    <TableRow key={valor.id}>
                                        <TableCell>
                                            {/* Las flechas viven **con** el orden,
                                                no junto al menú de ciclo de vida:
                                                mover una fila es posición, no una
                                                decisión sobre el valor. */}
                                            <div className="flex items-center gap-1">
                                                <span className="w-4 text-muted-foreground">
                                                    {valor.sort_order}
                                                </span>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-7 w-7 p-0"
                                                    disabled={indice === 0}
                                                    onClick={() => mover(indice, -1)}
                                                    aria-label={`Move ${valor.label} up`}
                                                >
                                                    ↑
                                                </Button>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    className="h-7 w-7 p-0"
                                                    disabled={indice === values.length - 1}
                                                    onClick={() => mover(indice, 1)}
                                                    aria-label={`Move ${valor.label} down`}
                                                >
                                                    ↓
                                                </Button>
                                            </div>
                                        </TableCell>
                                        <TableCell className="font-medium">
                                            {editing?.id === valor.id ? (
                                                <div className="flex gap-2">
                                                    <Input
                                                        value={editLabel}
                                                        onChange={(e) => setEditLabel(
                                                            e.target.value,
                                                        )}
                                                        aria-label={`Rename ${valor.label}`}
                                                    />
                                                    <Button
                                                        size="sm"
                                                        disabled={!editLabel.trim()}
                                                        onClick={guardarEdicion}
                                                    >
                                                        Save
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        onClick={() => setEditing(null)}
                                                    >
                                                        Cancel
                                                    </Button>
                                                </div>
                                            ) : (
                                                valor.label
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <Badge
                                                variant={valor.is_active ? 'default' : 'secondary'}
                                            >
                                                {valor.is_active ? 'Active' : 'Inactive'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <LifecycleRowActions
                                                isActive={valor.is_active}
                                                onEdit={() => empezarEdicion(valor)}
                                                onDeactivate={() => alternarEstado(valor)}
                                                onReactivate={() => alternarEstado(valor)}
                                                onDelete={() => setPorBorrar(valor)}
                                            />
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </section>
            </div>

            <ConfirmDestructiveDialog
                open={porBorrar !== null}
                onOpenChange={(abierto) => !abierto && setPorBorrar(null)}
                title={`Delete ${porBorrar?.label ?? ''}?`}
                description={(
                    <>
                        It will no longer appear in this list or in operational
                        forms, not even when showing inactive values. Past records
                        that used it stay readable.
                        {' '}
                        To take it out of use but keep it here, deactivate it instead.
                    </>
                )}
                busy={borrando}
                onConfirm={confirmarBorrado}
            />
        </div>
    );
}
