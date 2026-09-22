import { useMemo, useState } from 'react';
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
import { confirmPasswordReset } from '@/entities/users';

// El backend exige lo mismo (`MIN_PASSWORD_LENGTH` en users/schemas.py).
const MIN_PASSWORD_LENGTH = 10;

const changePasswordSchema = z
    .object({
        password: z
            .string()
            .min(MIN_PASSWORD_LENGTH, {
                message: `Use at least ${MIN_PASSWORD_LENGTH} characters`,
            }),
        confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
        message: 'The two passwords do not match',
        path: ['confirmPassword'],
    });

type ChangePasswordValues = z.infer<typeof changePasswordSchema>;

/**
 * Canje del enlace de recuperación por una contraseña nueva.
 *
 * El token viaja en la URL (`/change-password?token=…`) y solo sirve una vez:
 * al canjearlo el backend lo borra. Si falta, falló o caducó, el mensaje es el
 * mismo en los tres casos — distinguirlos daría pistas sobre qué tokens existen.
 */
export function ChangePasswordForm() {
    const dispatch = useAppDispatch();
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState('');

    const token = useMemo(
        () => new URLSearchParams(window.location.search).get('token') ?? '',
        [],
    );

    const form = useForm<ChangePasswordValues>({
        resolver: zodResolver(changePasswordSchema),
        defaultValues: { password: '', confirmPassword: '' },
    });

    const { handleSubmit, control } = form;

    const onSubmit = async (data: ChangePasswordValues) => {
        setIsSubmitting(true);
        setError('');
        try {
            await dispatch(
                confirmPasswordReset({ token, password: data.password }),
            ).unwrap();
            setDone(true);
        } catch (e) {
            setError(
                typeof e === 'string'
                    ? e
                    : 'This password reset link is invalid or has expired.',
            );
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center bg-background px-4">
            <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 shadow-sm">
                <div className="mb-6 text-center">
                    <h1 className="text-2xl font-bold text-foreground">Choose a new password</h1>
                    <p className="mt-2 text-sm text-muted-foreground">
                        This link can only be used once.
                    </p>
                </div>

                {done ? (
                    <div className="space-y-6 text-center">
                        <p className="text-sm text-muted-foreground">
                            Your password has been changed. You can sign in with it now.
                        </p>
                        <a
                            href="/login"
                            className="inline-block rounded-lg bg-primary px-6 py-3 text-primary-foreground"
                        >
                            Go to sign in
                        </a>
                    </div>
                ) : (
                    <Form {...form}>
                        <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                            <FormField
                                control={control}
                                name="password"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>New password</FormLabel>
                                        <FormControl>
                                            <Input type="password" autoComplete="new-password" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={control}
                                name="confirmPassword"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Confirm password</FormLabel>
                                        <FormControl>
                                            <Input type="password" autoComplete="new-password" {...field} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            {!token && (
                                <p className="text-sm text-destructive">
                                    This link is missing its token. Request a new one from
                                    the sign-in page.
                                </p>
                            )}

                            {error && <p className="text-sm text-destructive">{error}</p>}

                            <Button
                                type="submit"
                                disabled={isSubmitting || !token}
                                className="w-full"
                            >
                                {isSubmitting ? 'Saving…' : 'Change password'}
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
