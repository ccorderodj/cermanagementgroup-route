export {
    ACTIVITY_EMAIL_TYPES,
    activityEmailTemplateSchema,
    activityEmailRecipientSchema,
    activityEmailPreviewSchema,
} from './model/types';
export type {
    ActivityEmailPreview,
    ActivityEmailRecipient,
    ActivityEmailTemplate,
    ActivityEmailTestResult,
    ActivityEmailTestTargets,
    ActivityEmailToken,
    ActivityEmailType,
    StrategicRecipient,
} from './model/types';
export {
    fetchActivityEmailTemplates,
    updateActivityEmailTemplate,
    restoreActivityEmailTemplate,
    previewActivityEmailTemplate,
    fetchActivityEmailRecipients,
    updateActivityEmailRecipient,
    fetchActivityEmailTestTargets,
    sendActivityEmailTest,
    fetchStrategicRecipients,
    updateStrategicRecipient,
} from './model/services/activityEmailsService';
