# Contribuir

## Flujo de ramas

- `main`: produccion protegida.
- `develop`: integracion protegida.
- `feature/m<N>-<nombre>`: una rama por modulo.
- `fix/<nombre>` y `chore/<nombre>`: correcciones y tareas comunes.

No hacer push directo a `main` ni `develop`. Todo cambio entra mediante pull request hacia `develop`, y cada integracion requiere revision cruzada y CI verde.

## Commits

Usar Conventional Commits:

- `feat(m2): agregar gestion de casos`
- `fix(m4): corregir temporalizador`
- `test(m5): probar calculadora de rubrica`
- `chore(base): actualizar configuracion`

## Pull requests

Cada PR debe cubrir una responsabilidad clara, indicar sus RF y conservar la separacion entre router, dependencias, servicios y repositorios.

Los cambios de base pueden ser mantenidos por el responsable A. Los modulos M3, M4, M6 y despliegue pueden ser mantenidos por el responsable B.
