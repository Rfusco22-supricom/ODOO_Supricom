{
    "name": "SUPRICOM — Índice de Salud Administrativa",
    "version": "17.0.1.0.0",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "summary": "Configuración de captura para los KPIs de Gestión Administrativa y Cumplimiento",
    "description": """
Índice de Salud Administrativa — captura de datos
=================================================

El panel administrativo (repo Dashboard, issue #8) calcula 32 KPIs. Cuatro áreas
ya tienen fuente en Odoo; dos no la tenían porque nadie registraba el dato en
ninguna parte. Este módulo crea el sitio donde registrarlo, usando módulos
estándar en lugar de modelos nuevos:

* Gestión Administrativa
  - Documentos procesados a tiempo / tiempo de procesamiento -> approval.request
  - Anticipos y viáticos pendientes de legalización          -> hr.expense
  - Cumplimiento de cierre mensual                           -> project.task

* Cumplimiento y Control
  - Operaciones fuera de política  -> approval.request (categoría de excepción)
  - Incidencias abiertas vencidas  -> helpdesk.ticket (equipo con SLA)
  - Pendientes de auditoría        -> project.task
  - Reincidencias                  -> derivadas de las dos anteriores

No define modelos propios a propósito: todo lo que hace falta ya existe en
Odoo, y meter tablas nuevas habría dejado esos datos fuera del ERP.
""",
    "author": "SUPRICOM",
    "depends": [
        "approvals",
        "helpdesk",
        "project",
        "hr_expense",
    ],
    "data": [
        "data/approval_category_data.xml",
        "data/helpdesk_team_data.xml",
        "data/project_data.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
