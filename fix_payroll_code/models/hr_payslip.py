from odoo import models, api

class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_payslip_lines(self):
        """ 
        Llamamos al método original y, si los diccionarios resultantes 
        no traen la llave 'code', la inyectamos desde la regla salarial.
        """
        res = super(HrPayslip, self)._get_payslip_lines()
        
        # Buscamos todas las reglas involucradas de una sola vez para eficiencia
        rule_ids = [line['salary_rule_id'] for line in res if 'salary_rule_id' in line]
        rules = {rule.id: rule.code for rule in self.env['hr.salary.rule'].browse(rule_ids)}

        for line_vals in res:
            if not line_vals.get('code'):
                rule_id = line_vals.get('salary_rule_id')
                # Inyectamos el código de la regla o un fallback por seguridad
                line_vals['code'] = rules.get(rule_id) or 'UNDEFINED'
        
        return res

    def _get_worked_day_lines(self, domain=None, check_out_of_contract=True):
        res = super(HrPayslip, self)._get_worked_day_lines(domain=domain, check_out_of_contract=check_out_of_contract)
        
        if self.contract_id.schedule_pay == 'semi-monthly':
            # Buscar la línea de asistencia estándar (WORK100)
            attendance_line = None
            for line in res:
                we_type = self.env['hr.work.entry.type'].browse(line.get('work_entry_type_id'))
                if we_type.code == 'WORK100':
                    attendance_line = line
                    break
            
            if attendance_line:
                # Sumar días y horas de otras líneas (ausencias, permisos, etc.)
                other_days = sum(line['number_of_days'] for line in res if line != attendance_line)
                other_hours = sum(line['number_of_hours'] for line in res if line != attendance_line)
                
                # Definir metas (15 días y horas de contrato * 2)
                target_hours = self.contract_id.hours_per_week * 2.0
                attendance_line['number_of_days'] = max(0.0, 15.0 - other_days)
                attendance_line['number_of_hours'] = max(0.0, target_hours - other_hours)
                
        return res

    def compute_sheet(self):
        """
        Al calcular la hoja, si el recibo está en borrador/espera y no ha sido editado
        manualmente, refrescamos los worked_days desde las entradas de trabajo para
        garantizar que se aplique la corrección de 15 días y 88 horas automáticamente.
        """
        payslips = self.filtered(lambda slip: slip.state in ['draft', 'verify'] and not slip.edited)
        if payslips:
            payslips.mapped('worked_days_line_ids').unlink()
            payslips._compute_worked_days_line_ids()
        return super(HrPayslip, self).compute_sheet()


class HrPayslipWorkedDays(models.Model):
    _inherit = 'hr.payslip.worked_days'

    def _is_half_day(self):
        self.ensure_one()
        if self.payslip_id.contract_id.schedule_pay == 'semi-monthly':
            # Si el total de horas acumulado en la línea es igual o mayor al objetivo
            # quincenal esperado (ej: 88 o 80 horas), no es jornada reducida/medio día.
            target_hours = self.payslip_id.contract_id.hours_per_week * 2.0
            if self.number_of_hours >= target_hours:
                return False
        return super(HrPayslipWorkedDays, self)._is_half_day()
