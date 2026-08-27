from odoo import models, api, _
from odoo.exceptions import UserError

class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    def write(self, vals):
        # Códigos de secuencia fiscal que deben protegerse
        # l10n_nro_control_sale: Secuencia estándar del módulo l10n_ve_full
        # g3c.nro.ctrl: Secuencia usada por g3c_ve_homologacion
        # g3c.customer.invoice.number: Secuencia de número de factura (si aplica)
        protected_codes = ['l10n_nro_control_sale', 'g3c.nro.ctrl', 'g3c.customer.invoice.number']
        
        # Verificar si estamos intentando modificar el siguiente número
        if 'number_next' in vals or 'number_next_actual' in vals:
            for seq in self:
                if seq.code in protected_codes:
                    # Obtener el nuevo valor propuesto
                    new_next = vals.get('number_next') or vals.get('number_next_actual')
                    
                    # Obtener el valor actual
                    current_next = seq.number_next_actual
                    
                    if new_next < current_next:
                        raise UserError(_(
                            "Restricción de Seguridad (Homologación): No está permitido disminuir el número "
                            "de secuencia para controles fiscales ('%s').\n\n"
                            "Valor Actual: %s\n"
                            "Valor Intentado: %s\n\n"
                            "Disminuir la secuencia puede causar duplicidad de documentos legales. "
                            "Si necesita corregir, contacte al administrador del sistema."
                        ) % (seq.code, current_next, new_next))

        return super(IrSequence, self).write(vals)
