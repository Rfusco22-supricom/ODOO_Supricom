{
    'name': 'KPIs de Gestión Administrativa y Cumplimiento (Dashboard)',
    'version': '17.0.1.0.0',
    'category': 'Administration',
    'summary': 'Configuración de Approvals/Helpdesk/Project que consume el panel administrativo (Dashboard) para el issue #8.',
    'description': """
KPIs de Gestión Administrativa y Cumplimiento y Control (Dashboard)
====================================================================

No agrega modelos ni vistas nuevas. Crea, por compañía, la configuración
mínima que el Dashboard (lib/administracion/) necesita para leer estos
KPIs sin depender de un módulo custom más grande:

- Categorías de Approvals "Solicitud Administrativa" y "Excepción de
  Política", una por sede (aprovechan el módulo `approvals` ya instalado).
- Equipo de Helpdesk "Incidencias Administrativas" + su SLA (48h hasta la
  etapa "Solved"), una por sede.
- Proyectos compartidos "Cierre Mensual" y "Auditoría Interna", cada uno
  con sus etapas "Por hacer"/"Cerrado" y la etiqueta "Reincidencia".

Cada registro queda anotado en `ir.model.data` bajo este módulo con el
nombre externo `<prefijo>_empresa_<company_id>` (o sin sufijo para los
registros compartidos) — es la clave que usa el Dashboard para resolverlos
sin depender de nombres traducibles. Ver `hooks.py` para el detalle y
`lib/administracion/odooRefs.ts` del lado del Dashboard.

Deliberadamente NO incluye la compañía "DISTRIBUIDORA SUPRICOM, CA" (id 3)
— decisión explícita de Administración, no un olvido.

Deliberadamente NO toca "anticipos y viáticos pendientes de legalización":
Administración confirmó que eso se lleva por asiento contable directo
contra una cuenta de activo por sede (ya existente en el plan de cuentas),
no por Approvals/Helpdesk ni por hr.expense. El Dashboard lo lee
directamente de `account.move.line`, sin necesitar nada de este módulo.

Probado de punta a punta (crear una solicitud + un ticket de prueba y
confirmar que el Dashboard los reflejaba) en un ambiente QA de Odoo.sh
antes de proponer este módulo. Ver README.md de este módulo para el
detalle completo de esa investigación y esa prueba.
    """,
    'author': 'Supricom',
    'license': 'LGPL-3',
    'depends': [
        'approvals',
        'helpdesk',
        'project',
    ],
    'data': [],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
