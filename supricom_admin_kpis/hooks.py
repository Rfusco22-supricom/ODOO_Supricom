# -*- coding: utf-8 -*-
"""
Duplicar por compañía las categorías de Approvals y el equipo de Helpdesk
(issue #8, "Gestión Administrativa" / "Cumplimiento y Control" del Dashboard).

Por qué existe este hook y no basta con el XML de datos
---------------------------------------------------------
`approval.category` y `helpdesk.team` exigen una compañía obligatoria
(`company_id` es `required=True` en ambos modelos) — a diferencia de
`project.project`, que sí admite "todas las compañías" (`company_id` vacío).
Sin esto, las categorías "Solicitud Administrativa"/"Excepción de Política" y
el equipo "Incidencias Administrativas" que crea `data/approval_category_data.xml`
y `data/helpdesk_team_data.xml` solo existirían para UNA compañía — la que esté
activa cuando se instale el módulo — y el resto de sedes ni siquiera podría
verlos en su desplegable.

Este hook toma esos registros "plantilla" (los que crea el XML) y los clona
para cada compañía adicional que ya exista en la instancia, usando
`.copy()` para no reconstruir campo por campo (conserva la imagen de la
categoría, la config del equipo, etc.).

Cómo los encuentra el Dashboard en tiempo de ejecución
--------------------------------------------------------
Cada copia se registra en `ir.model.data` con un id externo que codifica la
compañía: `<id_externo_base>_empresa_<company_id>`. El Dashboard resuelve por
prefijo (`name like '<id_externo_base>_empresa_%'`) y arma un mapa
`company_id -> res_id` en runtime — así no hace falta que el código conozca
de antemano los ids de compañía de esta instancia (funcionan igual 1, 3 o 10
compañías, y una compañía nueva que se agregue después solo necesita correr
este mismo hook otra vez).

Reejecutar tras agregar una compañía nueva
--------------------------------------------
`post_init_hook` solo corre en la instalación inicial del módulo, no en cada
actualización. Si se agrega una sede nueva después, hay que volver a llamar
`post_init_hook(env)` a mano (por `odoo-bin shell`) para que esa sede también
tenga su categoría/equipo — de lo contrario, sus usuarios no verían estas
opciones y sus KPIs quedarían sin fuente para esa sede.
"""


def _clonar_por_compania(env, id_externo_base, modelo, defaults_extra=None):
    """Devuelve {company_id: res_id} con una copia del registro `id_externo_base`
    por cada res.company activa. Idempotente: si ya existe el id externo para
    una compañía, no la vuelve a crear."""
    IrModelData = env["ir.model.data"]
    original = env.ref(f"supricom_admin_kpis.{id_externo_base}")
    companias = env["res.company"].search([])

    mapa = {}
    for compania in companias:
        nombre_externo = f"{id_externo_base}_empresa_{compania.id}"
        existente = IrModelData.search(
            [("module", "=", "supricom_admin_kpis"), ("name", "=", nombre_externo)],
            limit=1,
        )
        if existente:
            mapa[compania.id] = existente.res_id
            continue

        if compania.id == original.company_id.id:
            registro = original
        else:
            defaults = {"company_id": compania.id, "name": original.name}
            if defaults_extra:
                defaults.update(defaults_extra(compania))
            registro = original.copy(defaults)

        IrModelData.create(
            {
                "module": "supricom_admin_kpis",
                "name": nombre_externo,
                "model": modelo,
                "res_id": registro.id,
                "noupdate": True,
            }
        )
        mapa[compania.id] = registro.id

    return mapa


def post_init_hook(env):
    _clonar_por_compania(
        env, "categoria_solicitud_administrativa", "approval.category"
    )
    _clonar_por_compania(
        env, "categoria_operaciones_fuera_politica", "approval.category"
    )
    mapa_equipos = _clonar_por_compania(
        env,
        "equipo_incidencias_administrativas",
        "helpdesk.team",
        # helpdesk.team autogenera un alias de correo si no se le da uno; al
        # copiar mas de un equipo en la misma transaccion el sufijo
        # automatico ("-copy-") choca entre si (UserError de alias
        # duplicado). Se le da uno explicito y unico por compañía.
        defaults_extra=lambda c: {
            "alias_name": f"incidencias-administrativas-empresa-{c.id}"
        },
    )

    # El SLA no se clona por compañía en el bucle generico de arriba porque
    # su company_id es un related de team_id.company_id (no un campo propio):
    # basta con apuntar cada copia al equipo de su compañía correspondiente.
    IrModelData = env["ir.model.data"]
    sla_original = env.ref("supricom_admin_kpis.sla_incidencias_administrativas")
    for company_id, team_id in mapa_equipos.items():
        nombre_externo = f"sla_incidencias_administrativas_empresa_{company_id}"
        if IrModelData.search(
            [("module", "=", "supricom_admin_kpis"), ("name", "=", nombre_externo)]
        ):
            continue
        if team_id == sla_original.team_id.id:
            registro = sla_original
        else:
            registro = sla_original.copy(
                {"team_id": team_id, "name": sla_original.name}
            )
        IrModelData.create(
            {
                "module": "supricom_admin_kpis",
                "name": nombre_externo,
                "model": "helpdesk.sla",
                "res_id": registro.id,
                "noupdate": True,
            }
        )
