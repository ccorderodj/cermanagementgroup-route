import { useCallback, useEffect, useState } from 'react';
import {
    Badge,
    Button,
    Checkbox,
    Input,
    Label,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import {
    createStandardValue,
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
 * el tenant configura son los **valores** de dentro. Un valor retirado sigue
 * existiendo: una actividad de marzo guardó su identificador y tiene que poder
 * resolverlo. Por eso la acción dice "Retire" y el listado puede mostrar lo
 * retirado en vez de esconderlo para siempre.
 */
export function StandardValuesPanel() {
    const [lists, setLists] = useState<StandardValueListSummary[]>([]);
    const [selected, setSelected] = useState<string | null>(null);
    const [values, setValues] = useState<StandardValue[]>([]);
    const [includeInactive, setIncludeInactive] = useState(false);
    const [nuevo, setNuevo] = useState('');
    const [editing, setEditing] = useState<StandardValue | null>(null);
    const [editLabel, setEditLabel] = useState('');
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

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
            <nav className="flex shrink-0 flex-col gap-1 lg:w-64" aria-label="Value lists">
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
                <section className="rounded-lg border border-border bg-card p-4">
                    <Label htmlFor="new-value">Add a value</Label>
                    <div className="mt-1.5 flex gap-2">
                        <Input
                            id="new-value"
                            value={nuevo}
                            onChange={(e) => setNuevo(e.target.value)}
                            placeholder="New value"
                        />
                        <Button onClick={anadir} disabled={!nuevo.trim()}>Add</Button>
                    </div>
                    {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
                </section>

                <div className="flex items-center gap-2">
                    <Checkbox
                        id="show-retired"
                        checked={includeInactive}
                        onCheckedChange={(v) => setIncludeInactive(v === true)}
                    />
                    <Label htmlFor="show-retired" className="text-sm text-muted-foreground">
                        Show retired values
                    </Label>
                </div>

                <section className="rounded-lg border border-border bg-card">
                    {values.length === 0 ? (
                        <p className="p-4 text-sm text-muted-foreground">
                            This list has no values yet.
                        </p>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead className="w-16">Order</TableHead>
                                    <TableHead>Label</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {values.map((valor, indice) => (
                                    <TableRow key={valor.id}>
                                        <TableCell className="text-muted-foreground">
                                            {valor.sort_order}
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
                                                {valor.is_active ? 'Active' : 'Retired'}
                                            </Badge>
                                        </TableCell>
                                        <TableCell className="text-right">
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                disabled={indice === 0}
                                                onClick={() => mover(indice, -1)}
                                                aria-label={`Move ${valor.label} up`}
                                            >
                                                ↑
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                disabled={indice === values.length - 1}
                                                onClick={() => mover(indice, 1)}
                                                aria-label={`Move ${valor.label} down`}
                                            >
                                                ↓
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => empezarEdicion(valor)}
                                            >
                                                Edit
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => alternarEstado(valor)}
                                            >
                                                {valor.is_active ? 'Retire' : 'Restore'}
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </section>
            </div>
        </div>
    );
}
