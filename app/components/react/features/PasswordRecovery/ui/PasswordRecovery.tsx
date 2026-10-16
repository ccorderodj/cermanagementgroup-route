import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import {
    Button,
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    Input,
} from '@/shared/ui/shadcn/new-york';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch';
import { requestPasswordReset } from '@/entities/users';

const passwordRecoverySchema = z.object({
    email: z.string().email({ message: 'Invalid email address' }),
});

type PasswordRecoveryValues = z.infer<typeof passwordRecoverySchema>;

/**
 * Solicitud de enlace de recuperación.
 *
 * Antes esta pantalla llamaba a `POST /auth/password-reset`, un endpoint que
 * estaba **comentado** en el backend: fallaba siempre con 404 (AUD-FE-003).
 * Ahora apunta al endpoint público reconstruido.
 *
 * **El mensaje de confirmación es siempre el mismo**, se haya emitido el enlace
 * o no. El backend responde igual exista o no la cuenta; mostrar aquí un aviso
 * distinto convertiría el formulario en un comprobador de direcciones y
 * anularía esa precaución.
 */
export function PasswordRecoveryForm() {
    const dispatch = useAppDispatch();
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [sent, setSent] = useState(false);
    const [error, setError] = useState('');

    const form = useForm<PasswordRecoveryValues>({
        resolver: zodResolver(passwordRecoverySchema),
        defaultValues: { email: '' },
    });

    const { handleSubmit, control } = form;

    const onSubmit = async (data: PasswordRecoveryValues) => {
        setIsSubmitting(true);
        setError('');
        try {
            await dispatch(requestPasswordReset({ email: data.email })).unwrap();
            setSent(true);
        } catch (e) {
            // Solo un fallo real de red o de servidor llega aquí: "no existe la
            // cuenta" no es un error, es la respuesta normal.
            setError(typeof e === 'string' ? e : 'Could not send the reset link.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
            <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm">
                <div className="mb-6 text-center">
                    <h1 className="text-2xl font-bold text-foreground">Reset your password</h1>
                    <p className="mt-2 text-sm text-muted-foreground">
                        Enter your email and we will send you a reset link.
                    </p>
                </div>

                {sent ? (
                    <div className="space-y-6 text-center">
                        <p className="text-sm text-muted-foreground">
                            If that address belongs to an account in this workspace,
                            a reset link is on its way. The link expires shortly and
                            can only be used once.
                        </p>
                        <a href="/login" className="inline-block text-sm text-primary hover:underline">
                            ← Back to sign in
                        </a>
                    </div>
                ) : (
                    <Form {...form}>
                        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                            <FormField
                                control={control}
                                name="email"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Email address</FormLabel>
                                        <FormControl>
                                            <Input placeholder="you@example.com" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            {error && <p className="text-sm text-destructive">{error}</p>}

                            <Button type="submit" disabled={isSubmitting} className="w-full">
                                {isSubmitting ? 'Sending…' : 'Send reset link'}
                            </Button>

                            <div className="text-center">
                                <a href="/login" className="text-sm text-primary hover:underline">
                                    ← Back to sign in
                                </a>
                            </div>
                        </form>
                    </Form>
                )}
            </div>
        </div>
    );
}
