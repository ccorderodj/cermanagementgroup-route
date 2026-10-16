import {
    useCallback, useEffect, useState, type ReactNode,
} from 'react';
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
import type { Paginated } from '@/shared/api';
import {
    fetchActivityEmailRecipients,
    fetchStrategicRecipients,
    updateActivityEmailRecipient,
    updateStrategicRecipient,
    type ActivityEmailRecipient,
    type StrategicRecipient,
} from '@/entities/RouteActivityEmails';
import { readServerProblem } from '../lib/errors';
import { ToggleSwitch } from './ToggleSwitch';

const PAGE_SIZE = 20;

/** Lo común de una fila: persona, correo de la cuenta, elegibilidad y versión. */
interface Fila {
    user_id: number;
    first_name: string;
    last_name: string;
    email: string;
    role_name: string | null;
    eligible: boolean;
    ineligible_reason: string | null;
    version: number;
}

interface Interruptor<R> {
    campo: keyof R & string;
    corto: string;
    largo: string;
}

interface ListaProps<R extends Fila> {
    titulo: string;
    explicacion: string;
    vacio: string;
    cargar: (p: { page: number; pageSize: number; q?: string }) => Promise<Paginated<R>>;
    /** Guarda **un** interruptor; los demás no se envían y no cambian. */
    guardar: (userId: number, campo: string, valor: boolean, version: number) => Promise<R>;
    interruptores: Interruptor<R>[];
    motivos: Record<string, string>;
    extra?: (row: R) => ReactNode;
}

/**
 * Una lista de destinatarios con sus interruptores.
 *
 * La lista es la del servidor y ya viene acotada a quien mira (un manager, su
 * rama). El correo es el de la cuenta y no se edita aquí. Cada interruptor se
 * guarda solo y los demás no cambian; si la persona no es elegible, quedan
 * bloqueados y se dice por qué.
 */
function ListaDeDestinatarios<R extends Fila>(props: ListaProps<R>) {
    const {
        titulo, explicacion, vacio, cargar, guardar, interruptores, motivos, extra,
    } = props;
    const [rows, setRows] = useState<R[]>([]);
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
            const data = await cargar({ page, pageSize: PAGE_SIZE, q: query });
            setRows(data.results);
            setTotal(data.count);
        } catch {
            setError('The recipients could not be loaded.');
        } finally {
            setLoading(false);
        }
    }, [cargar, page, query]);

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

    const toggle = async (row: R, campo: string, valor: boolean) => {
        setSaving(`${row.user_id}-${campo}`);
        setRowError((prev) => ({ ...prev, [row.user_id]: '' }));
        try {
            const actualizado = await guardar(row.user_id, campo, valor, row.version);
            setRows((prev) => prev.map((r) => (r.user_id === row.user_id ? actualizado : r)));
        } catch (err) {
            const problema = readServerProblem(err, 'The change could not be saved.');
            setRowError((prev) => ({ ...prev, [row.user_id]: problema.message ?? 'The change could not be saved.' }));
            // Un 409 es que el estado guardado ya no es el que se ve: se recarga
            // para enseñar el real antes de que nadie vuelva a intentarlo.
            if (problema.status === 409) await load();
        } finally {
            setSaving(null);
        }
    };

    const paginas = Math.max(1, Math.ceil(total / PAGE_SIZE));

    const interruptor = (row: R, i: Interruptor<R>) => (
        <ToggleSwitch
            id={`rcp-${row.user_id}-${i.campo}`}
            label={`${i.largo} for ${row.first_name} ${row.last_name}`}
            checked={Boolean(row[i.campo]) && row.eligible}
            disabled={!row.eligible || saving === `${row.user_id}-${i.campo}`}
            onChange={(v) => toggle(row, i.campo, v)}
        />
    );

    const aviso = (row: R) => {
        const texto = rowError[row.user_id] || (row.ineligible_reason ? motivos[row.ineligible_reason] : '');
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
        <section className="space-y-4" aria-label={titulo}>
            <h3 className="text-base font-semibold">{titulo}</h3>
            <p className="rounded-md border bg-muted/40 p-3 text-sm text-muted-foreground">{explicacion}</p>

            <div className="relative max-w-sm">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                <Input
                    aria-label={`Search ${titulo}`}
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
                    {query ? 'No users match this search.' : vacio}
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
                                    {interruptores.map((i) => (
                                        <TableHead key={i.campo} className="w-28 text-center">{i.corto}</TableHead>
                                    ))}
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rows.map((row) => (
                                    <TableRow key={row.user_id}>
                                        <TableCell>
                                            <div className="font-medium">{`${row.first_name} ${row.last_name}`}</div>
                                            <div className="text-xs text-muted-foreground">{row.role_name}</div>
                                            {extra?.(row)}
                                            {aviso(row)}
                                        </TableCell>
                                        <TableCell className="text-sm">{row.email}</TableCell>
                                        {interruptores.map((i) => (
                                            <TableCell key={i.campo} className="text-center">{interruptor(row, i)}</TableCell>
                                        ))}
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </div>

                    <ul className="space-y-3 md:hidden">
                        {rows.map((row) => (
                            <li key={row.user_id} className="space-y-2 rounded-md border p-3">
                                <div>
                                    <div className="font-medium">{`${row.first_name} ${row.last_name}`}</div>
                                    <div className="break-all text-xs text-muted-foreground">{row.email}</div>
                                    {row.role_name && <Badge variant="secondary" className="mt-1">{row.role_name}</Badge>}
                                    {extra?.(row)}
                                </div>
                                {interruptores.map((i) => (
                                    <div key={i.campo} className="flex items-center justify-between gap-2">
                                        <label htmlFor={`rcp-${row.user_id}-${i.campo}`} className="text-sm">{i.corto}</label>
                                        {interruptor(row, i)}
                                    </div>
                                ))}
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
        </section>
    );
}

const MOTIVOS_PERSONA: Record<string, string> = {
    inactive: 'Inactive in this company: cannot receive activity emails.',
    invalid_email: 'No valid email address. Correct it in Users first.',
};

const MOTIVOS_MANDO: Record<string, string> = {
    ...MOTIVOS_PERSONA,
    no_team: 'Nobody currently reports to this manager: there is nothing to report.',
};

const INTERRUPTORES_MOTIVACIONALES: Interruptor<ActivityEmailRecipient>[] = [
    { campo: 'midday_enabled', corto: 'Midday', largo: 'Midday Motivation' },
    { campo: 'end_of_day_enabled', corto: 'End of Day', largo: 'End of Day Recognition' },
];

const INTERRUPTORES_ESTRATEGICOS: Interruptor<StrategicRecipient>[] = [
    { campo: 'strategic_midday_enabled', corto: 'Midday', largo: 'Strategic Midday Report' },
    { campo: 'strategic_end_of_day_enabled', corto: 'End of Day', largo: 'Strategic End-of-Day Report' },
];

const cobertura = (row: StrategicRecipient) => (
    <div className="text-xs text-muted-foreground">
        {`Team in report: ${row.coverage} ${row.coverage === 1 ? 'person' : 'people'}`}
    </div>
);

const guardarMotivacional = (id: number, campo: string, valor: boolean, version: number) => (
    updateActivityEmailRecipient(id, { [campo]: valor, version } as Parameters<typeof updateActivityEmailRecipient>[1])
);

const guardarEstrategico = (id: number, campo: string, valor: boolean, version: number) => (
    updateStrategicRecipient(id, { [campo]: valor, version } as Parameters<typeof updateStrategicRecipient>[1])
);

/** Las dos listas, separadas: activar un reporte no toca los motivacionales. */
export function RecipientsTab() {
    return (
        <div className="space-y-8">
            <ListaDeDestinatarios
                titulo="Motivational Emails"
                explicacion={
                    'Who will be eligible for each motivational email once automatic sending is enabled. '
                    + 'Nothing is sent now. Everyone starts with both emails off, and no email is sent on a day '
                    + 'without completed activities.'
                }
                vacio="There are no users you can manage here."
                cargar={fetchActivityEmailRecipients}
                guardar={guardarMotivacional}
                interruptores={INTERRUPTORES_MOTIVACIONALES}
                motivos={MOTIVOS_PERSONA}
            />
            <ListaDeDestinatarios
                titulo="Strategic Activity Reports"
                explicacion={
                    'Managers (CEO, COO, Regional Manager) who will receive the team report once automatic sending '
                    + 'is enabled. The team is the one the hierarchy gives them today; enabling a report grants no '
                    + 'extra access. Nothing is sent now and everyone starts off.'
                }
                vacio="There are no managers you can manage here."
                cargar={fetchStrategicRecipients}
                guardar={guardarEstrategico}
                interruptores={INTERRUPTORES_ESTRATEGICOS}
                motivos={MOTIVOS_MANDO}
                extra={cobertura}
            />
        </div>
    );
}
