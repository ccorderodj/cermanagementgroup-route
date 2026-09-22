import { CheckCircle2, TriangleAlert } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/shadcn/new-york';
import type { PostureItem } from '@/entities/PlatformSettings';

interface SecurityPosturePanelProps {
    posture: PostureItem[];
    mode?: string;
}

/**
 * La seguridad que el despliegue tiene, de sólo lectura (S3).
 *
 * Se cambia en el entorno del despliegue, no aquí: son las opciones con las que
 * arranca el proceso. Lo marcado es lo que **en producción** estaría mal; en
 * desarrollo es normal verlo.
 */
export const SecurityPosturePanel = ({ posture, mode }: SecurityPosturePanelProps) => (
    <Card id="security-posture" data-testid="security-posture">
        <CardHeader className="pb-3">
            <CardTitle className="text-base">Security posture</CardTitle>
            <CardDescription>
                Set in the deployment environment and read when the application starts.
                {mode && mode !== 'PROD'
                    ? ` Items marked below are expected in ${mode}; each must be resolved before production.`
                    : ' Items marked below must be resolved.'}
            </CardDescription>
        </CardHeader>
        <CardContent>
            <ul className="divide-y divide-border">
                {posture.map((item) => (
                    <li
                        key={item.key}
                        data-testid={`posture-${item.key}`}
                        data-ok={item.ok}
                        className="grid gap-1 py-3 sm:grid-cols-[minmax(10rem,14rem)_1fr] sm:gap-4"
                    >
                        <div className="flex items-start gap-2">
                            {item.ok ? (
                                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-green-600" aria-label="Production-grade" />
                            ) : (
                                <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-label="Not production-grade" />
                            )}
                            <span className="text-sm font-medium">{item.title}</span>
                        </div>
                        <div className="min-w-0">
                            <p className="break-words font-mono text-sm">{item.value}</p>
                            <p className="text-xs text-muted-foreground">{item.detail}</p>
                        </div>
                    </li>
                ))}
            </ul>
        </CardContent>
    </Card>
);
