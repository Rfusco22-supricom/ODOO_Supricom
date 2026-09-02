# supricom_admin_kpis

Configuración (sin modelos ni vistas nuevas) que necesitan los KPIs de
**Gestión Administrativa** y **Cumplimiento y Control** del panel
administrativo (Dashboard, issue #8) — `lib/administracion/` en ese repo.

## Qué crea

Por cada compañía en `hooks.COMPANY_IDS` (1, 2, 7, 9, 10, 11 — **sin** la
compañía 3 "DISTRIBUIDORA SUPRICOM, CA", decisión explícita del usuario):

- Categoría de Approvals **"Solicitud Administrativa"**.
- Categoría de Approvals **"Excepción de Política"**.
- Equipo de Helpdesk **"Incidencias Administrativas"**, sin alias de correo
  real, con su SLA (48h hasta la etapa "Solved", prioridad mínima = aplica
  a todo).

Una sola vez, compartido entre todas las sedes (`company_id=False`):

- Proyecto **"Cierre Mensual"** con etapas "Por hacer"/"Cerrado".
- Proyecto **"Auditoría Interna"** con etapas "Por hacer"/"Cerrado".
- Etiqueta de proyecto **"Reincidencia"**.

Cada registro queda anotado en `ir.model.data` (módulo `supricom_admin_kpis`)
con un nombre externo estable — `<prefijo>_empresa_<company_id>` para lo que
es por sede, sin sufijo para lo compartido. El Dashboard resuelve estos ids
por ese nombre (`lib/administracion/odooRefs.ts`), nunca por texto, porque
`name` es un campo traducible.

## Qué NO hace (a propósito)

**No toca "anticipos y viáticos pendientes de legalización".** El diseño
original de ese KPI asumía `hr.expense.sheet` (el módulo de Gastos), pero
Administración confirmó que eso se lleva por **asiento contable directo**
contra una cuenta de activo ya existente en el plan de cuentas, una por
sede:

| Sede     | Cuenta                          | Código        | `reconcile` |
|----------|----------------------------------|---------------|-------------|
| Panamá   | CxC Empleados                     | `1.01.04.001` | No          |
| Caracas  | Prestamos a Empleados              | `1.01.05.103` | No          |
| Valencia | Prestamos Empleados                | `1.01.05.008` | Sí          |

Se verificó con movimientos reales (ej. Caracas: un empleado con anticipo de
$290, pagando cuotas de $40-50/mes, saldo pendiente $240) que el patrón real
es: débito al dar el anticipo, crédito en cada cuota pagada, el saldo baja
solo. Eso es lo que Administración llama "conciliar" — no requiere el
matching formal de Odoo (`reconcile=True`), así que el Dashboard lo mide
directo como **saldo (débito − crédito) por contacto** en esas 3 cuentas
(`lib/administracion/gestionAdministrativa.ts`, `fetchLegalizacionPendiente`),
sin necesitar nada de este módulo ni de `hr_expense`.

Caveat real, solo en Panamá: sus movimientos no traen `partner_id` asignado
(el nombre del empleado solo está en el texto de la descripción), así que
ahí el KPI sale como un total agregado por sede en vez de por empleado,
hasta que Administración empiece a asignar el contacto al capturar el
asiento.

**No incluye la compañía 3** ("DISTRIBUIDORA SUPRICOM, CA") — pedido
explícito del usuario, no un olvido.

## Por qué existe este módulo

Todo esto se armó y probó primero a mano, vía API JSON-RPC directa, contra
un ambiente QA real de Odoo.sh (clon de producción) — para no depender de
que alguien más revisara/instalara código en este repo mientras se
investigaba si el enfoque servía. Ya verificado de punta a punta:

1. Se creó una `approval.request` de prueba y un `helpdesk.ticket` de
   prueba (compañía Panamá).
2. Se confirmó que el Dashboard los reflejó correctamente ("Documentos
   procesados a tiempo" y "Incidencias abiertas vencidas" ambos en verde).
3. Se borraron los registros de prueba.

Con eso confirmado, se escribió este módulo para que la configuración quede
en control de versiones y sobreviva a que Odoo.sh reconstruya un ambiente
(pasó dos veces durante la investigación: un QA completo desapareció y fue
reemplazado por un clon nuevo de producción, perdiendo toda la config hecha
a mano) — instalar/actualizar este módulo la vuelve a crear sola.

## Instalación

```
Ajustes → Apps → Actualizar lista de aplicaciones → buscar "KPIs de Gestión
Administrativa y Cumplimiento" → Instalar
```

Es idempotente: instalarlo dos veces, o correr `-u supricom_admin_kpis`, no
duplica nada — cada función revisa `ir.model.data` antes de crear.

## Pendiente (del lado de Administración, no de este módulo)

- Cargar el checklist real de tareas del proyecto "Cierre Mensual" (hoy
  queda vacío, listo para recibir tareas reales).
- Definir la meta mensual de cobranza y el saldo mínimo operativo en $
  (viven como parámetros en el Dashboard, no en Odoo).
- Asignar el contacto (`partner_id`) al capturar los asientos de anticipos
  en Panamá, para que ese KPI deje de salir agregado y empiece a
  desglosarse por empleado.

## Estado

Instalado y probado solo en QA (`supricom2-qa-37385118` al momento de
escribir esto). **Todavía no se decidió si/cuándo instalar en producción**
— pendiente de resolver los puntos de arriba primero.
