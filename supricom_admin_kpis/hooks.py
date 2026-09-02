# -*- coding: utf-8 -*-
"""
Configuración que consumen los KPIs de "Gestión Administrativa" y
"Cumplimiento y Control" del Dashboard (lib/administracion/gestionAdministrativa.ts
y cumplimientoControl.ts). Todo lo de aquí se armó y probó a mano vía API
JSON-RPC contra un ambiente QA de Odoo.sh antes de escribirlo como módulo —
ver docs/issue-8-gestion-administrativa.md para el detalle de esa prueba.

Se usa `post_init_hook` en vez de archivos de datos XML porque la config es
la MISMA estructura repetida por compañía (categorías, equipo, SLA), y un
loop en Python es más corto y más fácil de mantener que 6 copias casi
idénticas de cada `<record>`.

Idempotente a propósito: cada función revisa `ir.model.data` antes de crear,
así que correr `-u supricom_admin_kpis` de nuevo (o instalarlo dos veces por
error) no duplica nada — simplemente no hace nada donde ya existe.
"""

# Compañías donde corre este piloto (issue #8 del Dashboard). Son las 6 de
# las 7 que tiene la base: DISTRIBUIDORA SUPRICOM, CA (id 3) queda afuera a
# propósito — el usuario pidió explícitamente no incluirla, no es un olvido.
COMPANY_IDS = [1, 2, 7, 9, 10, 11]

# Horas hasta la etapa "Solved" para el SLA de incidencias administrativas.
SLA_HORAS = 48.0

MODULO = "supricom_admin_kpis"


def _xmlid_existe(env, nombre):
    return bool(
        env["ir.model.data"].search(
            [("module", "=", MODULO), ("name", "=", nombre)], limit=1
        )
    )


def _registrar_xmlid(env, nombre, modelo, res_id):
    env["ir.model.data"].create(
        {
            "name": nombre,
            "module": MODULO,
            "model": modelo,
            "res_id": res_id,
            "noupdate": True,
        }
    )


def post_init_hook(env):
    _crear_categorias_approval(env)
    _crear_equipos_helpdesk(env)
    _crear_proyectos(env)


def _crear_categorias_approval(env):
    """Categorías 'Solicitud Administrativa' y 'Excepción de Política', una
    por sede. approval.category exige company_id — no admite 'todas las
    compañías' — por eso se duplica en vez de crear una sola vez.
    """
    Categoria = env["approval.category"]

    # Verificado contra las categorías reales ya probadas en QA: los
    # defaults de Odoo para estos campos NO son estos (has_* nace en "no",
    # requirer_document nace en "optional") — hay que fijarlos a mano para
    # que el flujo de aprobación exija adjuntar soporte, igual que se probó.
    campos_comunes = {
        "has_date": "optional",
        "has_period": "optional",
        "has_quantity": "optional",
        "has_amount": "optional",
        "has_reference": "optional",
        "has_partner": "optional",
        "has_payment_method": "optional",
        "has_location": "optional",
        "has_product": "optional",
        "requirer_document": "required",
        "approval_minimum": 1,
    }

    categorias = [
        ("Solicitud Administrativa", "categoria_solicitud_administrativa"),
        ("Excepción de Política", "categoria_operaciones_fuera_politica"),
    ]

    for company_id in COMPANY_IDS:
        for nombre, prefijo in categorias:
            xmlid = f"{prefijo}_empresa_{company_id}"
            if _xmlid_existe(env, xmlid):
                continue
            registro = Categoria.create(
                {"name": nombre, "company_id": company_id, **campos_comunes}
            )
            _registrar_xmlid(env, xmlid, "approval.category", registro.id)


def _crear_equipos_helpdesk(env):
    """Equipo 'Incidencias Administrativas' + su SLA, uno por sede."""
    Team = env["helpdesk.team"]
    Sla = env["helpdesk.sla"]
    stage_solved = env.ref("helpdesk.stage_solved")

    for company_id in COMPANY_IDS:
        xmlid_equipo = f"equipo_incidencias_administrativas_empresa_{company_id}"
        if _xmlid_existe(env, xmlid_equipo):
            continue

        equipo = Team.create(
            {
                "name": "Incidencias Administrativas",
                "company_id": company_id,
                "use_alias": False,
                "use_sla": True,
            }
        )
        # Verificado en QA: Odoo provisiona un alias de correo real al crear
        # el equipo AUNQUE use_alias=False venga en el create — hace falta
        # este write aparte después de creado para de verdad dejarlo sin
        # alias. No es redundante, es la única forma que funciona.
        equipo.write({"alias_name": False})
        _registrar_xmlid(env, xmlid_equipo, "helpdesk.team", equipo.id)

        Sla.create(
            {
                "name": "Resolución de incidencias administrativas",
                "team_id": equipo.id,
                "stage_id": stage_solved.id,
                # Prioridad "0" = la más baja = aplica a cualquier ticket,
                # sin importar la prioridad que le pongan.
                "priority": "0",
                "time": SLA_HORAS,
                "company_id": company_id,
            }
        )


def _crear_proyectos(env):
    """Proyectos compartidos 'Cierre Mensual' y 'Auditoría Interna', cada
    uno con sus etapas 'Por hacer'/'Cerrado' y la etiqueta 'Reincidencia'.
    company_id=False porque project.project sí admite 'todas las compañías'
    — a diferencia de approval.category/helpdesk.team, no hace falta
    duplicarlos por sede.
    """
    Project = env["project.project"]
    Stage = env["project.task.type"]
    Tag = env["project.tags"]

    if not _xmlid_existe(env, "tag_reincidencia"):
        tag = Tag.create({"name": "Reincidencia"})
        _registrar_xmlid(env, "tag_reincidencia", "project.tags", tag.id)

    proyectos = [
        ("proyecto_cierre_mensual", "Cierre Mensual", "cierre"),
        ("proyecto_auditoria_interna", "Auditoría Interna", "auditoria"),
    ]

    for xmlid_proyecto, nombre, prefijo_stage in proyectos:
        if _xmlid_existe(env, xmlid_proyecto):
            proyecto_id = env.ref(f"{MODULO}.{xmlid_proyecto}").id
        else:
            proyecto = Project.create({"name": nombre, "company_id": False})
            _registrar_xmlid(env, xmlid_proyecto, "project.project", proyecto.id)
            proyecto_id = proyecto.id

        # Bug real encontrado en la prueba de punta a punta: sin una etapa
        # inicial con sequence menor que "Cerrado", cualquier tarea nueva
        # nace YA cerrada. "Por hacer" tiene que existir antes de cargar
        # ninguna tarea real.
        xmlid_por_hacer = f"stage_{prefijo_stage}_por_hacer"
        if not _xmlid_existe(env, xmlid_por_hacer):
            stage = Stage.create(
                {
                    "name": "Por hacer",
                    "sequence": 0,
                    "fold": False,
                    "project_ids": [(4, proyecto_id)],
                }
            )
            _registrar_xmlid(env, xmlid_por_hacer, "project.task.type", stage.id)

        xmlid_cerrado = f"stage_{prefijo_stage}_cerrado"
        if not _xmlid_existe(env, xmlid_cerrado):
            stage = Stage.create(
                {
                    "name": "Cerrado",
                    "sequence": 1,
                    "fold": True,
                    "project_ids": [(4, proyecto_id)],
                }
            )
            _registrar_xmlid(env, xmlid_cerrado, "project.task.type", stage.id)
