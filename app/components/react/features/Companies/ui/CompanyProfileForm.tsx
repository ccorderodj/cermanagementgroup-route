import {
    memo, useCallback, useEffect, useMemo, useState,
} from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import {
    Building2, Loader2, Palette,
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
    Textarea,
} from '@/shared/ui/shadcn/new-york';
import { useToast } from '@/shared/lib/hooks/useToast/useToast';
import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch';
import { extractErrorMessage } from '@/shared/lib/utils/utils';
import {
    fetchCompanyProfile,
    updateCompanyProfile,
    UpdateCompanyProfilePayload,
} from '@/entities/Companies';

const HEX_COLOR_REGEX = /^$|^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/;

const companyProfileSchema = z.object({
    name: z.string().trim().min(1, 'Company name is required'),
    domain: z.string().trim().max(255, 'Domain must be at most 255 characters'),
    subdomain: z.string().trim().max(255, 'Subdomain must be at most 255 characters'),
    address: z.string().trim(),
    phone: z.string().trim().max(20, 'Phone must be at most 20 characters'),
    email: z.string().trim().email('Invalid email').or(z.literal('')),
    phone_secondary: z.string().trim().max(20, 'Secondary phone must be at most 20 characters'),
    website: z.string().trim().max(255, 'Website must be at most 255 characters'),
    logo_url: z.string().trim().max(500, 'Logo URL must be at most 500 characters'),

    brand_primary_color: z.string().trim().regex(HEX_COLOR_REGEX, 'Use hex format like #1D4ED8'),
    brand_secondary_color: z.string().trim().regex(HEX_COLOR_REGEX, 'Use hex format like #0EA5E9'),
    pdf_text_color: z.string().trim().regex(HEX_COLOR_REGEX, 'Use hex format like #0F172A'),
    pdf_muted_text_color: z.string().trim().regex(HEX_COLOR_REGEX, 'Use hex format like #64748B'),
    pdf_surface_color: z.string().trim().regex(HEX_COLOR_REGEX, 'Use hex format like #F8FAFC'),
});

type CompanyProfileFormValues = z.infer<typeof companyProfileSchema>;

const normalizeOptional = (value: string) => {
    const normalized = value.trim();
    return normalized || null;
};

export function CompanyProfileForm() {
    const dispatch = useAppDispatch();
    const { toast } = useToast();
    const [isLoadingProfile, setIsLoadingProfile] = useState<boolean>(true);
    const [isSaving, setIsSaving] = useState<boolean>(false);

    const form = useForm<CompanyProfileFormValues>({
        resolver: zodResolver(companyProfileSchema),
        defaultValues: {
            name: '',
            domain: '',
            subdomain: '',
            address: '',
            phone: '',
            email: '',
            phone_secondary: '',
            website: '',
            logo_url: '',

            brand_primary_color: '',
            brand_secondary_color: '',
            pdf_text_color: '',
            pdf_muted_text_color: '',
            pdf_surface_color: '',
        },
        mode: 'onChange',
    });

    const canSubmit = useMemo(
        () => form.formState.isValid && !isLoadingProfile && !isSaving,
        [form.formState.isValid, isLoadingProfile, isSaving],
    );

    const loadProfile = useCallback(async () => {
        try {
            const profile = await dispatch(fetchCompanyProfile()).unwrap();
            form.reset({
                name: profile.name ?? '',
                domain: profile.domain ?? '',
                subdomain: profile.subdomain ?? '',
                address: profile.address ?? '',
                phone: profile.phone ?? '',
                email: profile.email ?? '',
                phone_secondary: profile.phone_secondary ?? '',
                website: profile.website ?? '',
                logo_url: profile.logo_url ?? '',

                brand_primary_color: profile.brand_primary_color ?? '',
                brand_secondary_color: profile.brand_secondary_color ?? '',
                pdf_text_color: profile.pdf_text_color ?? '',
                pdf_muted_text_color: profile.pdf_muted_text_color ?? '',
                pdf_surface_color: profile.pdf_surface_color ?? '',
            });
        } catch (error) {
            toast({
                variant: 'destructive',
                title: 'Could not load company profile',
                description: extractErrorMessage(error, 'Unable to load company information'),
            });
        } finally {
            setIsLoadingProfile(false);
        }
    }, [dispatch, form, toast]);

    useEffect(() => {
        loadProfile();
    }, [loadProfile]);

    const submitProfile = useCallback(async (values: CompanyProfileFormValues) => {
        setIsSaving(true);
        try {
            const payload: UpdateCompanyProfilePayload = {
                name: values.name.trim(),
                domain: normalizeOptional(values.domain),
                subdomain: normalizeOptional(values.subdomain),
                address: normalizeOptional(values.address),
                phone: normalizeOptional(values.phone),
                email: normalizeOptional(values.email),
                phone_secondary: normalizeOptional(values.phone_secondary),
                website: normalizeOptional(values.website),
                logo_url: normalizeOptional(values.logo_url),

                brand_primary_color: normalizeOptional(values.brand_primary_color),
                brand_secondary_color: normalizeOptional(values.brand_secondary_color),
                pdf_text_color: normalizeOptional(values.pdf_text_color),
                pdf_muted_text_color: normalizeOptional(values.pdf_muted_text_color),
                pdf_surface_color: normalizeOptional(values.pdf_surface_color),
            };
            const updated = await dispatch(updateCompanyProfile(payload)).unwrap();

            form.reset({
                name: updated.name ?? '',
                domain: updated.domain ?? '',
                subdomain: updated.subdomain ?? '',
                address: updated.address ?? '',
                phone: updated.phone ?? '',
                email: updated.email ?? '',
                phone_secondary: updated.phone_secondary ?? '',
                website: updated.website ?? '',
                logo_url: updated.logo_url ?? '',

                brand_primary_color: updated.brand_primary_color ?? '',
                brand_secondary_color: updated.brand_secondary_color ?? '',
                pdf_text_color: updated.pdf_text_color ?? '',
                pdf_muted_text_color: updated.pdf_muted_text_color ?? '',
                pdf_surface_color: updated.pdf_surface_color ?? '',
            });

            toast({
                title: 'Company profile updated',
                description: 'Company configuration has been saved successfully.',
            });
        } catch (error) {
            toast({
                variant: 'destructive',
                title: 'Could not save company profile',
                description: extractErrorMessage(error, 'Unable to update company information'),
            });
        } finally {
            setIsSaving(false);
        }
    }, [dispatch, form, toast]);

    return (
        <div className="space-y-6 p-4 md:p-8" data-testid="CompanyProfileForm">
            <div>
                <h2 className="text-2xl font-bold tracking-tight">Company Profile</h2>
                <p className="">Manage company contact details and branding.</p>
            </div>

            <div className="rounded-lg border bg-background p-4">
                <Form {...form}>
                    <form onSubmit={form.handleSubmit(submitProfile)} className="space-y-0">
                        <fieldset className="space-y-6">
                            <div className="mb-3 flex items-start justify-between gap-3 border-b pb-4">
                                <div>
                                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                                        <Building2 className="h-4 w-4" />
                                        Company Information
                                    </h3>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                    control={form.control}
                                    name="name"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Company Name</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter company name" disabled={isLoadingProfile || isSaving} />
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
                                            <FormLabel>Email</FormLabel>
                                            <FormControl>
                                                <Input {...field} type="email" placeholder="Enter company email" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="phone"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Phone</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter phone" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="phone_secondary"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Secondary Phone</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter secondary phone" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="domain"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Domain</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter domain" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="subdomain"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Subdomain</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter subdomain" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="website"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Website</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter website URL" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="logo_url"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Logo URL</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="Enter logo URL" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />

                            </div>

                            <FormField
                                control={form.control}
                                name="address"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Address</FormLabel>
                                        <FormControl>
                                            <Textarea {...field} rows={3} placeholder="Enter company address" disabled={isLoadingProfile || isSaving} />
                                        </FormControl>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            <div className="mb-3 flex items-start justify-between gap-3 border-b pt-2 pb-4">
                                <div>
                                    <h3 className="flex items-center gap-2 text-lg font-semibold">
                                        <Palette className="h-4 w-4" />
                                        Branding Colors
                                    </h3>
                                </div>
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <FormField
                                    control={form.control}
                                    name="brand_primary_color"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Primary Color</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="#1D4ED8" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="brand_secondary_color"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>Secondary Color</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="#0EA5E9" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="pdf_text_color"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>PDF Text Color</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="#0F172A" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="pdf_muted_text_color"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>PDF Muted Text Color</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="#64748B" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                                <FormField
                                    control={form.control}
                                    name="pdf_surface_color"
                                    render={({ field }) => (
                                        <FormItem>
                                            <FormLabel>PDF Surface Color</FormLabel>
                                            <FormControl>
                                                <Input {...field} placeholder="#F8FAFC" disabled={isLoadingProfile || isSaving} />
                                            </FormControl>
                                            <FormMessage />
                                        </FormItem>
                                    )}
                                />
                            </div>

                            <div>
                                <Button
                                    type="submit"
                                    disabled={!canSubmit}
                                    className="w-full bg-primary p-2 font-medium text-white hover:bg-primary"
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

            <AlertDialog open={isSaving} onOpenChange={() => { }}>
                <AlertDialogContent className="max-w-sm border-slate-700 bg-slate-950 text-slate-100">
                    <div className="flex items-center gap-3 py-2">
                        <Loader2 className="h-5 w-5 animate-spin text-cyan-400" />
                        <div>
                            <p className="text-base font-semibold">Saving Changes...</p>
                            <p className="text-sm text-slate-300">Please wait while we update company settings.</p>
                        </div>
                    </div>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
}

export default memo(CompanyProfileForm);
