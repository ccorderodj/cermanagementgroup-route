-- CER Route: consultas de informe.
-- Devuelven estado para leer. Requieren :company_id.
-- Uso:  psql -v company_id=1 -f route_informes.sql <base>

\echo 'U-03 [Usuarios y roles] Rol de CER Route concedido a alguien sin perfil, y viceversa'
SELECT u.username, r.name AS rol, sp.id AS supervisor_profile_id
FROM user_company uc
JOIN role r ON r.id = uc.role_id
JOIN "user" u ON u.id = uc.user_id
LEFT JOIN supervisor_profile sp
  ON sp.user_id = uc.user_id AND sp.company_id = uc.company_id
   AND sp.deleted_at IS NULL
WHERE uc.company_id = :company_id
  AND r.name IN ('supervisor', 'route_admin')
ORDER BY r.name, u.username;

\echo 'U-04 [Usuarios y roles] Superusuarios de plataforma'
SELECT id, username, email, is_active, last_login
FROM "user"
WHERE is_superuser IS TRUE
ORDER BY id;

\echo 'U-05 [Usuarios y roles] Roles sin ninguna capacidad concedida'
SELECT r.id, r.name, r.category, count(rp.id) AS capacidades
FROM role r
LEFT JOIN role_permission rp ON rp.role_id = r.id AND rp.is_active IS TRUE
WHERE r.company_id = :company_id AND r.is_active IS TRUE
GROUP BY r.id, r.name, r.category
HAVING count(rp.id) = 0;

\echo 'U-06 [Usuarios y roles] Solicitudes de cambio de capacidades pendientes'
SELECT rq.id, r.name AS rol, rq.status, rq.requested_by_user_id,
       rq.reviewed_by_user_id, rq.created_at
FROM role_permission_change_request rq
JOIN role r ON r.id = rq.role_id
WHERE rq.company_id = :company_id AND rq.status = 'pending'
ORDER BY rq.created_at;

\echo 'J-05 [Jornada de trabajo] Origen de la hora de inicio, distribucion'
SELECT started_at_source, count(*) AS cuantas,
       round(avg(EXTRACT(EPOCH FROM (started_received_at - started_at)))::numeric, 1) AS retraso_medio_s
FROM work_session
WHERE company_id = :company_id
GROUP BY started_at_source
ORDER BY cuantas DESC;

\echo 'J-06 [Jornada de trabajo] Jornadas sin vehiculo aplicable'
SELECT id, user_id, session_date, vehicle_id, mpg_snapshot
FROM work_session
WHERE company_id = :company_id AND vehicle_id IS NULL
ORDER BY session_date DESC;

\echo 'J-07 [Jornada de trabajo] Snapshot de MPG sin vehiculo, o al contrario'
SELECT id, company_id, vehicle_id, mpg_snapshot
FROM work_session
WHERE (vehicle_id IS NULL AND mpg_snapshot IS NOT NULL)
   OR (vehicle_id IS NOT NULL AND mpg_snapshot IS NULL);

\echo 'V-04 [Vigencia de vehiculo] El vehiculo que una jornada deberia haber resuelto'
SELECT ws.id AS work_session_id, ws.started_at, ws.vehicle_id AS vehiculo_en_snapshot,
       va.vehicle_id AS vehiculo_vigente_entonces,
       (ws.vehicle_id IS DISTINCT FROM va.vehicle_id) AS discrepa
FROM work_session ws
JOIN supervisor_profile sp
  ON sp.user_id = ws.user_id AND sp.company_id = ws.company_id
LEFT JOIN vehicle_assignment va
  ON va.company_id = ws.company_id
 AND va.supervisor_profile_id = sp.id
 AND va.effective_from <= ws.started_at
 AND (va.effective_to IS NULL OR va.effective_to > ws.started_at)
WHERE ws.company_id = :company_id
ORDER BY ws.started_at DESC;

\echo 'V-05 [Vigencia de vehiculo] Historial de asignaciones de un supervisor'
SELECT va.supervisor_profile_id, u.username, v.unit AS vehiculo,
       va.effective_from, va.effective_to,
       CASE WHEN va.effective_to IS NULL THEN 'abierta' ELSE 'cerrada' END AS estado
FROM vehicle_assignment va
JOIN supervisor_profile sp ON sp.id = va.supervisor_profile_id
JOIN "user" u ON u.id = sp.user_id
JOIN vehicle v ON v.id = va.vehicle_id
WHERE va.company_id = :company_id
ORDER BY u.username, va.effective_from;

\echo 'T-07 [Viajes] Cadena de cambios de plan con un salto'
SELECT c.trip_id, c.id, c.changed_at, c.from_purpose, c.to_purpose,
       lag(c.to_purpose) OVER (PARTITION BY c.trip_id ORDER BY c.changed_at, c.id) AS to_anterior
FROM trip_purpose_change c
WHERE c.company_id = :company_id
ORDER BY c.trip_id, c.changed_at, c.id;

\echo 'O-04 [Odometro] Excepciones de odometro y su estado'
SELECT r.id, r.work_session_id, r.evidence_type, r.status, r.reason,
       r.requested_by, r.requested_at, r.decided_by, r.decided_at, r.consumed_at
FROM odometer_exception_request r
WHERE r.company_id = :company_id
ORDER BY r.requested_at DESC;

\echo 'O-06 [Odometro] Estado de las lecturas por jornada'
SELECT e.evidence_type, e.status, e.evidence_method, count(*) AS cuantas
FROM odometer_evidence e
WHERE e.company_id = :company_id
GROUP BY e.evidence_type, e.status, e.evidence_method
ORDER BY e.evidence_type, cuantas DESC;

\echo 'C-03 [Actividades] Bloque sin ninguna actividad etiquetada'
SELECT ae.id, ae.company_id, ae.trip_id, ae.status
FROM activity_execution ae
LEFT JOIN activity_execution_activity a ON a.activity_execution_id = ae.id
WHERE ae.company_id = :company_id
GROUP BY ae.id, ae.company_id, ae.trip_id, ae.status
HAVING count(a.id) = 0;

\echo 'C-04 [Actividades] La etiqueta guardada frente al valor de lista actual'
SELECT a.id, a.label AS etiqueta_guardada, sv.label AS etiqueta_actual,
       sv.deleted_at, sv.is_active
FROM activity_execution_activity a
JOIN standard_value sv ON sv.id = a.standard_value_id
WHERE a.company_id = :company_id AND a.label <> sv.label;

\echo 'L-09 [Evidencia de ubicacion] Distribucion de niveles de evidencia'
SELECT evidence_level, count(*) AS cuantos,
       round(100.0 * count(*) / NULLIF(sum(count(*)) OVER (), 0), 1) AS pct,
       round(avg(accuracy_m)::numeric, 1) AS precision_media_m,
       round(avg(source_age_seconds)::numeric, 1) AS edad_media_s
FROM location_fix
WHERE company_id = :company_id
GROUP BY evidence_level
ORDER BY cuantos DESC;

\echo 'L-10 [Evidencia de ubicacion] Ubicaciones perdidas por motivo'
SELECT reason_code, permission_state, count(*) AS cuantas
FROM missing_location_event
WHERE company_id = :company_id
GROUP BY reason_code, permission_state
ORDER BY cuantas DESC;

\echo 'L-13 [Evidencia de ubicacion] Avisos pendientes de entregar'
SELECT n.channel, n.status, count(*) AS cuantos,
       min(e.occurred_at) AS mas_antiguo
FROM missing_location_notification n
JOIN missing_location_event e ON e.id = n.missing_location_event_id
WHERE n.company_id = :company_id
GROUP BY n.channel, n.status
ORDER BY n.channel, cuantos DESC;

\echo 'L-14 [Evidencia de ubicacion] Eventos ocurridos sin punto y sin Missing'
SELECT e.company_id, e.event_kind, e.subject_id, e.occurred_at,
       EXTRACT(EPOCH FROM (now() - e.occurred_at))::int AS antiguedad_s
FROM (
    SELECT company_id, 'start_trip' AS event_kind, id AS subject_id, started_at AS occurred_at
    FROM trip WHERE started_at IS NOT NULL
    UNION ALL
    SELECT company_id, 'arrived', id, arrived_at FROM trip WHERE arrived_at IS NOT NULL
    UNION ALL
    SELECT c.company_id, 'change_plan', c.id, c.changed_at FROM trip_purpose_change c
) e
WHERE e.company_id = :company_id
  AND NOT EXISTS (SELECT 1 FROM location_fix f
                  WHERE f.company_id = e.company_id AND f.event_kind = e.event_kind
                    AND f.subject_id = e.subject_id)
  AND NOT EXISTS (SELECT 1 FROM missing_location_event m
                  WHERE m.company_id = e.company_id AND m.event_kind = e.event_kind
                    AND m.subject_id = e.subject_id)
ORDER BY e.occurred_at;

\echo 'K-09 [Kilometraje] Tramos consecutivos que no se encadenan'
SELECT s.trip_mileage_id, s.sequence, s.from_latitude, s.from_longitude,
       lag(s.to_latitude) OVER w AS lat_anterior,
       lag(s.to_longitude) OVER w AS lon_anterior
FROM trip_mileage_segment s
WINDOW w AS (PARTITION BY s.trip_mileage_id ORDER BY s.sequence);

\echo 'K-11 [Kilometraje] Estado del kilometraje por proveedor'
SELECT m.state, s.provider, s.method, s.provider_version,
       count(DISTINCT m.id) AS viajes, count(s.id) AS tramos,
       round(avg(s.distance_meters)::numeric, 1) AS distancia_media_m
FROM trip_mileage m
LEFT JOIN trip_mileage_segment s ON s.trip_mileage_id = m.id
WHERE m.company_id = :company_id
GROUP BY m.state, s.provider, s.method, s.provider_version
ORDER BY viajes DESC;

\echo 'K-12 [Kilometraje] Suma del dia por jornada, con lo no resuelto'
SELECT ws.id AS work_session_id, ws.session_date, u.username,
       count(*) FILTER (WHERE m.state = 'calculated') AS calculados,
       round(sum(m.total_meters) FILTER (WHERE m.state = 'calculated') / 1609.344, 2) AS millas,
       count(*) FILTER (WHERE m.state = 'pending_calculation') AS pendientes,
       count(*) FILTER (WHERE m.state = 'not_calculable') AS no_calculables,
       count(*) FILTER (WHERE m.state = 'calculation_failed') AS fallidos,
       (count(*) FILTER (WHERE m.state <> 'calculated') = 0) AS totalmente_resuelta
FROM work_session ws
JOIN "user" u ON u.id = ws.user_id
JOIN trip t ON t.work_session_id = ws.id AND t.company_id = ws.company_id
JOIN trip_mileage m ON m.trip_id = t.id AND m.company_id = t.company_id
WHERE ws.company_id = :company_id
GROUP BY ws.id, ws.session_date, u.username
ORDER BY ws.session_date DESC;

\echo 'K-13 [Kilometraje] Viajes terminados sin fila de kilometraje'
SELECT t.id AS trip_id, t.company_id, t.status, t.arrived_at, t.ended_at
FROM trip t
WHERE t.company_id = :company_id
  AND t.status IN ('arrived', 'closed', 'interrupted')
  AND NOT EXISTS (SELECT 1 FROM trip_mileage m
                  WHERE m.trip_id = t.id AND m.company_id = t.company_id)
ORDER BY t.arrived_at;

\echo 'X-02 [Correlacion offline] Cobertura de la clave de accion'
SELECT 'work_session' AS tabla,
       count(*) AS filas,
       count(client_action_key) AS con_clave,
       count(*) - count(client_action_key) AS sin_clave
FROM work_session WHERE company_id = :company_id
UNION ALL
SELECT 'trip', count(*), count(client_action_key), count(*) - count(client_action_key)
FROM trip WHERE company_id = :company_id
UNION ALL
SELECT 'trip_purpose_change', count(*), count(client_action_key), count(*) - count(client_action_key)
FROM trip_purpose_change WHERE company_id = :company_id;

\echo 'X-03 [Correlacion offline] Retraso de sincronizacion de la evidencia'
SELECT f.event_kind,
       count(*) AS puntos,
       round(avg(EXTRACT(EPOCH FROM (f.server_received_at - f.device_captured_at)))::numeric, 1) AS retraso_medio_s,
       round(max(EXTRACT(EPOCH FROM (f.server_received_at - f.device_captured_at)))::numeric, 1) AS retraso_max_s,
       count(*) FILTER (WHERE f.server_received_at - f.device_captured_at > interval '5 minutes') AS sincronizados_tarde
FROM location_fix f
WHERE f.company_id = :company_id
GROUP BY f.event_kind
ORDER BY retraso_max_s DESC NULLS LAST;

\echo 'H-02 [Integridad historica] Disparadores de proteccion presentes y activos'
SELECT c.relname AS tabla, t.tgname AS disparador,
       CASE t.tgenabled WHEN 'O' THEN 'activo' WHEN 'D' THEN 'DESACTIVADO'
            ELSE t.tgenabled::text END AS estado
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
WHERE NOT t.tgisinternal
  AND (t.tgname LIKE '%append_only%' OR t.tgname LIKE '%no_truncate%')
ORDER BY c.relname, t.tgname;

\echo 'H-03 [Integridad historica] Restricciones que sostienen los invariantes'
SELECT conname AS restriccion, conrelid::regclass AS tabla,
       CASE contype WHEN 'c' THEN 'CHECK' WHEN 'u' THEN 'UNIQUE'
            WHEN 'x' THEN 'EXCLUDE' WHEN 'f' THEN 'FK' ELSE contype::text END AS tipo
FROM pg_constraint
WHERE conname IN (
    'ex_vehicle_assignment_no_overlap',
    'ck_vehicle_assignment_period',
    'ck_location_fix_evidence_level',
    'ck_location_fix_event_subject',
    'ck_location_fix_coordinates',
    'ck_location_fix_cached_age',
    'ck_trip_mileage_calculated_facts',
    'ck_trip_mileage_terminal_needs_reason',
    'ck_missing_location_notification_delivered',
    'uq_missing_location_notification_channel',
    'uq_trip_mileage_trip',
    'ck_activity_execution_terminal_facts',
    'uq_user_company_user_company'
)
ORDER BY conrelid::regclass::text, conname;

\echo 'H-04 [Integridad historica] Indices unicos de correlacion e idempotencia'
SELECT indexname AS indice, tablename AS tabla, indexdef LIKE '%UNIQUE%' AS es_unico
FROM pg_indexes
WHERE indexname IN (
    'uq_location_fix_event',
    'uq_missing_location_event',
    'uq_vehicle_assignment_current',
    'uq_work_session_client_action_key',
    'uq_trip_client_action_key',
    'uq_trip_purpose_change_client_action_key',
    'uq_trip_mileage_segment_sequence',
    'uq_activity_execution_trip'
)
ORDER BY tablename, indexname;

\echo 'H-05 [Integridad historica] Version del esquema aplicada'
SELECT version_num AS migracion_aplicada FROM alembic_version;

\echo 'D-01 [Auditoria] Eventos de auditoria sin actor'
SELECT id, company_id, entity_type, action, actor_user_id, occurred_at
FROM audit_event
WHERE actor_user_id IS NULL
  AND entity_type NOT IN ('trip_mileage')
ORDER BY occurred_at DESC;

\echo 'D-03 [Auditoria] Transiciones de kilometraje auditadas'
SELECT action, count(*) AS cuantas, min(occurred_at) AS primera, max(occurred_at) AS ultima
FROM audit_event
WHERE company_id = :company_id AND entity_type = 'trip_mileage'
GROUP BY action ORDER BY cuantas DESC;

\echo 'D-04 [Auditoria] Actividad de auditoria por tipo de entidad'
SELECT entity_type, action, count(*) AS cuantas
FROM audit_event
WHERE company_id = :company_id
GROUP BY entity_type, action
ORDER BY entity_type, cuantas DESC;

\echo 'D-05 [Auditoria] Claves de idempotencia y su caducidad'
SELECT scope, count(*) AS cuantas,
       count(*) FILTER (WHERE expires_at < now()) AS caducadas,
       min(created_at) AS mas_antigua
FROM idempotency_record
WHERE company_id = :company_id
GROUP BY scope ORDER BY cuantas DESC;
