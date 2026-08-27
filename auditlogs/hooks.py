# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_setup_seniat_user(env):
    """
    Configuración post-instalación para usuario SENIAT.
    - Crea el usuario SENIAT si no existe
    - Asigna el grupo de solo lectura
    - Configura permisos de acceso a modelos
    - Asegura que sea usuario interno activo
    - Concede acceso a menús sin restringir apps públicas (no rompe admin)
    """
    _logger.info(">>> INICIANDO CONFIGURACIÓN USUARIO SENIAT <<<")

    # 1. OBTENER TODAS LAS COMPAÑÍAS (MULTICOMPAÑÍA)
    all_companies = env["res.company"].search([])
    if not all_companies:
        _logger.warning(
            "No se encontró ninguna compañía. Abortando configuración SENIAT."
        )
        return

    main_company = all_companies[0]
    _logger.info(f"Encontradas {len(all_companies)} compañía(s) en el sistema")

    # 2. OBTENER GRUPO SENIAT
    seniat_group = env.ref(
        "auditlogs.group_seniat_readonly", raise_if_not_found=False
    )
    if not seniat_group:
        _logger.warning("No se encontró el grupo SENIAT. Abortando configuración.")
        return

    # ✅ GRUPO DE USUARIO INTERNO
    internal_group = env.ref("base.group_user", raise_if_not_found=False)
    if not internal_group:
        _logger.warning(
            "No se encontró el grupo base.group_user. Abortando configuración."
        )
        return

    # ✅ GRUPO PORTAL (para remover si existe)
    portal_group = env.ref("base.group_portal", raise_if_not_found=False)

    # 3. BUSCAR O CREAR USUARIO SENIAT
    user_seniat = (
        env["res.users"]
        .with_context(active_test=False)
        .search([("login", "=", "seniat@gov.ve")], limit=1)
    )

    if not user_seniat:
        _logger.info("Creando usuario SENIAT...")
        user_seniat = env["res.users"].create(
            {
                "name": "Auditoria SENIAT",
                "login": "seniat@gov.ve",
                "password": "seniat2025",
                "active": True,
                "share": False,  # ✅ FORZAR USUARIO INTERNO (NO PORTAL)
                "company_id": main_company.id,
                # MULTICOMPAÑÍA: Asignar TODAS las compañías al usuario SENIAT
                "company_ids": [(6, 0, all_companies.ids)],
                "groups_id": [
                    (4, internal_group.id),  # ✅ Grupo interno
                    (4, seniat_group.id),    # ✅ Grupo readonly SENIAT
                ],
            }
        )
        _logger.info(f"✓ Usuario SENIAT creado exitosamente (ID: {user_seniat.id})")
        _logger.info(f"✓ Asignadas {len(all_companies)} compañías al usuario SENIAT")
    else:
        _logger.info(
            f"Usuario SENIAT ya existe (ID: {user_seniat.id}). Actualizando configuración..."
        )

        # Preparar valores a actualizar
        update_vals = {}

        # ✅ Asegurar que sea interno (share=False)
        if user_seniat.share:
            update_vals["share"] = False
            _logger.info("✓ Usuario SENIAT será marcado como interno (share=False)")

        # ✅ Asegurar grupo interno
        if internal_group.id not in user_seniat.groups_id.ids:
            update_vals.setdefault("groups_id", [])
            update_vals["groups_id"].append((4, internal_group.id))
            _logger.info("✓ Grupo interno (base.group_user) será asignado")

        # ✅ Asegurar que tenga el grupo readonly SENIAT
        if seniat_group.id not in user_seniat.groups_id.ids:
            update_vals.setdefault("groups_id", [])
            update_vals["groups_id"].append((4, seniat_group.id))
            _logger.info("✓ Grupo SENIAT readonly será asignado")

        # ✅ Si tenía portal, removerlo
        if portal_group and portal_group.id in user_seniat.groups_id.ids:
            update_vals.setdefault("groups_id", [])
            update_vals["groups_id"].append((3, portal_group.id))
            _logger.info("✓ Grupo portal removido si existía")

        # ✅ Asegurar que esté activo
        if not user_seniat.active:
            update_vals["active"] = True
            _logger.info("✓ Usuario SENIAT será reactivado")

        # ✅ MULTICOMPAÑÍA: acceso a TODAS las compañías
        missing_companies = all_companies - user_seniat.company_ids
        if missing_companies:
            update_vals["company_ids"] = [(6, 0, all_companies.ids)]
            _logger.info(f"✓ Se agregarán {len(missing_companies)} compañías faltantes")

        # Aplicar actualizaciones
        if update_vals:
            user_seniat.write(update_vals)
            _logger.info("✓ Usuario SENIAT actualizado exitosamente")

    # 4. LISTA DE MODELOS CON ACCESO DE LECTURAs
    models_to_read = {
        "Contabilidad": [
            "account.move",
            "account.move.line",
            "account.payment",
            "account.journal",
            "account.account",
            "account.bank.statement",
            "account.bank.statement.line",
            "account.analytic.line",
        ],
        "Ventas": ["sale.order", "sale.order.line", "sale.report","sale.order.option"],
        "Compras": ["purchase.order", "purchase.order.line"],
        "Inventario": [
            "stock.picking",
            "stock.move",
            "stock.quant",
            "product.product",
            "product.template",
            "stock.location",
            "stock.warehouse",
            "stock.picking.type",
        ],
        "Sistema": [
            "res.users",
            "res.company",
            "res.partner",
            "res.currency",
            "res.groups",
        ],
        "Auditoria": [
            "auditlog.log",
            "auditlog.log.line",
            "auditlog.rule",
            "auditlog.http.session",
            "auditlog.http.request",
            "auditlog.config",
            "auditlog.autovacuum",
        ],
    }

    # 5. CREAR PERMISOS DE ACCESO A MODELOS (SI NO EXISTEN)
    _logger.info("Verificando permisos de acceso a modelos...")
    created_count = 0

    for area, model_names in models_to_read.items():
        for model_name in model_names:
            model_record = env["ir.model"].search([("model", "=", model_name)], limit=1)

            if model_record:
                existing_access = env["ir.model.access"].search(
                    [
                        ("group_id", "=", seniat_group.id),
                        ("model_id", "=", model_record.id),
                    ],
                    limit=1,
                )

                if not existing_access:
                    env["ir.model.access"].create(
                        {
                            "name": f'access_seniat_{model_name.replace(".", "_")}',
                            "model_id": model_record.id,
                            "group_id": seniat_group.id,
                            "perm_read": True,
                            "perm_write": False,
                            "perm_create": False,
                            "perm_unlink": False,
                        }
                    )
                    created_count += 1
            else:
                _logger.debug(
                    f"Modelo '{model_name}' no encontrado (puede no estar instalado)"
                )

    if created_count > 0:
        _logger.info(f"✓ {created_count} permisos de acceso creados")
    else:
        _logger.info("✓ todos los permisos de acceso ya existen")

    # 6. ASIGNAR ACCESO A MENÚS SIN ROMPER ADMIN
    _logger.info("Configurando acceso a menús (modo seguro)...")

    # Menús raíz de apps que SENIAT debe ver
    root_menu_xmlids = [
        "account.menu_finance",           # Contabilidad
        "account_accountant.menu_accounting", # Contabilidad (Enterprise)
        "sale.sale_menu_root",            # Ventas
        "purchase.menu_purchase_root",    # Compras
        "stock.menu_stock_root",          # Inventario
        "base.menu_administration",       # Configuración (solo Usuarios y Compañías)
        "auditlogs.menu_audit",  # Auditoría
        "contacts.menu_contacts",         # Contactos
    ]

    root_menus = env["ir.ui.menu"]
    for xmlid in root_menu_xmlids:
        m = env.ref(xmlid, raise_if_not_found=False)
        if m:
            root_menus |= m

    if root_menus:
        # Menús hijos de esos roots
        all_related_menus = env["ir.ui.menu"].search(
            [("id", "child_of", root_menus.ids)]
        )

        # Menús de configuración que NO deben tener acceso SENIAT
        config_menu_xmlids = [
            "account.menu_finance_configuration",
            "sale.menu_sale_config",
            "purchase.menu_purchase_config",
            "stock.menu_stock_config_settings",
            "base.menu_config",
            "base.menu_custom",
        ]
        
        config_menus = env["ir.ui.menu"]
        for xmlid in config_menu_xmlids:
            m = env.ref(xmlid, raise_if_not_found=False)
            if m:
                config_menus |= m
                # ✅ Limpiar: remover SENIAT si fue agregado previamente
                if seniat_group.id in m.groups_id.ids:
                    m.write({"groups_id": [(3, seniat_group.id)]})
                    _logger.info(f"✓ Removido grupo SENIAT de menú de configuración: {m.name}")

        granted = 0
        skipped_public = 0
        skipped_config = 0

        for menu in all_related_menus:
            # ✅ Menú sin grupos = público interno → NO tocar
            if not menu.groups_id:
                skipped_public += 1
                continue

            # ✅ Menú de configuración → NO agregar SENIAT
            if menu.id in config_menus.ids:
                skipped_config += 1
                continue

            # ✅ Menú ya restringido → agregar SENIAT sin quitar a nadie
            if seniat_group.id not in menu.groups_id.ids:
                menu.write({"groups_id": [(4, seniat_group.id)]})
                granted += 1

        _logger.info(f"✓ Menús restringidos a los que se agregó SENIAT: {granted}")
        _logger.info(f"✓ Menús públicos que no se tocaron: {skipped_public}")
        _logger.info(f"✓ Menús de configuración excluidos: {skipped_config}")
    else:
        _logger.warning("No se encontraron menús raíz para configurar.")

    _logger.info(">>> CONFIGURACIÓN SENIAT FINALIZADA EXITOSAMENTE <<<")

    # 7. CONFIGURAR REGLAS DE AUDITORÍA OPCIONALES
    setup_optional_audit_rules(env)


def setup_optional_audit_rules(env):
    """
    Crea reglas de auditoría para modelos opcionales solo si existen en la base de datos.
    Esto evita errores de instalación cuando los módulos dependientes no están instalados.
    """
    _logger.info(">>> VERIFICANDO REGLAS DE AUDITORÍA PARA MODELOS OPCIONALES <<<")

    optional_models = {
        "account.asset": "account.asset",
        "account.retention": "account.retention",
        "account.retention.line": "account.retention.line",
        "account.tax.unit": "account.tax.unit",
        "economic.activity": "economic.activity",
        "economic.branch": "economic.branch",
        "debit.note.reason": "debit.note.reason",
        "transfer.reason": "transfer.reason",
    }

    for model_name, rule_name in optional_models.items():
        model_record = env["ir.model"].search([("model", "=", model_name)], limit=1)
        if not model_record:
            _logger.info(
                f"Modelo opcional '{model_name}' no encontrado. Saltando creación de regla."
            )
            continue

        rule_exists = env["auditlog.rule"].search(
            [("model_id", "=", model_record.id)], limit=1
        )
        if rule_exists:
            _logger.debug(f"Regla para '{model_name}' ya existe.")
            continue

        try:
            env["auditlog.rule"].create(
                {
                    "name": rule_name,
                    "model_id": model_record.id,
                    "log_read": False,
                    "log_create": True,
                    "log_write": True,
                    "log_unlink": True,
                    "log_type": "full",
                    "state": "subscribed",
                }
            )
            _logger.info(
                f"✓ Regla de auditoría creada dinámicamente para '{model_name}'"
            )
        except Exception as e:
            _logger.error(f"Error al crear regla para '{model_name}': {str(e)}")
