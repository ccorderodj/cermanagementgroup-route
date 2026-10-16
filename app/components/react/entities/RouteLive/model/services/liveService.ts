import { $api, parseApi } from '@/shared/api';
import { liveTodaySchema, type LiveToday } from '../types';

/**
 * Una sola lectura para toda la pantalla.
 *
 * No es comodidad: Today / Live se refresca solo cada treinta segundos, y
 * reconstruirlo desde varios endpoints multiplicaría ese tráfico y obligaría al
 * navegador a recomponer reglas que son del dominio — qué significa "On Route",
 * qué millas cuentan, qué día es hoy.
 */
export async function fetchTodayLive(): Promise<LiveToday> {
    const response = await $api.get('/live/today');
    return parseApi(liveTodaySchema, response.data, 'fetchTodayLive');
}
