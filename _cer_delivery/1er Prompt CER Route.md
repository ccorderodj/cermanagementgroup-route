Vas a iniciar el proyecto CER Route.

Recibirás dos fuentes de contexto:

1. `CER_ROUTE_RTE01_PACKAGE_V1_0`
2. Un MD adicional con experiencia técnica obtenida previamente en otro desarrollo que utilizó geolocalización.

Trabaja en este orden:

1. Lee primero `00_READ_ME_FIRST.md`.
2. Revisa completamente el baseline funcional V0.7 actualizado y el mockup de referencia.
3. Revisa las instrucciones específicas de `RTE01`.
4. Usa el roadmap únicamente para comprender hacia dónde se dirige el producto; no ejecutes checkpoints posteriores.
5. Después revisa el MD externo de geolocalización.

El MD externo de geolocalización es contexto técnico no vinculante. Utilízalo para identificar tecnologías utilizadas, problemas encontrados, soluciones que funcionaron, limitaciones y problemas no resueltos. No asumas que sus decisiones técnicas deben replicarse en CER Route.

## Objetivo de RTE01

Construir una comprensión técnica completa de CER Route y dejar el proyecto preparado para iniciar su desarrollo de forma controlada.

CER define el producto, sus flujos, comportamiento y resultado esperado.

Tú debes definir y justificar cómo debe implementarse end-to-end.

No reinterpretar ni modificar silenciosamente decisiones funcionales aprobadas.

## Trabajo esperado

Analiza el producto completo y determina, según corresponda:

* arquitectura propuesta;
* estructura del aplicativo;
* experiencia Supervisor Mobile;
* experiencia Admin responsive;
* autenticación y autorización;
* roles y permisos;
* modelo de datos;
* estados y transiciones;
* Work Sessions;
* Trips;
* Activities;
* Change Plan;
* geolocalización;
* cálculo de mileage;
* manejo de permisos de ubicación;
* pérdida y recuperación de señal;
* comportamiento Mobile y suspensión/reanudación;
* vehículos;
* MPG y Fuel Grade;
* Fuel Reference e histórico;
* cálculo estimado de combustible;
* reporting;
* exportación Excel;
* auditoría/logging;
* seguridad;
* validaciones;
* testing;
* deployment;
* riesgos y dependencias.

Utiliza la experiencia externa de geolocalización para mejorar el análisis y evitar repetir problemas conocidos, pero evalúa independientemente qué aplica a CER Route.

## Preparación técnica

Puedes inspeccionar, crear o preparar el entorno de desarrollo necesario para comprender y arrancar correctamente el proyecto, incluyendo repositorio, estructura base, dependencias, configuración local, herramientas de desarrollo, testing o documentación técnica.

Si resulta razonable crear una fundación mínima para validar decisiones técnicas o confirmar que el entorno funciona, puedes hacerlo siempre que no implique ejecutar funcionalmente RTE02 ni adelantar features no autorizados.

No construyas anticipadamente el producto completo.

## Decisiones

Cuando existan varias alternativas técnicas válidas:

* presenta las opciones;
* explica ventajas;
* riesgos;
* impacto;
* recomendación.

Solo eleva a CER decisiones que tengan impacto relevante en producto, arquitectura, seguridad, costo, privacidad, operación o capacidad futura.

No pidas a CER que diseñe la solución técnica.

## Restricciones importantes

* CER Route es un producto independiente de CER ERP.
* El mockup es referencia funcional/UX, no arquitectura de producción.
* El baseline V0.7 actualizado prevalece sobre cualquier diferencia puntual del mockup.
* No introduzcas catálogos, flujos o funcionalidades que CER no haya solicitado.
* No conviertas la aplicación en un sistema de fleet management, CRM, payroll o workforce management.
* No avanzar a RTE02 sin autorización expresa de CER.

## Entregable

Devuelve:

`CER_ROUTE_RTE01_IMPLEMENTATION_REPORT.md`

Utiliza la estructura incluida en:

`05_Deliverable_Expected/CER_ROUTE_RTE01_REPORT_STRUCTURE.md`

El informe debe permitir a CER identificar claramente:

* qué comprendiste del producto;
* qué propones técnicamente;
* qué componentes serán necesarios;
* qué decisiones técnicas tomaste;
* qué decisiones necesitan aprobación;
* qué riesgos existen;
* qué aprendiste del contexto externo de geolocalización;
* qué preparaste en el entorno;
* qué está listo para iniciar desarrollo;
* qué permanece pendiente;
* si RTE01 puede considerarse Completed, Partial o Blocked.

El objetivo final de este checkpoint es que CER pueda revisar tu análisis y decidir si la base técnica está suficientemente alineada para liberar RTE02.
