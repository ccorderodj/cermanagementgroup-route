import { cn } from '@/shared/lib/utils/utils';

interface ToggleSwitchProps {
    id: string;
    checked: boolean;
    disabled?: boolean;
    label: string;
    onChange: (checked: boolean) => void;
}

/**
 * Interruptor accesible (`role="switch"`): se activa con el teclado, enseña el
 * foco y anuncia su nombre y su estado. Los colores salen de los tokens.
 */
export function ToggleSwitch({ id, checked, disabled, label, onChange }: ToggleSwitchProps) {
    return (
        <button
            id={id}
            type="button"
            role="switch"
            aria-checked={checked}
            aria-label={label}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            className={cn(
                'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border-2 border-transparent transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                'disabled:cursor-not-allowed disabled:opacity-50',
                checked ? 'bg-primary' : 'bg-input',
            )}
        >
            <span
                aria-hidden="true"
                className={cn(
                    'pointer-events-none block size-5 rounded-full bg-background shadow transition-transform',
                    checked ? 'translate-x-5' : 'translate-x-0',
                )}
            />
        </button>
    );
}
