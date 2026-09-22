/**
 * Cómo se enseña cada estado. **Una sola vez, para Settings y Diagnostics.**
 *
 * Cada mapa tiene respaldo (S9): si el servidor añade un estado que esta versión
 * no conoce, la pantalla enseña su nombre en una insignia neutra en vez de
 * romperse o, peor, de pintarlo en verde.
 */

export type Tone = 'default' | 'secondary' | 'destructive' | 'outline' | 'success';

export interface Presentation {
    label: string;
    tone: Tone;
}

function conRespaldo(mapa: Record<string, Presentation>) {
    return (estado: string | null | undefined): Presentation => (
        (estado && mapa[estado]) || { label: estado ? estado.replace(/_/g, ' ') : 'Unknown', tone: 'outline' }
    );
}

export const integrationStatus = conRespaldo({
    verified: { label: 'Verified', tone: 'success' },
    configured: { label: 'Not verified', tone: 'secondary' },
    failing: { label: 'Failing', tone: 'destructive' },
    incomplete: { label: 'Incomplete', tone: 'outline' },
    master_key_missing: { label: 'Credentials unreadable', tone: 'destructive' },
    not_configured: { label: 'Not configured', tone: 'outline' },
    disabled: { label: 'Disabled', tone: 'secondary' },
    unavailable: { label: 'Not available yet', tone: 'secondary' },
});

export const gateStatus = conRespaldo({
    closed: { label: 'Closed', tone: 'success' },
    open: { label: 'Open', tone: 'destructive' },
    waiting_cer: { label: 'Waiting for CER', tone: 'secondary' },
});

export const checkStatus = conRespaldo({
    healthy: { label: 'Healthy', tone: 'success' },
    degraded: { label: 'Degraded', tone: 'destructive' },
    auth_failed: { label: 'Authentication failed', tone: 'destructive' },
    unreachable: { label: 'Unreachable', tone: 'destructive' },
    not_applicable: { label: 'Not configured', tone: 'secondary' },
    unknown: { label: 'Never checked', tone: 'outline' },
});

export const checkTrigger = conRespaldo({
    manual: { label: 'Manual', tone: 'outline' },
    scheduled: { label: 'Scheduled', tone: 'outline' },
    verify: { label: 'Verify', tone: 'outline' },
});

/** El tipo de credencial: lo que la guía enseña junto a cada campo. */
export const FIELD_KIND: Record<string, { label: string; hint: string }> = {
    public_identifier: {
        label: 'Public identifier',
        hint: 'Identifies the account. Not secret, but not something to publish either.',
    },
    secret: {
        label: 'Secret',
        hint: 'Encrypted before it is stored. It can be replaced, never read back.',
    },
    endpoint: { label: 'Endpoint', hint: 'An address the server connects to.' },
    mailbox: { label: 'Mailbox', hint: 'An email address that must exist in your mail system.' },
    choice: { label: 'Choice', hint: 'One of a fixed set of values.' },
    policy: { label: 'Policy', hint: 'A limit or behaviour you decide.' },
    preset: { label: 'Preset', hint: 'Filled in for you; change it only if your provider says so.' },
};

export function fieldKind(kind: string) {
    return FIELD_KIND[kind] ?? { label: kind.replace(/_/g, ' '), hint: '' };
}

export const CHECK_KIND: Record<string, string> = {
    infrastructure: 'Infrastructure',
    integration: 'Integrations',
    integrity: 'Evidence integrity',
    platform: 'Platform',
};

/** Fecha legible, o un guion. Nunca «Invalid Date». */
export function when(iso: string | null | undefined): string {
    if (!iso) return '—';
    const fecha = new Date(iso);
    return Number.isNaN(fecha.getTime()) ? '—' : fecha.toLocaleString();
}

/** Una expresión del servidor, si el navegador la entiende. Si no, la valida
 *  sólo el servidor: mejor eso que rechazar aquí un valor correcto. */
export function compilePattern(pattern: string | null | undefined): RegExp | null {
    if (!pattern) return null;
    try {
        return new RegExp(pattern);
    } catch {
        return null;
    }
}
