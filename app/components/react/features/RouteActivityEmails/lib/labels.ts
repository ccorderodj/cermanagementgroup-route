import type { ActivityEmailType, Delivery, DeliveryTrigger } from '@/entities/RouteActivityEmails';

/** Cómo se lee cada estado de un envío. Nunca «entregado»: eso sólo lo sabe el buzón. */
export const DELIVERY_STATUS_LABEL: Record<Delivery['status'], string> = {
    pending: 'Pending',
    claimed: 'Sending',
    accepted_by_provider: 'Accepted by the mail provider (delivery not confirmed)',
    retryable_failure: 'Not sent — will be retried',
    permanent_failure: 'Not sent — the provider refused it',
    skipped: 'Not sent',
    unknown_outcome: 'Uncertain outcome — needs reconciliation',
};

export const EMAIL_TYPE_LABEL: Record<ActivityEmailType, string> = {
    midday_motivation: 'Midday Motivation',
    end_of_day_recognition: 'End of Day Recognition',
    strategic_midday_report: 'Strategic Midday Report',
    strategic_end_of_day_report: 'Strategic End-of-Day Report',
};

/** El disparador de una entrega, como lo nombra la pantalla. */
export const TRIGGER_LABEL: Record<DeliveryTrigger, string> = {
    scheduler: 'Scheduler',
    reconcile: 'DigitalOcean job',
    manual: 'Send now',
    resend: 'Resend',
};

/** El origen guardado (`schedule`…) traducido a disparador. */
export const SOURCE_TO_TRIGGER: Record<Delivery['source'], DeliveryTrigger> = {
    schedule: 'scheduler',
    reconcile: 'reconcile',
    manual: 'manual',
};
