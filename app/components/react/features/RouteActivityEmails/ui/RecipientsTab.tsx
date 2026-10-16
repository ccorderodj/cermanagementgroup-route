import { useCallback, useEffect, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import {
    Badge,
    Button,
    Input,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/shared/ui/shadcn/new-york';
import {
    fetchActivityEmailRecipients,
    updateActivityEmailRecipient,
    type ActivityEmailRecipient,
} from '@/entities/RouteActivityEmails';
import { readServerProblem } from '../lib/errors';
import { ToggleSwitch } from './ToggleSwitch';

const PAGE_SIZE = 20;

type Campo = 'midday_enabled' | 'end_of_day_enabled';

const MOTIVO: Record<string, string> = {
    inactive: 'Inactive in this company: cannot receive activity emails.',
    invalid_email: 'No valid email address. Correct it in Users first.',
};

/**
 * Quién es elegible para cada correo.
 *
 * La lista es la del servidor: personas que ejecutan jornada y que quien mira
 * puede gestionar (un manager, sólo su rama). El correo es el de la cuenta y no
 * se edita aquí. Cada interruptor se guarda solo y el otro no cambia; sin
 * correo válido o sin acceso activo, los interruptores quedan bloqueados.
 */
export function RecipientsTab() {
    const [rows, setRows] = useState<ActivityEmailRecipient[]>([]);
    const [total, setTotal] = useState(0);
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState<string | null>(null);
    const [rowError, setRowError] = useState<Record<number, string>>({});

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchActivityEmailRecipients({ page, pageSize: PAGE_SIZE, q: query });
            setRows(data.results);
            setTotal(data.count);
        } catch {
            setError('The recipients could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, [page, query]);

    useEffect(() => {
        load();
    }, [load]);

    useEffect(() => {
        const t = window.setTimeout(() => {
            setPage(1);
            setQuery(search.trim());
        }, 300);
        return () => window.clearTimeout(t);
    }, [search]);

    const toggle = async (row: ActivityEmailRecipient, campo: Campo, valor: boolean) => {
        const clave = `${row.user_id}-${campo}`;
        setSaving(clave);
        setRowError((prev) => ({ ...prev, [row.user_id]: '' }));
        try {
            const actualizado = await updateActivityEmailRecipient(row.user_id, {
                [campo]: valor,
                version: row.version,
            });
            setRows((prev) => prev.map((r) => (r.user_id === row.user_id ? actualizado : r)));
        } catch (err) {
            const problema = readServerProblem(err, 'The change could not be saved.');
            setRowError((prev) => ({
                ...prev,
                [row.user_id]: problema.message ?? 'The change could not be saved.',
            }));
            // Un 409 es que el estado guardado ya no es el que se ve: se recarga
            // para enseñar el real antes de que nadie vuelva a intentarlo.
            if (problema.status === 409) await load();
        } finally {
            setSaving(null);
        }
    };

    const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const interruptor = (row: ActivityEmailRecipient, campo: Campo, etiqueta: string) => (
        <ToggleSwitch
            id={`rcp-${row.user_id}-${campo}`}
            label={`${etiqueta} for ${row.first_name} ${row.last_name}`}
            checked={row[campo] && row.eligible}
            disabled={!row.eligible || saving === `${row.user_id}-${campo}`}
            onChange={(v) => toggle(row, campo, v)}
        />
    );

    const aviso = (row: ActivityEmailRecipient) => {
        const texto = rowError[row.user_id] || (row.ineligible_reason ? MOTIVO[row.ineligible_reason] : '');
        if (!texto) return null;
        const esError = Boolean(rowError[row.user_id]);
        return (
            <p role={esError ? 'alert' : undefined} className={esError ? 'text-xs text-destructive' : 'text-xs text-muted-foreground'}>
                {texto}
                {row.ineligible_reason === 'invalid_email' && !esError && (
                    <>
                        {' '}
                        <a className="text-primary underline" href="/admin/route/users">Open Users</a>
                    </>
                )}
            </p>
        );
    };

    return (
        <div className="space-y-4">
            <p className="rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">
                This page sets who will be eligible for each email once automatic sending is enabled.
                It does not send anything now. Everyone starts with both emails off,
                and no email is sent on a day without completed activities.
            </p>

            <div className="relative max-w-sm">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input
                    aria-label="Search users"
                    placeholder="Search by name, username or email"
                    className="pl-8"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                />
            </div>

            {error && (
                <div role="alert" className="flex items-center gap-3 text-sm text-destructive">
                    {error}
                    <Button type="button" variant="outline" size="sm" onClick={load}>Retry</Button>
                </div>
            )}

            {loading && rows.length === 0 && (
                <div className="flex justify-center py-10">
                    <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
                </div>
            )}
            {!loading && !error && rows.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                    {query ? 'No users match this search.' : 'There are no users you can manage here.'}
                </p>
            )}
            {rows.length > 0 && (
                <>
                    <div className="hidden rounded-md border md:block">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>User</TableHead>
                                    <TableHead>Email</TableHead>
                                    <TableHead className="w-28 text-center">Midday</TableHead>
                                    <TableHead className="w-28 text-center">End of Day</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows.map((row) => (
                                    <TableRow key={row.user_id} data-testid={`recipient-${row.user_id}`}>
                                        <TableCell>
                                            <div className="font-medium">{`${row.first_name} ${row.last_name}`}</div>
                                            <div className="text-xs text-muted-foreground">{row.role_name}</div>
                                            {aviso(row)}
                                        </TableCell>
                                        <TableCell className="text-sm">{row.email}</TableCell>
                                        <TableCell className="text-center">
                                            {interruptor(row, 'midday_enabled', 'Midday Motivation')}
                                        </TableCell>
                                        <TableCell className="text-center">
                                            {interruptor(row, 'end_of_day_enabled', 'End of Day Recognition')}
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>

                    <ul className="space-y-3 md:hidden">
                        {rows.map((row) => (
                            <li key={row.user_id} className="space-y-2 rounded-md border p-3" data-testid={`recipient-card-${row.user_id}`}>
                                <div>
                                    <div className="font-medium">{`${row.first_name} ${row.last_name}`}</div>
                                    <div className="break-all text-xs text-muted-foreground">{row.email}</div>
                                    {row.role_name && <Badge variant="secondary" className="mt-1">{row.role_name}</Badge>}
                                </div>
                                <div className="flex items-center justify-between gap-2">
                                    <label htmlFor={`rcp-${row.user_id}-midday_enabled`} className="text-sm">Midday</label>
                                    {interruptor(row, 'midday_enabled', 'Midday Motivation')}
                                </div>
                                <div className="flex items-center justify-between gap-2">
                                    <label htmlFor={`rcp-${row.user_id}-end_of_day_enabled`} className="text-sm">End of Day</label>
                                    {interruptor(row, 'end_of_day_enabled', 'End of Day Recognition')}
                                </div>
                                {aviso(row)}
                            </li>
                        ))}
                    </ul>

                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                        <span>{`${total} user${total === 1 ? '' : 's'}`}</span>
                        <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                                Previous
                            </Button>
                            <span>{`Page ${page} of ${paginas}`}</span>
                            <Button type="button" variant="outline" size="sm" disabled={page >= paginas || loading} onClick={() => setPage((p) => p + 1)}>
                                Next
                            </Button>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
