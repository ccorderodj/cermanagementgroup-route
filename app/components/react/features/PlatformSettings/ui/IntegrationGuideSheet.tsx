import { useEffect, useMemo, useState } from 'react';
import { ExternalLink, KeyRound, Loader2, ShieldCheck, TriangleAlert } from 'lucide-react';
import { z } from 'zod';
import {
    Badge,
    Button,
    Input,
    Label,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/shared/ui/shadcn/new-york';
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/shadcn/new-york/Alert/Alert';
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from '@/shared/ui/shadcn/new-york/Sheet/Sheet';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import {
    clearIntegrationSecret,
    saveIntegration,
    sendTestEmail,
    setIntegrationSecret,
    verifyIntegration,
    type CheckRun,
    type Integration,
    type Provider,
    type ProviderField,
} from '@/entities/PlatformSettings';
import { checkStatus, compilePattern, fieldKind, integrationStatus, when } from '../lib/presentation';

/** Una guía es una secuencia de verdad: sin proveedor no hay credenciales que
 *  conseguir, y sin credenciales no hay nada que verificar. */
const STEPS = ['Provider', 'Get credentials', 'Enter credentials', 'Verify'] as const;

const STEP_BUTTON = [
    'flex w-full items-center gap-2 rounded-md border px-2.5 py-2 text-left text-xs transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
].join(' ');
const STEP_BUTTON_CURRENT = 'border-primary bg-primary/5 font-semibold text-foreground';
const STEP_BUTTON_OTHER = 'border-border text-muted-foreground hover:bg-accent';
const STEP_NUMBER = 'flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] tabular-nums';

interface IntegrationGuideSheetProps {
    integration: Integration | null;
    initialStep?: number;
    onOpenChange: (open: boolean) => void;
}

function defaultProvider(integration: Integration): Provider | undefined {
    return integration.providers.find((p) => p.key === integration.provider)
        ?? integration.providers.find((p) => p.recommended && p.available)
        ?? integration.providers.find((p) => p.available)
        ?? integration.providers[0];
}

function initialValues(integration: Integration, provider: Provider | undefined): Record<string, string> {
    if (!provider) return {};
    const mismo = integration.provider === provider.key;
    return Object.fromEntries(
        provider.fields
            .filter((f) => f.kind !== 'secret')
            .map((f) => {
                const guardado = mismo ? integration.config[f.name] : undefined;
                const valor = guardado ?? f.default ?? '';
                return [f.name, String(valor)];
            }),
    );
}

/** El esquema del formulario, construido con los mismos campos y expresiones
 *  que valida el servidor. */
function configSchema(fields: ProviderField[]) {
    return z.object(Object.fromEntries(fields.map((f) => {
        const expresion = compilePattern(f.pattern);
        return [f.name, z.string().superRefine((bruto, ctx) => {
            const valor = bruto.trim();
            if (!valor) {
                if (f.required) ctx.addIssue({ code: z.ZodIssueCode.custom, message: `${f.label} is required.` });
                return;
            }
            if (f.choices.length > 0 && !f.choices.includes(valor)) {
                ctx.addIssue({ code: z.ZodIssueCode.custom, message: `Choose one of: ${f.choices.join(', ')}.` });
                return;
            }
            if (expresion && !expresion.test(valor)) {
                ctx.addIssue({
                    code: z.ZodIssueCode.custom,
                    message: `${f.label} does not look like ${f.format || 'a valid value'}.`,
                });
            }
        })];
    })));
}

const FieldMeta = ({ field }: { field: ProviderField }) => {
    const tipo = fieldKind(field.kind);
    return (
        <div className="flex flex-col gap-1 text-xs">
            <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant={field.kind === 'secret' ? 'destructive' : 'outline'} title={tipo.hint}>
                    {tipo.label}
                </Badge>
                {field.required ? (
                    <span className="text-muted-foreground">Required</span>
                ) : (
                    <span className="text-muted-foreground">Optional</span>
                )}
                {field.expires && <span className="text-muted-foreground">· Expires</span>}
            </div>
            <p className="text-muted-foreground">
                <span className="font-medium text-foreground">Where to find it: </span>
                {field.source}
            </p>
            {field.format && (
                <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">Format: </span>
                    {field.format}
                </p>
            )}
        </div>
    );
};

/**
 * La guía de una integración, en cuatro pasos.
 *
 * Todo lo que enseña —qué proveedor, dónde se consigue cada credencial, qué
 * campo la recibe y de qué tipo es— sale de `providers.py` a través de la API.
 * La pantalla no escribe guías: si lo hiciera, acabaría pidiendo un campo que el
 * servidor rechaza.
 *
 * Los secretos son de sólo escritura. Un campo vacío con «Replace» significa que
 * hay uno guardado; nunca se rellena con él.
 */
export const IntegrationGuideSheet = ({ integration, initialStep = 0, onOpenChange }: IntegrationGuideSheetProps) => {
    const dispatch = useAppDispatch();
    const { toast } = useToast();

    const [step, setStep] = useState(initialStep);
    const [providerKey, setProviderKey] = useState<string | undefined>();
    const [values, setValues] = useState<Record<string, string>>({});
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [secretDrafts, setSecretDrafts] = useState<Record<string, { value: string; expiresAt: string }>>({});
    const [busy, setBusy] = useState<string | null>(null);
    const [serverError, setServerError] = useState('');
    const [lastCheck, setLastCheck] = useState<CheckRun | null>(null);
    const [testTo, setTestTo] = useState('');

    // Al abrir otra integración, la guía empieza de cero con lo guardado.
    const abierta = integration?.key;
    useEffect(() => {
        if (!integration) return;
        const proveedor = defaultProvider(integration);
        setStep(initialStep);
        setProviderKey(proveedor?.key);
        setValues(initialValues(integration, proveedor));
        setErrors({});
        setSecretDrafts({});
        setServerError('');
        setLastCheck(null);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [abierta, initialStep]);

    const provider = useMemo(
        () => integration?.providers.find((p) => p.key === providerKey),
        [integration, providerKey],
    );

    if (!integration) return null;

    const estado = integrationStatus(integration.status);
    const configFields = provider?.fields.filter((f) => f.kind !== 'secret') ?? [];
    const secretFields = provider?.fields.filter((f) => f.kind === 'secret') ?? [];
    const guardadoEsEste = integration.provider === provider?.key;
    const cambiaProveedor = Boolean(integration.provider && provider && integration.provider !== provider.key);
    const verificable = ['configured', 'verified', 'failing'].includes(integration.status);

    const chooseProvider = (p: Provider) => {
        if (!p.available) return;
        setProviderKey(p.key);
        setValues(initialValues(integration, p));
        setErrors({});
        setServerError('');
    };

    const saveConfig = async () => {
        if (!provider) return;
        const resultado = configSchema(configFields).safeParse(values);
        if (!resultado.success) {
            setErrors(Object.fromEntries(resultado.error.issues.map((i) => [String(i.path[0]), i.message])));
            return;
        }
        setErrors({});
        setServerError('');
        setBusy('config');
        const config = Object.fromEntries(
            Object.entries(values).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v !== ''),
        );
        const accion = await dispatch(saveIntegration({
            key: integration.key,
            provider: provider.key,
            config,
            enabled: true,
            expectedVersion: integration.version,
        }));
        setBusy(null);
        if (saveIntegration.fulfilled.match(accion)) {
            toast({ title: `${integration.title} saved`, description: 'Verification was reset. Verify again once credentials are set.' });
        } else {
            setServerError(accion.payload ?? 'Could not save the configuration.');
        }
    };

    const saveSecret = async (field: ProviderField) => {
        const borrador = secretDrafts[field.name];
        if (!borrador?.value) {
            setErrors((e) => ({ ...e, [field.name]: `Paste the ${field.label.toLowerCase()} first.` }));
            return;
        }
        setErrors((e) => ({ ...e, [field.name]: '' }));
        setServerError('');
        setBusy(`secret:${field.name}`);
        const accion = await dispatch(setIntegrationSecret({
            key: integration.key,
            name: field.name,
            value: borrador.value,
            expiresAt: borrador.expiresAt || undefined,
        }));
        setBusy(null);
        if (setIntegrationSecret.fulfilled.match(accion)) {
            // El valor sale del navegador en cuanto el servidor lo tiene.
            setSecretDrafts((d) => ({ ...d, [field.name]: { value: '', expiresAt: '' } }));
            toast({ title: `${field.label} stored`, description: 'It is encrypted and cannot be read back.' });
        } else {
            setServerError(accion.payload ?? 'Could not store the credential.');
        }
    };

    const clearSecret = async (field: ProviderField) => {
        setBusy(`clear:${field.name}`);
        setServerError('');
        const accion = await dispatch(clearIntegrationSecret({ key: integration.key, name: field.name }));
        setBusy(null);
        if (clearIntegrationSecret.rejected.match(accion)) {
            setServerError(accion.payload ?? 'Could not remove the credential.');
        }
    };

    const verify = async () => {
        setBusy('verify');
        setServerError('');
        const accion = await dispatch(verifyIntegration(integration.key));
        setBusy(null);
        if (verifyIntegration.fulfilled.match(accion)) {
            setLastCheck(accion.payload.check);
        } else {
            setServerError(accion.payload ?? 'Could not verify.');
        }
    };

    const sendTest = async () => {
        setBusy('test');
        setServerError('');
        const accion = await dispatch(sendTestEmail({ key: integration.key, to: testTo.trim() }));
        setBusy(null);
        if (sendTestEmail.fulfilled.match(accion)) {
            toast({ title: 'Test message sent', description: `Check the inbox of ${accion.payload.to}.` });
        } else {
            setServerError(accion.payload ?? 'The test message was not sent.');
        }
    };

    const secretState = (name: string) => integration.secrets.find((s) => s.name === name);

    return (
        <Sheet open={Boolean(integration)} onOpenChange={onOpenChange}>
            <SheetContent
                side="right"
                className="flex w-full max-w-full flex-col gap-0 overflow-y-auto p-0 sm:max-w-2xl"
                data-testid={`guide-${integration.key}`}
            >
                <SheetHeader className="border-b border-border px-5 py-4 text-left">
                    <div className="flex flex-wrap items-center gap-2 pr-8">
                        <SheetTitle>{integration.title}</SheetTitle>
                        <Badge variant={estado.tone}>{estado.label}</Badge>
                        {integration.open_decision && <Badge variant="outline">{integration.open_decision}</Badge>}
                    </div>
                    <SheetDescription>{integration.summary}</SheetDescription>
                    <nav aria-label="Setup steps" className="mt-3">
                        <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                            {STEPS.map((nombre, indice) => (
                                <li key={nombre}>
                                    <button
                                        type="button"
                                        onClick={() => setStep(indice)}
                                        aria-current={step === indice ? 'step' : undefined}
                                        className={`${STEP_BUTTON} ${step === indice ? STEP_BUTTON_CURRENT : STEP_BUTTON_OTHER}`}
                                    >
                                        <span className={`${STEP_NUMBER} ${step === indice ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
                                            {indice + 1}
                                        </span>
                                        {nombre}
                                    </button>
                                </li>
                            ))}
                        </ol>
                    </nav>
                </SheetHeader>

                <div className="flex flex-1 flex-col gap-4 px-5 py-4">
                    {serverError && (
                        <Alert variant="destructive" data-testid="guide-error">
                            <TriangleAlert className="size-4" />
                            <AlertTitle>That did not work</AlertTitle>
                            <AlertDescription>{serverError}</AlertDescription>
                        </Alert>
                    )}

                    {step === 0 && (
                        <fieldset className="flex flex-col gap-3">
                            <legend className="mb-2 text-sm font-medium">Choose who provides this service</legend>
                            {integration.providers.map((p) => {
                                const elegido = p.key === providerKey;
                                return (
                                    <label
                                        key={p.key}
                                        htmlFor={`provider-${integration.key}-${p.key}`}
                                        className={`flex cursor-pointer gap-3 rounded-md border p-4 ${
                                            elegido ? 'border-primary bg-primary/5' : 'border-border'
                                        } ${p.available ? '' : 'cursor-not-allowed opacity-70'}`}
                                    >
                                        <input
                                            id={`provider-${integration.key}-${p.key}`}
                                            type="radio"
                                            name={`provider-${integration.key}`}
                                            className="mt-1"
                                            checked={elegido}
                                            disabled={!p.available}
                                            onChange={() => chooseProvider(p)}
                                        />
                                        <div className="min-w-0">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <span className="text-sm font-semibold">{p.title}</span>
                                                {p.recommended && <Badge variant="success">Recommended</Badge>}
                                                {!p.available && <Badge variant="secondary">Not available yet</Badge>}
                                                {integration.provider === p.key && <Badge variant="outline">Saved</Badge>}
                                            </div>
                                            <p className="mt-1 text-sm text-muted-foreground">{p.summary}</p>
                                            <p className="mt-1 text-xs text-muted-foreground">
                                                <span className="font-medium text-foreground">Who at CER can get it: </span>
                                                {p.who}
                                            </p>
                                        </div>
                                    </label>
                                );
                            })}
                            {cambiaProveedor && (
                                <Alert>
                                    <TriangleAlert className="size-4" />
                                    <AlertDescription>
                                        Saving a different provider removes the credentials stored for the current one.
                                    </AlertDescription>
                                </Alert>
                            )}
                        </fieldset>
                    )}

                    {step === 1 && provider && (
                        <div className="flex flex-col gap-4">
                            <p className="text-sm">
                                <span className="font-medium">Who at CER can get it: </span>
                                {provider.who}
                            </p>
                            <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm">
                                {provider.steps.map((s) => (
                                    <li key={s.text} className="pl-1">
                                        {s.text}
                                        {s.link && (
                                            <a
                                                href={s.link}
                                                target="_blank"
                                                rel="noreferrer noopener"
                                                className="ml-1 inline-flex items-center gap-0.5 text-primary underline-offset-4 hover:underline"
                                            >
                                                Open
                                                <ExternalLink className="size-3" aria-hidden="true" />
                                            </a>
                                        )}
                                    </li>
                                ))}
                            </ol>
                            {provider.warnings.map((w) => (
                                <Alert key={w}>
                                    <TriangleAlert className="size-4" />
                                    <AlertDescription>{w}</AlertDescription>
                                </Alert>
                            ))}
                            {provider.fields.length > 0 && (
                                <div className="rounded-md border border-border">
                                    <div className="border-b border-border px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                                        What you will enter
                                    </div>
                                    <ul className="divide-y divide-border">
                                        {provider.fields.map((f) => (
                                            <li key={f.name} className="flex flex-col gap-1 px-3 py-2.5">
                                                <span className="text-sm font-medium">{f.label}</span>
                                                <FieldMeta field={f} />
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                            {provider.docs.length > 0 && (
                                <div className="flex flex-col gap-1 text-sm">
                                    <span className="font-medium">Provider documentation</span>
                                    {provider.docs.map((d) => (
                                        <a
                                            key={d.url}
                                            href={d.url}
                                            target="_blank"
                                            rel="noreferrer noopener"
                                            className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                                        >
                                            {d.label}
                                            <ExternalLink className="size-3" aria-hidden="true" />
                                        </a>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {step === 2 && provider && !provider.available && (
                        <Alert>
                            <TriangleAlert className="size-4" />
                            <AlertTitle>Nothing can be entered yet</AlertTitle>
                            <AlertDescription>
                                {provider.title}
                                {' '}
                                cannot be configured until the requirements in step 2 are met. No fields are
                                shown because they would be guesses.
                            </AlertDescription>
                        </Alert>
                    )}

                    {step === 2 && provider?.available && (
                        <div className="flex flex-col gap-6">
                            <section className="flex flex-col gap-4" aria-labelledby="guide-config-title">
                                <h3 id="guide-config-title" className="text-sm font-semibold">Settings</h3>
                                {configFields.map((f) => (
                                    <div key={f.name} className="flex flex-col gap-1.5">
                                        <Label htmlFor={`field-${f.name}`}>{f.label}</Label>
                                        {f.choices.length > 0 ? (
                                            <Select
                                                value={values[f.name] ?? ''}
                                                onValueChange={(v) => setValues((s) => ({ ...s, [f.name]: v }))}
                                            >
                                                <SelectTrigger id={`field-${f.name}`}>
                                                    <SelectValue placeholder="Choose…" />
                                                </SelectTrigger>
                                                <SelectContent>
                                                    {f.choices.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                                                </SelectContent>
                                            </Select>
                                        ) : (
                                            <Input
                                                id={`field-${f.name}`}
                                                value={values[f.name] ?? ''}
                                                placeholder={f.format}
                                                autoComplete="off"
                                                spellCheck={false}
                                                aria-invalid={Boolean(errors[f.name])}
                                                onChange={(e) => setValues((s) => ({ ...s, [f.name]: e.target.value }))}
                                            />
                                        )}
                                        <FieldMeta field={f} />
                                        {errors[f.name] && <p className="text-xs text-destructive">{errors[f.name]}</p>}
                                    </div>
                                ))}
                                <div>
                                    <Button type="button" onClick={saveConfig} disabled={busy !== null} data-testid="guide-save-config">
                                        {busy === 'config' && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
                                        {guardadoEsEste ? 'Save settings' : `Save and use ${provider.title}`}
                                    </Button>
                                </div>
                            </section>

                            {secretFields.length > 0 && (
                                <section className="flex flex-col gap-4" aria-labelledby="guide-secrets-title">
                                    <div>
                                        <h3 id="guide-secrets-title" className="flex items-center gap-2 text-sm font-semibold">
                                            <KeyRound className="size-4" aria-hidden="true" />
                                            Credentials
                                        </h3>
                                        <p className="text-xs text-muted-foreground">
                                            Encrypted before they are stored. They can be replaced but never shown again.
                                        </p>
                                    </div>
                                    {!guardadoEsEste && (
                                        <p className="text-xs text-muted-foreground">Save the settings above first.</p>
                                    )}
                                    {secretFields.map((f) => {
                                        const guardado = secretState(f.name);
                                        const borrador = secretDrafts[f.name] ?? { value: '', expiresAt: '' };
                                        return (
                                            <div key={f.name} className="flex flex-col gap-1.5 rounded-md border border-border p-3">
                                                <div className="flex flex-wrap items-center justify-between gap-2">
                                                    <Label htmlFor={`secret-${f.name}`}>{f.label}</Label>
                                                    {guardado?.present ? (
                                                        <span className="text-xs text-muted-foreground">
                                                            {`Stored ${when(guardado.set_at)}`}
                                                            {guardado.expires_at && ` · expires ${when(guardado.expires_at)}`}
                                                        </span>
                                                    ) : (
                                                        <Badge variant="outline">Not set</Badge>
                                                    )}
                                                </div>
                                                <Input
                                                    id={`secret-${f.name}`}
                                                    type="password"
                                                    autoComplete="new-password"
                                                    spellCheck={false}
                                                    disabled={!guardadoEsEste}
                                                    placeholder={guardado?.present ? 'Paste a new value to replace it' : f.format}
                                                    value={borrador.value}
                                                    onChange={(e) => setSecretDrafts((d) => ({
                                                        ...d, [f.name]: { ...borrador, value: e.target.value },
                                                    }))}
                                                />
                                                {f.expires && (
                                                    <div className="flex flex-col gap-1">
                                                        <Label htmlFor={`secret-exp-${f.name}`} className="text-xs font-normal">
                                                            Expiry date (you will be emailed 30 days before)
                                                        </Label>
                                                        <Input
                                                            id={`secret-exp-${f.name}`}
                                                            type="date"
                                                            className="w-full sm:w-48"
                                                            disabled={!guardadoEsEste}
                                                            value={borrador.expiresAt}
                                                            onChange={(e) => setSecretDrafts((d) => ({
                                                                ...d, [f.name]: { ...borrador, expiresAt: e.target.value },
                                                            }))}
                                                        />
                                                    </div>
                                                )}
                                                <FieldMeta field={f} />
                                                {errors[f.name] && <p className="text-xs text-destructive">{errors[f.name]}</p>}
                                                <div className="flex flex-wrap gap-2 pt-1">
                                                    <Button
                                                        type="button"
                                                        size="sm"
                                                        disabled={!guardadoEsEste || busy !== null}
                                                        onClick={() => saveSecret(f)}
                                                        data-testid={`guide-save-secret-${f.name}`}
                                                    >
                                                        {busy === `secret:${f.name}` && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
                                                        {guardado?.present ? 'Replace' : 'Store'}
                                                    </Button>
                                                    {guardado?.present && (
                                                        <Button
                                                            type="button"
                                                            size="sm"
                                                            variant="outline"
                                                            disabled={busy !== null}
                                                            onClick={() => clearSecret(f)}
                                                        >
                                                            Remove
                                                        </Button>
                                                    )}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </section>
                            )}
                        </div>
                    )}

                    {step === 3 && (
                        <div className="flex flex-col gap-4">
                            <p className="text-sm text-muted-foreground">
                                Verify runs the same check as Diagnostics against the saved configuration. The
                                production gate closes only when it passes.
                            </p>
                            {integration.missing.length > 0 && integration.status !== 'verified' && (
                                <ul className="list-disc pl-5 text-sm text-muted-foreground">
                                    {integration.missing.map((m) => <li key={m}>{m}</li>)}
                                </ul>
                            )}
                            <div>
                                <Button type="button" onClick={verify} disabled={!verificable || busy !== null} data-testid="guide-verify">
                                    {busy === 'verify' ? (
                                        <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
                                    ) : (
                                        <ShieldCheck className="mr-2 size-4" aria-hidden="true" />
                                    )}
                                    {busy === 'verify' ? 'Verifying…' : 'Verify'}
                                </Button>
                            </div>
                            {lastCheck && (
                                <Alert variant={lastCheck.status === 'healthy' ? 'default' : 'destructive'} data-testid="guide-verify-result">
                                    <AlertTitle className="flex items-center gap-2">
                                        <Badge variant={checkStatus(lastCheck.status).tone}>{checkStatus(lastCheck.status).label}</Badge>
                                        {lastCheck.status === 'healthy' ? 'Verified. The gate is closed.' : 'Not verified. The gate stays open.'}
                                    </AlertTitle>
                                    <AlertDescription>{lastCheck.detail}</AlertDescription>
                                </Alert>
                            )}
                            {integration.verified_at && !lastCheck && (
                                <p className="text-sm">{`Last verified ${when(integration.verified_at)}.`}</p>
                            )}

                            {(integration.key === 'email' || integration.key === 'email_fallback') && (
                                <section className="flex flex-col gap-2 rounded-md border border-border p-3" aria-labelledby="guide-test-title">
                                    <h3 id="guide-test-title" className="text-sm font-semibold">Send a test message</h3>
                                    <p className="text-xs text-muted-foreground">
                                        Verify signs in without sending. This sends one real message to the address you choose.
                                    </p>
                                    <div className="flex flex-col gap-2 sm:flex-row">
                                        <Input
                                            type="email"
                                            aria-label="Test recipient"
                                            placeholder="you@cermanagementgroup.com"
                                            value={testTo}
                                            onChange={(e) => setTestTo(e.target.value)}
                                        />
                                        <Button
                                            type="button"
                                            variant="outline"
                                            disabled={!testTo.trim() || !guardadoEsEste || busy !== null}
                                            onClick={sendTest}
                                        >
                                            {busy === 'test' && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
                                            Send
                                        </Button>
                                    </div>
                                </section>
                            )}
                        </div>
                    )}
                </div>

                <div className="sticky bottom-0 flex items-center justify-between gap-2 border-t border-border bg-background px-5 py-3">
                    <Button type="button" variant="ghost" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
                        Back
                    </Button>
                    {step < STEPS.length - 1 ? (
                        <Button type="button" variant="outline" disabled={!provider} onClick={() => setStep((s) => s + 1)}>
                            {`Next: ${STEPS[step + 1]}`}
                        </Button>
                    ) : (
                        <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
                    )}
                </div>
            </SheetContent>
        </Sheet>
    );
};
