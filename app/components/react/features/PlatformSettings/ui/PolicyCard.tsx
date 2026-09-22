import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import {
    Badge,
    Button,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    Checkbox,
    Input,
    Label,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { savePolicy, type Policy } from '@/entities/PlatformSettings';

/** Nombre y ayuda de cada ajuste. Lo que no está aquí se enseña con su clave. */
const FIELDS: Record<string, { label: string; hint?: string; unit?: string }> = {
    allowed_types: { label: 'Allowed file types' },
    max_bytes: { label: 'Largest file', unit: 'bytes' },
    max_image_dimension: { label: 'Longest photo side after normalizing', unit: 'px' },
    jpeg_quality: { label: 'JPEG quality', hint: '50–95. Higher keeps more detail and makes larger files.' },
    max_pdf_pages: { label: 'Most pages in a PDF' },
    enabled: { label: 'Run checks on a schedule' },
    interval_minutes: { label: 'Check every', unit: 'minutes' },
};

const FILE_TYPES: { value: string; label: string }[] = [
    { value: 'image/jpeg', label: 'JPEG photo' },
    { value: 'image/png', label: 'PNG image' },
    { value: 'image/heic', label: 'HEIC (iPhone photo)' },
    { value: 'image/heif', label: 'HEIF photo' },
    { value: 'image/webp', label: 'WebP image' },
    { value: 'application/pdf', label: 'PDF document' },
];

/** Ajustes que no se pueden cambiar desde aquí, con el motivo en `hint`. */
/** Campos de política que la pantalla muestra sin permitir editarlos. */
const LOCKED = new Set<string>();

interface PolicyCardProps {
    policy: Policy;
    note?: string;
}

function megabytes(bytes: unknown): string {
    const n = Number(bytes);
    return Number.isFinite(n) ? `${(n / (1024 * 1024)).toFixed(1)} MB` : '';
}

export const PolicyCard = ({ policy, note }: PolicyCardProps) => {
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const [draft, setDraft] = useState<Record<string, unknown>>(policy.value);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        setDraft(policy.value);
    }, [policy.value]);

    const changed = JSON.stringify(draft) !== JSON.stringify(policy.value);

    const save = async () => {
        setSaving(true);
        setError('');
        const accion = await dispatch(savePolicy({ key: policy.key, value: draft, expectedVersion: policy.version }));
        setSaving(false);
        if (savePolicy.fulfilled.match(accion)) {
            toast({ title: `${policy.title} saved` });
        } else {
            setError(accion.payload ?? 'Could not save the policy.');
        }
    };

    return (
        <Card data-testid={`policy-${policy.key}`} className="flex flex-col">
            <CardHeader className="pb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <CardTitle className="text-base">{policy.title}</CardTitle>
                    <Badge variant={policy.customized ? 'secondary' : 'outline'}>
                        {policy.customized ? 'Customized' : 'Defaults'}
                    </Badge>
                </div>
                <CardDescription>{policy.summary}</CardDescription>
                {note && <p className="pt-1 text-xs text-muted-foreground">{note}</p>}
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-4">
                {Object.entries(policy.defaults).map(([name, porDefecto]) => {
                    const meta = FIELDS[name] ?? { label: name.replace(/_/g, ' ') };
                    const id = `policy-${policy.key}-${name}`;
                    const valor = draft[name];

                    if (Array.isArray(porDefecto)) {
                        const elegidos = Array.isArray(valor) ? (valor as string[]) : [];
                        return (
                            <fieldset key={name} className="flex flex-col gap-2">
                                <legend className="mb-1 text-sm font-medium">{meta.label}</legend>
                                <div className="grid gap-2 sm:grid-cols-2">
                                    {FILE_TYPES.map((t) => (
                                        <div key={t.value} className="flex items-center gap-2">
                                            <Checkbox
                                                id={`${id}-${t.value}`}
                                                checked={elegidos.includes(t.value)}
                                                onCheckedChange={(on) => setDraft((d) => ({
                                                    ...d,
                                                    [name]: on
                                                        ? [...elegidos, t.value]
                                                        : elegidos.filter((v) => v !== t.value),
                                                }))}
                                            />
                                            <Label htmlFor={`${id}-${t.value}`} className="text-sm font-normal">{t.label}</Label>
                                        </div>
                                    ))}
                                </div>
                            </fieldset>
                        );
                    }

                    if (typeof porDefecto === 'boolean') {
                        return (
                            <div key={name} className="flex items-start gap-2">
                                <Checkbox
                                    id={id}
                                    className="mt-0.5"
                                    checked={Boolean(valor)}
                                    disabled={LOCKED.has(name)}
                                    onCheckedChange={(on) => setDraft((d) => ({ ...d, [name]: Boolean(on) }))}
                                />
                                <div>
                                    <Label htmlFor={id} className="text-sm font-normal">{meta.label}</Label>
                                    {meta.hint && <p className="text-xs text-muted-foreground">{meta.hint}</p>}
                                </div>
                            </div>
                        );
                    }

                    return (
                        <div key={name} className="flex flex-col gap-1.5">
                            <Label htmlFor={id}>{meta.label}</Label>
                            <div className="flex items-center gap-2">
                                <Input
                                    id={id}
                                    type="number"
                                    inputMode="numeric"
                                    className="w-full tabular-nums sm:w-40"
                                    value={valor === undefined || valor === null ? '' : String(valor)}
                                    onChange={(e) => setDraft((d) => ({
                                        ...d,
                                        [name]: e.target.value === '' ? '' : Number(e.target.value),
                                    }))}
                                />
                                {meta.unit && <span className="text-sm text-muted-foreground">{meta.unit}</span>}
                                {name === 'max_bytes' && <span className="text-sm text-muted-foreground">{`(${megabytes(valor)})`}</span>}
                            </div>
                            {meta.hint && <p className="text-xs text-muted-foreground">{meta.hint}</p>}
                        </div>
                    );
                })}

                {error && <p className="text-sm text-destructive">{error}</p>}

                <div className="mt-auto flex flex-wrap gap-2 pt-1">
                    <Button type="button" size="sm" onClick={save} disabled={!changed || saving}>
                        {saving && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
                        Save
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={saving || JSON.stringify(draft) === JSON.stringify(policy.defaults)}
                        onClick={() => setDraft(policy.defaults)}
                    >
                        Use defaults
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
};
