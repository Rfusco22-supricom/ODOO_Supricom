# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # 1. Buscar la estructura salarial "Pago Quincenal"
    structure_quincenal = env['hr.payroll.structure'].search([('name', '=', 'Pago Quincenal')], limit=1)
    if not structure_quincenal:
        structure_quincenal = env['hr.payroll.structure'].browse(5)
        
    if structure_quincenal.exists():
        # A. Desactivar la regla DTM de la estructura "Pago Quincenal"
        dtm_rule_quincenal = env['hr.salary.rule'].search([
            ('code', '=', 'DTM'),
            ('struct_id', '=', structure_quincenal.id)
        ])
        if dtm_rule_quincenal:
            dtm_rule_quincenal.write({'active': False})
            
        # B. Corregir el porcentaje de Seguro Educativo (SE) a 1.25% (0.0125) en Pago Quincenal
        se_rule_quincenal = env['hr.salary.rule'].search([
            ('code', '=', 'SE'),
            ('struct_id', '=', structure_quincenal.id)
        ])
        if se_rule_quincenal:
            se_rule_quincenal.write({
                'amount_python_compute': "result = ((categories['BASIC'] + categories['ALW'])*0.0125)*-1"
            })

        # C. Corregir la regla de Riesgo Profesional en Pago Quincenal (ocultar de recibo y hacer fórmula positiva)
        riesgo_rule = env['hr.salary.rule'].search([
            ('code', '=', 'Riesgo_Profesional'),
            ('struct_id', '=', structure_quincenal.id)
        ])
        if riesgo_rule:
            riesgo_rule.write({
                'name': 'Riesgo Profesional',
                'appears_on_payslip': False,
                'amount_python_compute': "result = (categories['BASIC'] + categories['ALW']) * 0.021"
            })
            
    # 2. Obtener referencias de categorías por seguridad
    alw_category = env.ref('hr_payroll.ALW', raise_if_not_found=False)
    ded_category = env.ref('hr_payroll.DED', raise_if_not_found=False)
    net_category = env.ref('hr_payroll.NET', raise_if_not_found=False)
    comp_category = env.ref('hr_payroll.COMP', raise_if_not_found=False)
    
    alw_id = alw_category.id if alw_category else env['hr.salary.rule.category'].search([('code', '=', 'ALW')], limit=1).id
    ded_id = ded_category.id if ded_category else env['hr.salary.rule.category'].search([('code', '=', 'DED')], limit=1).id
    net_id = net_category.id if net_category else env['hr.salary.rule.category'].search([('code', '=', 'NET')], limit=1).id
    comp_id = comp_category.id if comp_category else env['hr.salary.rule.category'].search([('code', '=', 'COMP')], limit=1).id


    # 3. Crear o buscar la nueva estructura salarial "Décimo Tercer Mes"
    structure_d3m = env['hr.payroll.structure'].search([('name', '=', 'Décimo Tercer Mes')], limit=1)
    if not structure_d3m:
        struct_vals = {
            'name': 'Décimo Tercer Mes',
            'type_id': structure_quincenal.type_id.id if structure_quincenal else env['hr.payroll.structure.type'].search([], limit=1).id,
            'country_id': structure_quincenal.country_id.id if structure_quincenal and structure_quincenal.country_id else False,
        }
        structure_d3m = env['hr.payroll.structure'].create(struct_vals)
        
    # 4. Crear o actualizar las reglas salariales asociadas a "Décimo Tercer Mes"
    
    # REGLA A: Décimo Tercer Mes (Asignación DTM)
    dtm_rule = env['hr.salary.rule'].search([('code', '=', 'DTM'), ('struct_id', '=', structure_d3m.id)], limit=1)
    dtm_code = (
        "# 1. Definir el rango de los últimos 4 meses según la partida\n"
        "fecha_fin = payslip.date_to\n"
        "fecha_inicio = fecha_fin - relativedelta(months=4)\n\n"
        "# 2. Buscar todos los recibos confirmados del empleado en ese rango\n"
        "nominas_anteriores = payslip.env['hr.payslip'].search([\n"
        "    ('employee_id', '=', employee.id),\n"
        "    ('date_to', '>=', fecha_inicio),\n"
        "    ('date_to', '<=', fecha_fin),\n"
        "    ('state', '=', 'done')\n"
        "])\n\n"
        "# 3. Sumar el 'Salario Bruto' (GROSS) de esas nóminas\n"
        "total_ganado = sum(nominas_anteriores.mapped('line_ids').filtered(lambda l: l.code == 'GROSS').mapped('total'))\n\n"
        "# 4. El cálculo del DTM es 1/12 (8.33%) del salario acumulado\n"
        "result = total_ganado / 12"
    )
    dtm_vals = {
        'name': 'Décimo Tercer Mes',
        'code': 'DTM',
        'category_id': alw_id,
        'sequence': 10,
        'amount_select': 'code',
        'amount_python_compute': dtm_code,
        'struct_id': structure_d3m.id,
        'active': True,
    }
    if dtm_rule:
        dtm_rule.write(dtm_vals)
    else:
        env['hr.salary.rule'].create(dtm_vals)
        
    # REGLA B: Seguro Social DTM (Deducción 7.25%)
    ss_dtm_rule = env['hr.salary.rule'].search([('code', '=', 'SS_DTM'), ('struct_id', '=', structure_d3m.id)], limit=1)
    ss_dtm_code = (
        "# Seguro Social con tasa del 7.25% sobre el Décimo Tercer Mes\n"
        "result = (categories['ALW'] * 0.0725) * -1"
    )
    ss_dtm_vals = {
        'name': 'Seguro Social DTM',
        'code': 'SS_DTM',
        'category_id': ded_id,
        'sequence': 20,
        'amount_select': 'code',
        'amount_python_compute': ss_dtm_code,
        'struct_id': structure_d3m.id,
        'active': True,
    }
    if ss_dtm_rule:
        ss_dtm_rule.write(ss_dtm_vals)
    else:
        env['hr.salary.rule'].create(ss_dtm_vals)
        
    # REGLA C: Seguro Social Patronal DTM (Aporte Empresa 10.75%)
    ss_patronal_dtm_rule = env['hr.salary.rule'].search([('code', '=', 'SS_Patronal_DTM'), ('struct_id', '=', structure_d3m.id)], limit=1)
    ss_patronal_dtm_code = (
        "# Seguro Social Patronal con tasa del 10.75% sobre el Décimo Tercer Mes\n"
        "result = categories['ALW'] * 0.1075"
    )
    ss_patronal_dtm_vals = {
        'name': 'Seguro Social Patronal DTM',
        'code': 'SS_Patronal_DTM',
        'category_id': comp_id,
        'sequence': 25,
        'amount_select': 'code',
        'amount_python_compute': ss_patronal_dtm_code,
        'struct_id': structure_d3m.id,
        'active': True,
        'appears_on_payslip': False,
    }
    if ss_patronal_dtm_rule:
        ss_patronal_dtm_rule.write(ss_patronal_dtm_vals)
    else:
        env['hr.salary.rule'].create(ss_patronal_dtm_vals)
        
    # REGLA D: Salario Neto (NET)
    net_rule = env['hr.salary.rule'].search([('code', '=', 'NET'), ('struct_id', '=', structure_d3m.id)], limit=1)
    net_code = (
        "# Salario neto es la suma de asignaciones y deducciones\n"
        "result = categories['ALW'] + categories['DED']"
    )
    net_vals = {
        'name': 'Salario Neto',
        'code': 'NET',
        'category_id': net_id,
        'sequence': 100,
        'amount_select': 'code',
        'amount_python_compute': net_code,
        'struct_id': structure_d3m.id,
        'active': True,
    }
    if net_rule:
        net_rule.write(net_vals)
    else:
        env['hr.salary.rule'].create(net_vals)

