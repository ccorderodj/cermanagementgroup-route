-- CER Route: la puerta de invariantes, en UNA SOLA consulta.
--
-- Pensado para clientes graficos (DBeaver, DataGrip, pgAdmin): se ejecuta
-- como una sentencia y devuelve una fila por invariante, no 57 pestanas.
--
-- No lleva meta-comandos de psql ni parametros: se pega y se ejecuta.
--
-- COMO SE LEE: `filas = 0` en las 57 es correcto. Cualquier fila con
-- `filas > 0` es un HALLAZGO, y sale arriba porque el orden es descendente.
-- Para ver QUE filas son, no cuantas, busca ese `id` en
-- route_invariantes_cliente.sql y corre esa consulta sola.

SELECT * FROM (
SELECT 'A-01' AS id, 'Aislamiento de tenant' AS flujo, 'Pertenencia con rol de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT uc.id AS user_company_id, uc.company_id, uc.role_id, r.company_id AS role_company_id
FROM user_company uc
JOIN role r ON r.id = uc.role_id
WHERE r.company_id <> uc.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-02' AS id, 'Aislamiento de tenant' AS flujo, 'Jornada cuyo vehiculo es de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT ws.id AS work_session_id, ws.company_id, ws.vehicle_id, v.company_id AS vehicle_company_id
FROM work_session ws
JOIN vehicle v ON v.id = ws.vehicle_id
WHERE v.company_id <> ws.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-03' AS id, 'Aislamiento de tenant' AS flujo, 'Viaje colgado de la jornada de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT t.id AS trip_id, t.company_id, ws.company_id AS session_company_id
FROM trip t
JOIN work_session ws ON ws.id = t.work_session_id
WHERE ws.company_id <> t.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-04' AS id, 'Aislamiento de tenant' AS flujo, 'Punto de ubicacion en jornada de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT f.id AS location_fix_id, f.company_id, ws.company_id AS session_company_id
FROM location_fix f
JOIN work_session ws ON ws.id = f.work_session_id
WHERE ws.company_id <> f.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-05' AS id, 'Aislamiento de tenant' AS flujo, 'Kilometraje cuyo viaje es de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT m.id AS trip_mileage_id, m.company_id, t.company_id AS trip_company_id
FROM trip_mileage m
JOIN trip t ON t.id = m.trip_id
WHERE t.company_id <> m.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-06' AS id, 'Aislamiento de tenant' AS flujo, 'Aviso de Missing cuyo hecho es de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT n.id AS notification_id, n.company_id, e.company_id AS event_company_id
FROM missing_location_notification n
JOIN missing_location_event e ON e.id = n.missing_location_event_id
WHERE e.company_id <> n.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-07' AS id, 'Aislamiento de tenant' AS flujo, 'Tramo cuyo kilometraje padre es de otra empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT s.id AS segment_id, s.company_id, m.company_id AS parent_company_id
FROM trip_mileage_segment s
JOIN trip_mileage m ON m.id = s.trip_mileage_id
WHERE m.company_id <> s.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'A-08' AS id, 'Aislamiento de tenant' AS flujo, 'Valor de lista de otra empresa usado en un viaje' AS invariante,
       (SELECT count(*) FROM (
SELECT t.id AS trip_id, t.company_id, t.current_standard_value_id, sv.company_id AS value_company_id
FROM trip t
JOIN standard_value sv ON sv.id = t.current_standard_value_id
WHERE sv.company_id <> t.company_id
       ) AS q) AS filas
UNION ALL
SELECT 'U-01' AS id, 'Usuarios y roles' AS flujo, 'Pertenencias duplicadas de una persona en una empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT user_id, company_id, count(*) AS cuantas
FROM user_company
GROUP BY user_id, company_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'U-02' AS id, 'Usuarios y roles' AS flujo, 'Acceso retirado que sigue activo' AS invariante,
       (SELECT count(*) FROM (
SELECT id, user_id, company_id, is_active, deleted_at
FROM user_company
WHERE deleted_at IS NOT NULL AND is_active IS TRUE
       ) AS q) AS filas
UNION ALL
SELECT 'U-07' AS id, 'Usuarios y roles' AS flujo, 'Aprobaciones donde quien pidio tambien reviso' AS invariante,
       (SELECT count(*) FROM (
SELECT id, role_id, requested_by_user_id, reviewed_by_user_id, status
FROM role_permission_change_request
WHERE reviewed_by_user_id IS NOT NULL
  AND reviewed_by_user_id = requested_by_user_id
       ) AS q) AS filas
UNION ALL
SELECT 'U-08' AS id, 'Usuarios y roles' AS flujo, 'Perfil de supervisor sin pertenencia a la empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT sp.id AS supervisor_profile_id, sp.company_id, sp.user_id
FROM supervisor_profile sp
WHERE NOT EXISTS (
    SELECT 1 FROM user_company uc
    WHERE uc.user_id = sp.user_id AND uc.company_id = sp.company_id
)
       ) AS q) AS filas
UNION ALL
SELECT 'L-15' AS id, 'Evidencia de ubicacion' AS flujo, 'Motivo de Missing fuera del catalogo' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, event_kind, reason_code
FROM missing_location_event
WHERE reason_code NOT IN (
    'permission_denied', 'position_unavailable', 'acquisition_timeout',
    'cached_rejected', 'recovery_window_exhausted', 'no_client_report'
)
       ) AS q) AS filas
UNION ALL
SELECT 'K-14' AS id, 'Kilometraje' AS flujo, 'Calculado con razon terminal, o no calculado con fecha' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, trip_id, state, total_meters, calculated_at, terminal_reason
FROM trip_mileage
WHERE (state = 'calculated' AND terminal_reason IS NOT NULL)
   OR (state <> 'calculated' AND calculated_at IS NOT NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'J-01' AS id, 'Jornada de trabajo' AS flujo, 'Mas de una jornada ACTIVA por supervisor' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, user_id, count(*) AS activas
FROM work_session
WHERE status = 'active'
GROUP BY company_id, user_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'J-02' AS id, 'Jornada de trabajo' AS flujo, 'Jornada terminada antes de empezar' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, user_id, started_at, ended_at
FROM work_session
WHERE ended_at IS NOT NULL AND ended_at < started_at
       ) AS q) AS filas
UNION ALL
SELECT 'J-03' AS id, 'Jornada de trabajo' AS flujo, 'Jornada ENDED sin hora de cierre' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, status, started_at, ended_at
FROM work_session
WHERE status = 'ended' AND ended_at IS NULL
       ) AS q) AS filas
UNION ALL
SELECT 'J-04' AS id, 'Jornada de trabajo' AS flujo, 'Ocurrencia posterior a la recepcion' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, started_at, started_received_at, started_at_source
FROM work_session
WHERE started_received_at IS NOT NULL
  AND started_at > started_received_at + interval '5 minutes'
       ) AS q) AS filas
UNION ALL
SELECT 'V-01' AS id, 'Vigencia de vehiculo' AS flujo, 'Asignaciones solapadas del mismo supervisor' AS invariante,
       (SELECT count(*) FROM (
SELECT a.id AS a_id, b.id AS b_id, a.supervisor_profile_id,
       a.effective_from AS a_desde, a.effective_to AS a_hasta,
       b.effective_from AS b_desde, b.effective_to AS b_hasta
FROM vehicle_assignment a
JOIN vehicle_assignment b
  ON b.company_id = a.company_id
 AND b.supervisor_profile_id = a.supervisor_profile_id
 AND b.id > a.id
WHERE tstzrange(a.effective_from, a.effective_to, '[)')
   && tstzrange(b.effective_from, b.effective_to, '[)')
       ) AS q) AS filas
UNION ALL
SELECT 'V-02' AS id, 'Vigencia de vehiculo' AS flujo, 'Asignaciones de duracion cero' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, supervisor_profile_id, vehicle_id, effective_from, effective_to
FROM vehicle_assignment
WHERE effective_to IS NOT NULL AND effective_to = effective_from
       ) AS q) AS filas
UNION ALL
SELECT 'V-03' AS id, 'Vigencia de vehiculo' AS flujo, 'Mas de una asignacion abierta por supervisor' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, supervisor_profile_id, count(*) AS abiertas
FROM vehicle_assignment
WHERE effective_to IS NULL
GROUP BY company_id, supervisor_profile_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'T-01' AS id, 'Viajes' AS flujo, 'Mas de un viaje vivo por jornada' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, work_session_id, count(*) AS vivos
FROM trip
WHERE status NOT IN ('closed', 'interrupted')
GROUP BY company_id, work_session_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'T-02' AS id, 'Viajes' AS flujo, 'Secuencia de viaje duplicada o con huecos' AS invariante,
       (SELECT count(*) FROM (
SELECT work_session_id, sequence, count(*) AS cuantos
FROM trip
GROUP BY work_session_id, sequence
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'T-03' AS id, 'Viajes' AS flujo, 'Viaje ARRIVED o CLOSED sin hora de llegada' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, status, started_at, arrived_at
FROM trip
WHERE status IN ('arrived', 'closed') AND arrived_at IS NULL
       ) AS q) AS filas
UNION ALL
SELECT 'T-04' AS id, 'Viajes' AS flujo, 'Llegada anterior a la salida' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, started_at, arrived_at
FROM trip
WHERE arrived_at IS NOT NULL AND started_at IS NOT NULL AND arrived_at < started_at
       ) AS q) AS filas
UNION ALL
SELECT 'T-05' AS id, 'Viajes' AS flujo, 'Viaje IN_TRANSIT sin hora de salida' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, status, started_at
FROM trip
WHERE status = 'in_transit' AND started_at IS NULL
       ) AS q) AS filas
UNION ALL
SELECT 'T-06' AS id, 'Viajes' AS flujo, 'El plan original nunca se reescribe' AS invariante,
       (SELECT count(*) FROM (
SELECT t.company_id, t.id AS trip_id, t.original_purpose, t.current_purpose,
       count(c.id) AS cambios,
       min(c.from_purpose) AS primer_from
FROM trip t
LEFT JOIN trip_purpose_change c ON c.trip_id = t.id AND c.company_id = t.company_id
GROUP BY t.company_id, t.id, t.original_purpose, t.current_purpose
HAVING count(c.id) > 0 AND min(c.from_purpose) <> t.original_purpose
       ) AS q) AS filas
UNION ALL
SELECT 'T-08' AS id, 'Viajes' AS flujo, 'Cambio de plan fuera de transito' AS invariante,
       (SELECT count(*) FROM (
SELECT c.id, c.trip_id, c.changed_at, t.status, t.started_at, t.arrived_at
FROM trip_purpose_change c
JOIN trip t ON t.id = c.trip_id AND t.company_id = c.company_id
WHERE t.started_at IS NOT NULL
  AND (c.changed_at < t.started_at
       OR (t.arrived_at IS NOT NULL AND c.changed_at > t.arrived_at))
       ) AS q) AS filas
UNION ALL
SELECT 'O-01' AS id, 'Odometro' AS flujo, 'Lectura confirmada sin quien la confirmo' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, evidence_type, status, confirmed_reading, confirmed_by, confirmed_at
FROM odometer_evidence
WHERE confirmed_reading IS NOT NULL AND (confirmed_by IS NULL OR confirmed_at IS NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'O-02' AS id, 'Odometro' AS flujo, 'Mas de una evidencia del mismo tipo por jornada' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, work_session_id, evidence_type, count(*) AS cuantas
FROM odometer_evidence
GROUP BY company_id, work_session_id, evidence_type
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'O-03' AS id, 'Odometro' AS flujo, 'Lectura de fin menor que la de inicio' AS invariante,
       (SELECT count(*) FROM (
SELECT i.work_session_id, i.confirmed_reading AS inicio, f.confirmed_reading AS fin
FROM odometer_evidence i
JOIN odometer_evidence f
  ON f.work_session_id = i.work_session_id AND f.company_id = i.company_id
WHERE i.evidence_type = 'start' AND f.evidence_type = 'end'
  AND i.confirmed_reading IS NOT NULL AND f.confirmed_reading IS NOT NULL
  AND f.confirmed_reading < i.confirmed_reading
       ) AS q) AS filas
UNION ALL
SELECT 'O-05' AS id, 'Odometro' AS flujo, 'Excepcion decidida sin quien la decidio' AS invariante,
       (SELECT count(*) FROM (
SELECT id, work_session_id, status, decided_by, decided_at
FROM odometer_exception_request
WHERE status IN ('approved', 'rejected')
  AND (decided_by IS NULL OR decided_at IS NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'C-01' AS id, 'Actividades' AS flujo, 'Mas de un bloque de ejecucion por viaje' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, trip_id, count(*) AS bloques
FROM activity_execution
GROUP BY company_id, trip_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'C-02' AS id, 'Actividades' AS flujo, 'Bloque terminal sin hora de fin o sin resultado' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, trip_id, status, terminal_action, ended_at,
       outcome_standard_value_id, outcome_label
FROM activity_execution
WHERE status IN ('completed', 'left')
  AND (ended_at IS NULL OR (outcome_standard_value_id IS NULL AND outcome_label IS NULL))
       ) AS q) AS filas
UNION ALL
SELECT 'C-05' AS id, 'Actividades' AS flujo, 'Bloque cuyo viaje no habia llegado' AS invariante,
       (SELECT count(*) FROM (
SELECT ae.id, ae.trip_id, ae.started_at, t.status, t.arrived_at
FROM activity_execution ae
JOIN trip t ON t.id = ae.trip_id AND t.company_id = ae.company_id
WHERE t.arrived_at IS NULL OR ae.started_at < t.arrived_at
       ) AS q) AS filas
UNION ALL
SELECT 'L-01' AS id, 'Evidencia de ubicacion' AS flujo, 'Mas de un punto autoritativo por evento' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, event_kind, subject_kind, subject_id, count(*) AS puntos
FROM location_fix
GROUP BY company_id, event_kind, subject_kind, subject_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'L-02' AS id, 'Evidencia de ubicacion' AS flujo, 'Nivel de evidencia fuera de los tres permitidos' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, event_kind, evidence_level
FROM location_fix
WHERE evidence_level NOT IN ('fresh', 'degraded_cached', 'recovered')
       ) AS q) AS filas
UNION ALL
SELECT 'L-03' AS id, 'Evidencia de ubicacion' AS flujo, 'Punto cacheado sin edad, o fresco con ella' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, event_kind, evidence_level, source_age_seconds
FROM location_fix
WHERE (evidence_level = 'degraded_cached' AND source_age_seconds IS NULL)
   OR (evidence_level <> 'degraded_cached' AND source_age_seconds IS NOT NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'L-04' AS id, 'Evidencia de ubicacion' AS flujo, 'Coordenadas fuera de rango' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, latitude, longitude
FROM location_fix
WHERE latitude < -90 OR latitude > 90 OR longitude < -180 OR longitude > 180
       ) AS q) AS filas
UNION ALL
SELECT 'L-05' AS id, 'Evidencia de ubicacion' AS flujo, 'Pareja evento-sujeto imposible' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, event_kind, subject_kind
FROM location_fix
WHERE NOT (
     (event_kind IN ('start_work','end_work') AND subject_kind = 'work_session')
  OR (event_kind IN ('start_trip','arrived')  AND subject_kind = 'trip')
  OR (event_kind = 'change_plan'              AND subject_kind = 'trip_purpose_change')
  OR (event_kind IN ('activity_complete','activity_leave') AND subject_kind = 'activity_execution')
)
       ) AS q) AS filas
UNION ALL
SELECT 'L-06' AS id, 'Evidencia de ubicacion' AS flujo, 'Punto atado a una fila que no existe' AS invariante,
       (SELECT count(*) FROM (
SELECT f.id, f.event_kind, f.subject_kind, f.subject_id
FROM location_fix f
WHERE (f.subject_kind = 'trip' AND NOT EXISTS (
          SELECT 1 FROM trip t WHERE t.id = f.subject_id AND t.company_id = f.company_id))
   OR (f.subject_kind = 'trip_purpose_change' AND NOT EXISTS (
          SELECT 1 FROM trip_purpose_change c WHERE c.id = f.subject_id AND c.company_id = f.company_id))
   OR (f.subject_kind = 'work_session' AND NOT EXISTS (
          SELECT 1 FROM work_session w WHERE w.id = f.subject_id AND w.company_id = f.company_id))
   OR (f.subject_kind = 'activity_execution' AND NOT EXISTS (
          SELECT 1 FROM activity_execution a WHERE a.id = f.subject_id AND a.company_id = f.company_id))
       ) AS q) AS filas
UNION ALL
SELECT 'L-07' AS id, 'Evidencia de ubicacion' AS flujo, 'Captura posterior a la recepcion' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, event_kind, device_captured_at, server_received_at
FROM location_fix
WHERE device_captured_at > server_received_at + interval '5 minutes'
       ) AS q) AS filas
UNION ALL
SELECT 'L-08' AS id, 'Evidencia de ubicacion' AS flujo, 'Un evento con punto Y con Missing a la vez' AS invariante,
       (SELECT count(*) FROM (
SELECT f.company_id, f.event_kind, f.subject_kind, f.subject_id
FROM location_fix f
JOIN missing_location_event m
  ON m.company_id = f.company_id AND m.event_kind = f.event_kind
 AND m.subject_kind = f.subject_kind AND m.subject_id = f.subject_id
       ) AS q) AS filas
UNION ALL
SELECT 'L-11' AS id, 'Evidencia de ubicacion' AS flujo, 'Missing sin su registro de aviso' AS invariante,
       (SELECT count(*) FROM (
SELECT e.id, e.company_id, e.event_kind, e.subject_id, e.occurred_at
FROM missing_location_event e
WHERE NOT EXISTS (
    SELECT 1 FROM missing_location_notification n
    WHERE n.missing_location_event_id = e.id AND n.company_id = e.company_id
)
       ) AS q) AS filas
UNION ALL
SELECT 'L-12' AS id, 'Evidencia de ubicacion' AS flujo, 'Aviso entregado sin fecha de entrega' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, missing_location_event_id, channel, status, delivered_at
FROM missing_location_notification
WHERE (status = 'notified' AND delivered_at IS NULL)
   OR (status <> 'notified' AND delivered_at IS NOT NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'K-01' AS id, 'Kilometraje' AS flujo, 'Mas de un kilometraje por viaje' AS invariante,
       (SELECT count(*) FROM (
SELECT company_id, trip_id, count(*) AS cuantos
FROM trip_mileage
GROUP BY company_id, trip_id
HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'K-02' AS id, 'Kilometraje' AS flujo, 'Total publicado en un estado que no es `calculated`' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, trip_id, state, total_meters, calculated_at, terminal_reason
FROM trip_mileage
WHERE (state = 'calculated' AND (total_meters IS NULL OR calculated_at IS NULL))
   OR (state <> 'calculated' AND total_meters IS NOT NULL)
       ) AS q) AS filas
UNION ALL
SELECT 'K-03' AS id, 'Kilometraje' AS flujo, 'Estado de excepcion sin razon terminal' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, trip_id, state, terminal_reason
FROM trip_mileage
WHERE state IN ('not_calculable', 'calculation_failed') AND terminal_reason IS NULL
       ) AS q) AS filas
UNION ALL
SELECT 'K-04' AS id, 'Kilometraje' AS flujo, 'Pendientes sin camino de salida' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, trip_id, state, attempt_count, next_attempt_at, last_error
FROM trip_mileage
WHERE state = 'pending_calculation'
  AND (next_attempt_at IS NULL OR attempt_count >= 5)
       ) AS q) AS filas
UNION ALL
SELECT 'K-05' AS id, 'Kilometraje' AS flujo, 'Total que no cuadra con la suma de sus tramos' AS invariante,
       (SELECT count(*) FROM (
SELECT m.id, m.trip_id, m.total_meters,
       round(sum(s.distance_meters), 2) AS suma_de_tramos,
       count(s.id) AS tramos
FROM trip_mileage m
JOIN trip_mileage_segment s ON s.trip_mileage_id = m.id AND s.company_id = m.company_id
WHERE m.state = 'calculated'
GROUP BY m.id, m.trip_id, m.total_meters
HAVING round(sum(s.distance_meters), 2) <> round(m.total_meters, 2)
       ) AS q) AS filas
UNION ALL
SELECT 'K-06' AS id, 'Kilometraje' AS flujo, 'Tramo mas corto que la linea recta' AS invariante,
       (SELECT count(*) FROM (
SELECT s.id, s.trip_mileage_id, s.sequence, s.distance_meters, s.haversine_meters,
       s.provider, s.from_event_kind, s.to_event_kind
FROM trip_mileage_segment s
WHERE s.haversine_meters IS NOT NULL
  AND s.distance_meters < s.haversine_meters
       ) AS q) AS filas
UNION ALL
SELECT 'K-07' AS id, 'Kilometraje' AS flujo, 'Secuencia de tramos con hueco o duplicada' AS invariante,
       (SELECT count(*) FROM (
SELECT trip_mileage_id, count(*) AS tramos, min(sequence) AS primero,
       max(sequence) AS ultimo, count(DISTINCT sequence) AS distintos
FROM trip_mileage_segment
GROUP BY trip_mileage_id
HAVING min(sequence) <> 1
    OR max(sequence) <> count(*)
    OR count(DISTINCT sequence) <> count(*)
       ) AS q) AS filas
UNION ALL
SELECT 'K-08' AS id, 'Kilometraje' AS flujo, 'El primer tramo no sale de la salida, o el ultimo no llega' AS invariante,
       (SELECT count(*) FROM (
SELECT s.trip_mileage_id, s.sequence, s.from_event_kind, s.to_event_kind
FROM trip_mileage_segment s
WHERE (s.sequence = 1 AND s.from_event_kind <> 'start_trip')
   OR (s.to_event_kind = 'arrived' AND s.sequence <> (
          SELECT max(o.sequence) FROM trip_mileage_segment o
          WHERE o.trip_mileage_id = s.trip_mileage_id))
       ) AS q) AS filas
UNION ALL
SELECT 'K-10' AS id, 'Kilometraje' AS flujo, 'Provenance que sobrevive al purgado' AS invariante,
       (SELECT count(*) FROM (
SELECT s.id, s.trip_mileage_id, s.sequence,
       (s.from_latitude IS NOT NULL AND s.to_latitude IS NOT NULL) AS tiene_coordenadas,
       (s.from_evidence_level IS NOT NULL AND s.to_evidence_level IS NOT NULL) AS tiene_nivel,
       (s.from_captured_at IS NOT NULL AND s.to_captured_at IS NOT NULL) AS tiene_horas,
       (s.provider IS NOT NULL AND s.method IS NOT NULL) AS tiene_proveedor,
       (s.from_fix_id IS NOT NULL) AS referencia_blanda_viva
FROM trip_mileage_segment s
WHERE s.from_latitude IS NULL OR s.to_latitude IS NULL
   OR s.from_evidence_level IS NULL OR s.to_evidence_level IS NULL
   OR s.from_captured_at IS NULL OR s.to_captured_at IS NULL
   OR s.provider IS NULL OR s.method IS NULL
       ) AS q) AS filas
UNION ALL
SELECT 'X-01' AS id, 'Correlacion offline' AS flujo, 'Clave de accion duplicada dentro de una empresa' AS invariante,
       (SELECT count(*) FROM (
SELECT 'work_session' AS tabla, company_id, client_action_key, count(*) AS cuantas
FROM work_session WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
UNION ALL
SELECT 'trip', company_id, client_action_key, count(*)
FROM trip WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
UNION ALL
SELECT 'trip_purpose_change', company_id, client_action_key, count(*)
FROM trip_purpose_change WHERE client_action_key IS NOT NULL
GROUP BY company_id, client_action_key HAVING count(*) > 1
       ) AS q) AS filas
UNION ALL
SELECT 'H-01' AS id, 'Integridad historica' AS flujo, 'Hechos append-only modificados despues de crearse' AS invariante,
       (SELECT count(*) FROM (
SELECT 'location_fix' AS tabla, id, created_at, updated_at
FROM location_fix WHERE updated_at > created_at + interval '1 second'
UNION ALL
SELECT 'missing_location_event', id, created_at, updated_at
FROM missing_location_event WHERE updated_at > created_at + interval '1 second'
UNION ALL
SELECT 'trip_mileage_segment', id, created_at, updated_at
FROM trip_mileage_segment WHERE updated_at > created_at + interval '1 second'
       ) AS q) AS filas
UNION ALL
SELECT 'D-02' AS id, 'Auditoria' AS flujo, 'Coordenadas filtradas en la traza de auditoria' AS invariante,
       (SELECT count(*) FROM (
SELECT id, company_id, entity_type, action, occurred_at
FROM audit_event
WHERE changes::text ~* '(latitude|longitude|"lat"|"lon")'
       ) AS q) AS filas
) AS puerta
ORDER BY filas DESC, id;
