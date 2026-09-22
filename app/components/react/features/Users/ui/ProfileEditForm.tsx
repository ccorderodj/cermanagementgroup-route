import {
    memo, useCallback, useEffect, useMemo, useState,
} from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import {
    Eye, EyeOff, Loader2, Mail, ShieldCheck, UserRound,
} from 'lucide-react';
import {
    AlertDialog,
    AlertDialogContent,
    Button,
    Form,
    FormControl,
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    Input,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/shared/ui/shadcn/new-york';
import CookieService from '@/shared/lib/utils/CookieService';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch';
import { extractErrorMessage } from '@/shared/lib/utils/utils';
import { fetchProfile, updateProfile } from '@/entities/users';
import { useUser } from '@/app/providers/StoreProvider';

const profileSchema = z.object({
    first_name: z.string().trim().min(1, 'First name is required'),
    last_name: z.string().trim().min(1, 'Last name is required'),
    username: z.string().trim().min(1, 'Username is required'),
    email: z.string().trim().email('Invalid email'),
    gender: z.enum(['true', 'false']),
    new_password: z.string().default(''),
    confirm_password: z.string().default(''),
}).superRefine((values, ctx) => {
    const newPassword = values.new_password.trim();
    const confirmPassword = values.confirm_password.trim();
    const hasPasswordInput = Boolean(newPassword || confirmPassword);

    if (!hasPasswordInput) {
        return;
    }

    if (!newPassword) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['new_password'],
            message: 'New password is required',
        });
    }

    if (!confirmPassword) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['confirm_password'],
            message: 'Confirm password is required',
        });
    }

    if (newPassword && newPassword.length < 8) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['new_password'],
            message: 'Password must be at least 8 characters',
        });
    }

    if (newPassword && !/[A-Z]/.test(newPassword)) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['new_password'],
            message: 'Must include one uppercase letter',
        });
    }

    if (newPassword && !/[0-9]/.test(newPassword)) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['new_password'],
            message: 'Must include one number',
        });
    }

    if (newPassword && confirmPassword && newPassword !== confirmPassword) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['confirm_password'],
            message: 'Passwords do not match',
        });
    }
});

type ProfileFormValues = z.infer<typeof profileSchema>;

export function ProfileEditForm() {
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const { userLogged, setUserLogged } = useUser();
    const [isLoadingProfile, setIsLoadingProfile] = useState<boolean>(true);
    const [isSaving, setIsSaving] = useState<boolean>(false);
    const [showNewPassword, setShowNewPassword] = useState<boolean>(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState<boolean>(false);

    const form = useForm<ProfileFormValues>({
        resolver: zodResolver(profileSchema),
        defaultValues: {
            first_name: '',
            last_name: '',
            username: '',
            email: '',
            gender: 'false',
            new_password: '',
            confirm_password: '',
        },
        mode: 'onChange',
    });

    const canSubmit = useMemo(
        () => form.formState.isValid && !isSaving && !isLoadingProfile,
        [form.formState.isValid, isSaving, isLoadingProfile],
    );

    const loadProfile = useCallback(async () => {
        try {
            const result = await dispatch(fetchProfile()).unwrap();
            form.reset({
                first_name: result.first_name ?? '',
                last_name: result.last_name ?? '',
                username: result.username ?? '',
                email: result.email ?? '',
                gender: result.gender ? 'true' : 'false',
                new_password: '',
                confirm_password: '',
            });
        } catch (error) {
            toast({
                variant: 'destructive',
                title: 'Could not load profile',
                description: extractErrorMessage(error, 'Unable to load user profile'),
            });
        } finally {
            setIsLoadingProfile(false);
        }
    }, [dispatch, form, toast]);

    useEffect(() => {
        loadProfile();
    }, [loadProfile]);

    const submitProfile = useCallback(async (values: ProfileFormValues) => {
        setIsSaving(true);
        try {
            const hasPasswordUpdate = Boolean(
                values.new_password.trim()
                || values.confirm_password.trim(),
            );

            const profilePayload = {
                first_name: values.first_name.trim(),
                last_name: values.last_name.trim(),
                username: values.username.trim(),
                email: values.email.trim(),
                gender: values.gender === 'true',
                new_password: hasPasswordUpdate ? values.new_password.trim() : undefined,
            };
            const updated = await dispatch(updateProfile(profilePayload)).unwrap();

            if (userLogged) {
                const nextUser = {
                    ...userLogged,
                    first_name: updated.first_name,
                    last_name: updated.last_name,
                    username: updated.username,
                    email: updated.email,
                    gender: updated.gender,
                };
                setUserLogged(nextUser);
                CookieService.setCookie('user_data', JSON.stringify(nextUser), 1);
            }

            form.setValue('new_password', '');
            form.setValue('confirm_password', '');

            toast({
                title: hasPasswordUpdate ? 'Profile and password updated' : 'Profile updated',
                description: hasPasswordUpdate
                    ? 'Your profile and password have been changed successfully.'
                    : 'Your profile information has been saved.',
            });
        } catch (error) {
            toast({
                variant: 'destructive',
                title: 'Could not save changes',
                description: extractErrorMessage(error, 'Unable to update profile'),
            });
        } finally {
            setIsSaving(false);
        }
    }, [dispatch, form, setUserLogged, toast, userLogged]);

    if (!userLogged) {
        return (
            <div className="space-y-6 p-4 md:p-8">
                <div className="rounded-lg border bg-background p-4">
                    <h2 className="text-2xl font-bold tracking-tight">My Profile</h2>
                    <p className="">User context is not available.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6 p-4 md:p-8" data-testid="ProfileEditForm">
            <div>
                <h2 className="text-2xl font-bold tracking-tight">My Profile</h2>
                <p className="">Update your account information and password from one form.</p>
            </div>

            <div className="rounded-lg border bg-background p-4">
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(submitProfile)} className="space-y-0">
                        <fieldset className="space-y-6">
                            <div className="mb-3 flex items-start justify-between gap-3 border-b pb-4">
                                <div>
                                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                                        <UserRound className="h-4 w-4" />
                                        Profile Information
                                    </h3>
                                    <p className="mt-1 text-sm text-muted-foreground">
                                        Your changes are scoped to your current company access context.
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                    control={form.control}
                                    name="first_name"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>First Name</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter first name" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="last_name"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Last Name</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter last name" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="username"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Username</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter username" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="email"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel className="flex items-center gap-1.5">
                                                <Mail className="h-4 w-4" />
                                                Email
                                            </FormLabel>
                                            <FormControl>
                                                <Input {...field} type="email" placeholder="Enter email" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="gender"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Gender Avatar</FormLabel>
                                            <Select
                                                value={field.value}
                                                onValueChange={field.onChange}
                                                disabled={isLoadingProfile || isSaving}
                                            >
                                                <FormControl>
                                                    <SelectTrigger>
                                                        <SelectValue placeholder="Select avatar" />
                                                    </SelectTrigger>
                                                </FormControl>
                                                <SelectContent>
                                                    <SelectItem value="true">Male Avatar</SelectItem>
                                                    <SelectItem value="false">Female Avatar</SelectItem>
                                                </SelectContent>
                                            </Select>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>

                            <div className="mb-3 flex items-start justify-between gap-3 border-b pt-2 pb-4">
                                <div>
                                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                                        <ShieldCheck className="h-4 w-4" />
                                        Password & Security
                                    </h3>
                                    <p className="mt-1 text-sm text-muted-foreground">
                                        Optional. Fill these fields only if you want to change your password.
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                    control={form.control}
                                    name="new_password"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>New Password</FormLabel>
                                            <div className="relative">
                                                <FormControl>
                                                    <Input
                                                        {...field}
                                                        type={showNewPassword ? 'text' : 'password'}
                                                        placeholder="Enter new password"
                                                        className="pr-10"
                                                        disabled={isSaving || isLoadingProfile}
                                                    />
                                                </FormControl>
                                                <button
                                                    type="button"
                                                    onClick={() => setShowNewPassword((prev) => !prev)}
                                                    className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-700"
                                                    disabled={isSaving || isLoadingProfile}
                                                >
                                                    {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                                </button>
                                            </div>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                                <FormField
                                    control={form.control}
                                    name="confirm_password"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Confirm New Password</FormLabel>
                                            <div className="relative">
                                                <FormControl>
                                                    <Input
                                                        {...field}
                                                        type={showConfirmPassword ? 'text' : 'password'}
                                                        placeholder="Re-enter new password"
                                                        className="pr-10"
                                                        disabled={isSaving || isLoadingProfile}
                                                    />
                                                </FormControl>
                                                <button
                                                    type="button"
                                                    onClick={() => setShowConfirmPassword((prev) => !prev)}
                                                    className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-700"
                                                    disabled={isSaving || isLoadingProfile}
                                                >
                                                    {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                                </button>
                                            </div>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>

                            <div>
                                <Button
                                    type="submit"
                                    disabled={!canSubmit}
                                    className="w-full bg-primary text-white font-medium p-2 rounded-md hover:bg-primary"
                                >
                                    {(isLoadingProfile || isSaving) ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            {isSaving ? 'Saving...' : 'Loading...'}
                                        </>
                                    ) : (
                                        'Save Changes'
                                    )}
                                </Button>
                            </div>
                        </fieldset>
                    </form>
                </Form>
            </div>

            <AlertDialog open={isSaving} onOpenChange={() => {}}>
                <AlertDialogContent className="max-w-sm border-slate-700 bg-slate-950 text-slate-100">
                    <div className="flex items-center gap-3 py-2">
                        <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
                        <div>
                            <p className="text-base font-semibold">Saving Changes...</p>
                            <p className="text-sm text-slate-300">Please wait while we update your profile.</p>
                        </div>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

export default memo(ProfileEditForm);
