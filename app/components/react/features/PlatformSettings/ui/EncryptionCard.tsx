import { KeyRound } from 'lucide-react';
import {
    Badge,
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/shared/ui/shadcn/new-york';
import type { Gate, PostureItem } from '@/entities/PlatformSettings';
import { gateStatus } from '../lib/presentation';

interface EncryptionCardProps {
    masterKey?: PostureItem;
    gate?: Gate;
}

const Command = ({ children }: { children: string }) => (
    <code className="block overflow-x-auto whitespace-pre rounded-md bg-muted px-3 py-2 font-mono text-xs">
        {children}
    </code>
);

/**
 * La llave que cifra las credenciales guardadas desde Settings (D12-01).
 *
 * No se configura aquí, y a propósito: si la llave viviera en la misma base que
 * las credenciales, un volcado entregaría las dos juntas. Esta tarjeta explica
 * dónde va y enseña su huella, nunca su valor.
 */
export const EncryptionCard = ({ masterKey, gate }: EncryptionCardProps) => {
    const estado = gate ? gateStatus(gate.status) : null;
    return (
        <Card id="encryption" data-testid="encryption-card" className="scroll-mt-20">
            <CardHeader className="pb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <KeyRound className="size-4" aria-hidden="true" />
                        Encryption & secrets
                    </CardTitle>
                    {estado && <Badge variant={estado.tone}>{estado.label}</Badge>}
                </div>
                <CardDescription>
                    Credentials entered in Settings are encrypted with AES-256-GCM before they reach the
                    database. The key that encrypts them lives only in the deployment environment.
                </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4 text-sm">
                <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[8rem_1fr]">
                    <dt className="text-muted-foreground">Master key</dt>
                    <dd className="font-mono">{masterKey?.value ?? 'unknown'}</dd>
                    {gate && (
                        <>
                            <dt className="text-muted-foreground">Last check</dt>
                            <dd>{gate.detail}</dd>
                        </>
                    )}
                </dl>

                <ol className="flex list-decimal flex-col gap-3 pl-5">
                    <li className="pl-1">
                        <p>Generate a key once, on a trusted machine:</p>
                        <Command>python -m app.core.platform.secrets generate</Command>
                    </li>
                    <li className="pl-1">
                        Set it as the
                        {' '}
                        <code className="font-mono text-xs">PLATFORM_MASTER_KEY</code>
                        {' '}
                        environment variable of every application instance. On DigitalOcean App Platform, mark
                        the variable as encrypted.
                    </li>
                    <li className="pl-1">
                        Keep an offline copy with CER’s records. Without it, stored credentials cannot be
                        recovered and must be entered again.
                    </li>
                    <li className="pl-1">
                        <p>
                            To rotate: move the current key to
                            {' '}
                            <code className="font-mono text-xs">PLATFORM_MASTER_KEY_PREVIOUS</code>
                            , set the new one as
                            {' '}
                            <code className="font-mono text-xs">PLATFORM_MASTER_KEY</code>
                            , run the command below, then remove the previous key.
                        </p>
                        <Command>python -m app.core.platform.rotate_master_key</Command>
                    </li>
                </ol>

                <p className="text-xs text-muted-foreground">
                    Field-level encryption of SSN and bank data is a separate decision for CER (OD-07). The
                    managed database already encrypts its disks.
                </p>
            </CardContent>
        </Card>
    );
};
