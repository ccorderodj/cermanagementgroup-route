import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import {
    AlertTriangle,
    Eye,
    EyeOff,
} from 'lucide-react';

import {
    Button,
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    Input,
    ToastAction,
} from '@/shared/ui/shadcn/new-york';

import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch';
import { login } from '@/entities/users';
import { extractErrorMessage } from '@/shared/lib/utils/utils';
import { useApp } from '@/app/providers/StoreProvider';

const loginSchema = z.object({
    email: z
        .string()
        .email({
            message: 'Invalid email address',
        }),

    password: z
        .string()
        .min(6, {
            message: 'Password must be at least 6 characters',
        }),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginForm() {
    const { toast } = useToast();

    const {
        appData,
        companyLogo,
    } = useApp();

    const dispatch = useAppDispatch();

    const [isSubmitting, setIsSubmitting] = useState(false);
    const [showPassword, setShowPassword] = useState(false);

    const [isLogoVisible, setIsLogoVisible] = useState(true);
    const [isHeroLogoVisible, setIsHeroLogoVisible] = useState(true);

    // Banda de entorno de la identidad del proyecto (vacía = no se muestra).
    const environmentLabel = appData?.environment_label || '';
    const isDevMode = environmentLabel !== '';

    const companyName = appData?.company_name || appData?.app_title || 'Company';

    const showLogo = Boolean(companyLogo)
        && isLogoVisible;

    const showHeroLogo = Boolean(companyLogo)
        && isHeroLogoVisible;

    const getCompanyInitials = () => companyName
        .split(' ')
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word.charAt(0).toUpperCase())
        .join('');

    const form = useForm<LoginFormValues>({
        resolver: zodResolver(loginSchema),

        defaultValues: {
            email: '',
            password: '',
        },
    });

    const onSubmit = async (
        data: LoginFormValues,
    ) => {
        setIsSubmitting(true);

        try {
            const result = await dispatch(
                login({
                    email: data.email,
                    password: data.password,
                }),
            );

            if (login.rejected.match(result)) {
                const errorMessage = extractErrorMessage(result, '');

                throw new Error(errorMessage);
            }

            toast({
                title: 'Login successful',
                description: 'Welcome back!',
            });

            window.location.href = appData?.default_path || '/admin';
        } catch (error) {
            const errorMessage = error instanceof Error
                ? error.message
                : String(error);

            toast({
                variant: 'destructive',
                title: 'Login failed',

                description:
                    errorMessage
                    || 'Uh oh! Something went wrong.',

                action: (
                    <ToastAction altText="Try again">
                        Try again
                    </ToastAction>
                ),
            });
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#171e26]">

            {/* DEV MODE TOP MESSAGE */}
            {isDevMode && (
                <div
                    className="
                        fixed
                        left-0
                        top-0
                        z-50
                        flex
                        h-9
                        w-full
                        items-center
                        justify-center
                        gap-2
                        bg-red-600
                        px-4
                        text-xs
                        font-bold
                        uppercase
                        tracking-wider
                        text-white
                        shadow-md
                    "
                >
                    <AlertTriangle className="size-4" />

                    {environmentLabel}

                    <AlertTriangle className="size-4" />
                </div>
            )}

            <div
                className={`
                    grid
                    min-h-screen
                    lg:grid-cols-2
                    ${isDevMode ? 'pt-9' : ''}
                `}
            >
                {/* ===================================== */}
                {/* LEFT SIDE */}
                {/* ===================================== */}

                <section
                    className="
                        flex
                        min-h-screen
                        items-center
                        justify-center
                        bg-[#171e26]
                        px-6
                        py-12
                        lg:min-h-0
                        lg:px-12
                    "
                >
                    <div className="w-full max-w-md">

                        {/* COMPANY LOGO */}
                        <div className="mb-8 flex justify-center">
                            {showLogo ? (
                                <img
                                    src={companyLogo}
                                    alt={`${companyName} logo`}
                                    className="
                max-h-20
                max-w-[240px]
                object-contain
            "
                                    onError={() => setIsLogoVisible(false)}
                                />
                            ) : (
                                <div className="flex flex-col items-center gap-3">
                                    <div
                                        className="
                    flex
                    size-12
                    items-center
                    justify-center
                    rounded-xl
                    bg-cer-cyan
                    text-sm
                    font-bold
                    text-slate-950
                "
                                    >
                                        {getCompanyInitials()}
                                    </div>

                                    <span className="text-lg font-semibold text-white">
                                        {companyName}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* WELCOME */}
                        <div className="mb-8 text-center">
                            <h1
                                className="
                                    text-3xl
                                    font-bold
                                    tracking-tight
                                    text-white
                                "
                            >
                                Welcome back
                            </h1>

                            <p
                                className="
                                    mt-2
                                    text-sm
                                    leading-6
                                    text-slate-400
                                "
                            >
                                Sign in to access your
                                {' '}
                                {companyName}
                                {' '}
                                account.
                            </p>

                            {/* DEV MODE BADGE ONLY */}
                            {isDevMode && (
                                <div className="mt-4">
                                    <span
                                        className="
                                            inline-flex
                                            items-center
                                            gap-2
                                            rounded-full
                                            bg-red-500/15
                                            px-3
                                            py-1
                                            text-[10px]
                                            font-bold
                                            uppercase
                                            tracking-[0.15em]
                                            text-red-400
                                            ring-1
                                            ring-inset
                                            ring-red-500/30
                                        "
                                    >
                                        <AlertTriangle className="size-3" />

                                        {environmentLabel}
                                    </span>
                                </div>
                            )}
                        </div>

                        {/* FORM */}
                        <Form {...form}>
                            <form
                                onSubmit={form.handleSubmit(
                                    onSubmit,
                                )}
                                className="space-y-5"
                            >
                                {/* EMAIL */}
                                <FormField
                                    control={form.control}
                                    name="email"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel
                                                className="
                                                    text-sm
                                                    font-medium
                                                    text-white
                                                "
                                            >
                                                Email
                                            </FormLabel>

                                            <FormControl>
                                                <Input
                                                    type="email"
                                                    autoComplete="email"
                                                    placeholder="you@example.com"
                                                    {...field}
                                                    className="
                                                        h-11
                                                        border-slate-700
                                                        bg-transparent
                                                        text-white
                                                        placeholder:text-slate-600
                                                        focus-visible:border-cer-cyan
                                                        focus-visible:ring-cer-cyan/20
                                                    "
                                                />
                                            </FormControl>

                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                {/* PASSWORD */}
                                <FormField
                                    control={form.control}
                                    name="password"
                                    render={({ field }) => (
                                        <FormItem>
                                            <div className="flex items-center justify-between">
                                                <FormLabel
                                                    className="
                                                        text-sm
                                                        font-medium
                                                        text-white
                                                    "
                                                >
                                                    Password
                                                </FormLabel>

                                                {/* <a
                                                    href="/password-reset"
                                                    className="
                                                        text-xs
                                                        font-medium
                                                        text-cer-cyan
                                                        transition-colors
                                                        hover:text-cyan-300
                                                        hover:underline
                                                    "
                                                >
                                                    Forgot password?
                                                </a> */}
                                            </div>

                                            <div className="relative">
                                                <FormControl>
                                                    <Input
                                                        type={
                                                            showPassword
                                                                ? 'text'
                                                                : 'password'
                                                        }
                                                        autoComplete="current-password"
                                                        placeholder="••••••••"
                                                        {...field}
                                                        className="
                                                            h-11
                                                            border-slate-700
                                                            bg-transparent
                                                            pr-11
                                                            text-white
                                                            placeholder:text-slate-600
                                                            focus-visible:border-cer-cyan
                                                            focus-visible:ring-cer-cyan/20
                                                        "
                                                    />
                                                </FormControl>

                                                <button
                                                    type="button"
                                                    aria-label={
                                                        showPassword
                                                            ? 'Hide password'
                                                            : 'Show password'
                                                    }
                                                    onClick={() => setShowPassword(
                                                        (previous) => !previous,
                                                    )}
                                                    className="
                                                        absolute
                                                        right-3
                                                        top-1/2
                                                        -translate-y-1/2
                                                        rounded-md
                                                        p-1
                                                        text-slate-500
                                                        transition-colors
                                                        hover:text-white
                                                    "
                                                >
                                                    {showPassword ? (
                                                        <EyeOff className="size-4" />
                                                    ) : (
                                                        <Eye className="size-4" />
                                                    )}
                                                </button>
                                            </div>

                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                {/* SIGN IN */}
                                <Button
                                    type="submit"
                                    disabled={isSubmitting}
                                    className={`
                                        h-11
                                        w-full
                                        rounded-lg
                                        font-semibold
                                        transition-all
                                        bg-cer-cyan
                                        text-slate-950
                                        hover:bg-cer-cyan/90
                                    `}
                                >
                                    {isSubmitting
                                        ? 'Signing in...'
                                        : 'Sign In'}
                                </Button>
                            </form>
                        </Form>

                        {/* FOOTER */}
                        <div
                            className="
                                mt-8
                                text-center
                                text-xs
                                text-slate-500
                            "
                        >
                            ©
                            {' '}
                            {new Date().getFullYear()}
                            {' '}
                            {companyName}
                        </div>
                    </div>
                </section>

                {/* ===================================== */}
                {/* RIGHT SIDE */}
                {/* ===================================== */}

                <section
                    className="
                        relative
                        hidden
                        overflow-hidden
                        bg-slate-100
                        lg:flex
                        lg:items-center
                        lg:justify-center
                    "
                >
                    {/* BACKGROUND */}
                    <div
                        className="
                            absolute
                            inset-0
                            bg-gradient-to-br
                            from-slate-50
                            via-slate-100
                            to-slate-300
                        "
                    />

                    {/* DECORATION */}
                    <div
                        className="
                            absolute
                            -right-28
                            -top-28
                            size-[420px]
                            rounded-full
                            bg-white/40
                            blur-3xl
                        "
                    />

                    <div
                        className="
                            absolute
                            -bottom-36
                            -left-28
                            size-[450px]
                            rounded-full
                            bg-slate-400/20
                            blur-3xl
                        "
                    />

                    {/* COMPANY IMAGE */}
                    <div
                        className="
                            relative
                            z-10
                            flex
                            w-full
                            max-w-2xl
                            flex-col
                            items-center
                            justify-center
                            px-12
                            text-center
                        "
                    >
                        {showHeroLogo ? (
                            <img
                                src={companyLogo}
                                alt={`${companyName} logo`}
                                className="
                                    max-h-[320px]
                                    max-w-[75%]
                                    object-contain
                                    drop-shadow-xl
                                "
                                onError={() => setIsHeroLogoVisible(false)}
                            />
                        ) : (
                            <div
                                className="
                                    flex
                                    size-32
                                    items-center
                                    justify-center
                                    rounded-3xl
                                    bg-slate-900
                                    text-4xl
                                    font-bold
                                    text-white
                                    shadow-2xl
                                "
                            >
                                {getCompanyInitials()}
                            </div>
                        )}

                        {/* COMPANY NAME */}
                        <div className="mt-10">
                            <h2
                                className="
                                    text-3xl
                                    font-bold
                                    tracking-tight
                                    text-slate-900
                                "
                            >
                                {companyName}
                            </h2>

                            <p
                                className="
                                    mx-auto
                                    mt-3
                                    max-w-md
                                    text-sm
                                    leading-6
                                    text-slate-600
                                "
                            >
                                {appData?.brand_tagline || appData?.app_title}
                            </p>
                        </div>

                        {/* DEV MODE MESSAGE ONLY */}
                        {isDevMode && (
                            <div className="mt-6">
                                <span
                                    className="
                                        inline-flex
                                        items-center
                                        gap-2
                                        rounded-full
                                        bg-red-100
                                        px-4
                                        py-2
                                        text-xs
                                        font-bold
                                        uppercase
                                        tracking-wider
                                        text-red-700
                                        ring-1
                                        ring-red-200
                                    "
                                >
                                    <AlertTriangle className="size-3.5" />

                                    {environmentLabel}
                                </span>
                            </div>
                        )}
                    </div>

                    {/* FOOTER */}
                    <div
                        className="
                            absolute
                            bottom-6
                            left-0
                            right-0
                            text-center
                            text-xs
                            text-slate-500
                        "
                    >
                        Secure access to
                        {' '}
                        {companyName}
                    </div>
                </section>
            </div>
        </div>
    );
}
