# CER Staffing System — Architecture & Best Practices

Este documento define las buenas prácticas, principios arquitectónicos y convenciones recomendadas para el desarrollo y mantenimiento de **CER Staffing System**.

## Principios y prácticas

1. Mantener una arquitectura por capas clara: `Router → Service → DAO → Database`.
2. Aplicar Single Responsibility Principle (SRP).
3. Mantener routers ligeros, sin lógica de negocio ni queries directas.
4. Usar Services como capa de casos de uso y reglas de negocio.
5. Mantener DAOs enfocados en persistencia.
6. Preferir composición sobre herencia entre DAOs de dominio.
7. Permitir herencia técnica controlada mediante `BaseDAO`, mixins técnicos y Protocols.
8. Utilizar Dependency Injection.
9. Mantener contratos claros entre capas.
10. Utilizar excepciones específicas de dominio.
11. Centralizar el manejo de errores.
12. Evitar `HTTPException` dentro de DAOs.
13. Considerar Unit of Work para operaciones transaccionales complejas.
14. Definir claramente quién controla `commit`, `rollback`, `flush` y `refresh`.
15. Evitar orquestación entre DAOs; preferir Service/UoW.
16. Crear schemas específicos por intención: Create, Update, Patch, Response, Filter, etc.
17. Separar validación estructural de validación de negocio.
18. No devolver modelos ORM directamente desde la API.
19. Utilizar Enums para estados y valores cerrados.
20. Modelar explícitamente las transiciones de estado.
21. Evitar magic strings y magic numbers.
22. Mantener paginación uniforme.
23. Mantener filtros, búsqueda y ordenamiento consistentes.
24. Prevenir N+1 queries.
25. Cargar solamente los datos necesarios.
26. Crear índices de base de datos basados en queries reales.
27. Aplicar restricciones también en la base de datos.
28. Utilizar migraciones como fuente de verdad del schema.
29. Aplicar Soft Delete solamente cuando sea necesario.
30. Mantener auditoría consistente donde corresponda.
31. Implementar Audit Log para operaciones sensibles.
32. Considerar Strategy Pattern para comportamientos intercambiables.
33. Considerar Factory Pattern para construcción compleja.
34. Mantener Repository/DAO Pattern consistente.
35. Mantener `BaseDAO` pequeño y técnico.
36. Evitar `BaseService` gigantes.
37. Preferir composición sobre herencia en general.
38. Utilizar Protocols cuando una abstracción aporte desacoplamiento real.
39. Centralizar y validar la configuración.
40. Nunca guardar secretos en Git.
41. Utilizar logging estructurado.
42. Implementar Request/Correlation ID.
43. Evitar información sensible en logs.
44. Implementar Health Checks apropiados.
45. Configurar timeouts para servicios externos.
46. Implementar retries de forma controlada.
47. Considerar idempotencia para operaciones críticas.
48. Utilizar Adapter Pattern para integraciones externas.
49. Crear tests unitarios para Services.
50. Crear tests de integración para DAOs.
51. Crear tests HTTP para Routers.
52. No abusar de mocks.
53. Utilizar factories y fixtures de testing.
54. Priorizar cobertura basada en riesgo.
55. Mantener typing estricto.
56. Automatizar linting y formatting.
57. Utilizar pre-commit hooks.
58. Ejecutar CI en Pull Requests.
59. Mantener Pull Requests pequeños y enfocados.
60. Mantener convenciones de nombres consistentes.
61. Considerar organización orientada al dominio cuando el crecimiento lo justifique.
62. Documentar decisiones mediante Architecture Decision Records (ADRs).
63. Definir reglas explícitas de dependencia entre capas.
64. Evitar God Routers, God Services, God DAOs y God BaseDAOs.
65. No dividir archivos únicamente por tamaño; dividir por responsabilidad y cohesión.
66. No implementar patrones por moda.
67. Considerar Architecture Tests para verificar automáticamente las reglas de dependencia.

## Regla para herencia y composición en DAOs

```text
DAO → BaseDAO             ✅
DAO → Technical Mixin     ✅
DAO → Protocol            ✅

EmployeeDAO → AddressDAO  ❌
EmployeeDAO → PayrollDAO  ❌
EmployeeDAO → PositionDAO ❌
```

**Herencia para capacidades técnicas pequeñas y cohesivas. Composición para colaboración entre dominios.**

## Reglas de dependencia

```text
Router  → Service       ✅
Service → DAO           ✅
Service → UnitOfWork    ✅
DAO     → SQLAlchemy    ✅

Router  → DAO           ❌
Router  → SQLAlchemy    ❌
DAO     → Service       ❌
DAO     → FastAPI       ❌
DAO     → otro DAO      ⚠️
Service → HTTPException ⚠️
```

## MUST

- Router no debe acceder directamente a SQLAlchemy.
- Router no debe contener lógica de negocio.
- DAO no debe depender de FastAPI.
- DAO no debe lanzar `HTTPException`.
- Service debe contener casos de uso y reglas de negocio.
- DAOs de dominio no deben utilizar herencia múltiple entre ellos.
- Secretos nunca deben almacenarse en Git.
- Cambios estructurales de DB deben utilizar migraciones.
- Las transacciones deben tener fronteras claramente definidas.
- Las dependencias entre capas deben respetar la arquitectura establecida.

## SHOULD

- Preferir composición sobre herencia.
- Utilizar Dependency Injection.
- Utilizar excepciones de dominio.
- Mantener Response Schemas explícitos.
- Utilizar schemas específicos por operación.
- Utilizar Unit of Work para transacciones complejas.
- Mantener paginación uniforme.
- Utilizar logging estructurado.
- Mantener typing estricto.
- Crear tests por capa.
- Mantener PRs pequeños.
- Documentar decisiones arquitectónicas relevantes.
- Automatizar reglas arquitectónicas mediante CI.

## MAY

- Strategy Pattern.
- Factory Pattern.
- Adapter Pattern.
- Technical Mixins.
- Protocols.
- CQRS.
- Specification Pattern.
- Soft Delete.
- Idempotency.
- Architecture Tests adicionales.

## Principio fundamental

> **Alta cohesión, bajo acoplamiento, responsabilidades claras y dependencias explícitas.**

Los patrones de diseño y principios SOLID deben utilizarse para resolver problemas reales del sistema y no como objetivos independientes.

El objetivo es una arquitectura **fácil de entender, probar, modificar y extender sin introducir efectos secundarios innecesarios**.
