import * as React from 'react';
import type { Row } from '@tanstack/react-table';
import { Check, Loader2, X } from 'lucide-react';
import {
    Button,
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    approveRolePermissionRequest,
    rejectRolePermissionRequest,
    type RolePermissionChangeRequestEntity,
} from '@/entities/RolePermissionChangeRequests';

interface ReviewRowActionsProps<TData> {
    row: Row<TData>;
    onReviewed: () => void;
    onError: (message: string) => void;
}

/**
 * Aprobar o rechazar una solicitud.
 *
 * El backend decide quién puede hacerlo (rol de gestión, y nunca el
 * solicitante) y lo devuelve en `can_review` / `cannot_review_reason`. Aquí
 * solo se refleja: si no se puede, se explica por qué en vez de esconder el
 * control sin más.
 */
export function ReviewRowActions<TData>({ row, onReviewed, onError }: ReviewRowActionsProps<TData>) {
    const dispatch = useAppDispatch();
    const request = row.original as RolePermissionChangeRequestEntity;
    const [isBusy, setBusy] = React.useState(false);

    if (request.status !== 'pending') {
        return null;
    }

    if (!request.can_review) {
        return (
            <Tooltip>
                <TooltipTrigger asChild>
                    <span className="cursor-default text-xs text-muted-foreground">
                        Cannot review
                    </span>
                </TooltipTrigger>
                <TooltipContent>
                    {request.cannot_review_reason || 'You cannot review this request'}
                </TooltipContent>
            </Tooltip>
        );
    }

    const run = async (action: 'approve' | 'reject') => {
        setBusy(true);
        try {
            const thunk = action === 'approve'
                ? approveRolePermissionRequest({ requestId: request.id })
                : rejectRolePermissionRequest({ requestId: request.id });
            await dispatch(thunk).unwrap();
            onReviewed();
        } catch (e) {
            onError(typeof e === 'string' ? e : `Could not ${action} the request`);
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex items-center justify-end gap-1.5">
            <Button
                size="sm"
                variant="outline"
                disabled={isBusy}
                onClick={() => run('reject')}
                className="h-8 text-destructive hover:bg-destructive/10 hover:text-destructive"
            >
                <X className="mr-1 size-3.5" />
                Reject
            </Button>
            <Button size="sm" disabled={isBusy} onClick={() => run('approve')} className="h-8">
                {isBusy ? <Loader2 className="mr-1 size-3.5 animate-spin" /> : <Check className="mr-1 size-3.5" />}
                Approve
            </Button>
        </div>
    );
}
