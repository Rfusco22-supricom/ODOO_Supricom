from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.constrains('taxes_id', 'supplier_taxes_id')
    def _check_company_taxes(self):
        for record in self.sudo():
            # La compañía que importa es la del producto o la actual si es compartido
            company = record.company_id or self.env.company

            # Si el producto tiene compañía asignada, validar que sus impuestos coincidan
            if record.company_id:
                all_taxes = (record.taxes_id | record.supplier_taxes_id)
                wrong_taxes = all_taxes.filtered(lambda t: t.company_id and t.company_id != company)
                if wrong_taxes:
                    raise ValidationError(_("Acuerdo Fiscal: El producto no puede tener impuestos de otras compañías (%s). "
                                            "Asegúrese de seleccionar solo impuestos pertenecientes a %s.") % 
                                            (", ".join(wrong_taxes.mapped('name')), company.name))

            # Si la homologación está activa, validar impuestos
            if company.homologacion_activa:
                # Excepción: productos IGTF no requieren esta validación
                product_name = (record.name or '').upper()
                product_ref = (record.default_code or '').upper()
                if 'IGTF' in product_name or 'IGTF' in product_ref:
                    continue

                # Validar impuestos de VENTA (cliente) - exactamente 1 por compañía activa
                active_sale_taxes = record.taxes_id.filtered(lambda t: t.company_id == company)
                if len(active_sale_taxes) == 0:
                    raise ValidationError(
                        _("Acuerdo Fiscal: El producto '%s' debe tener exactamente un impuesto de venta (cliente) "
                          "configurado para %s.") % (record.name, company.name))
                if len(active_sale_taxes) > 1:
                    raise ValidationError(
                        _("Acuerdo Fiscal: No está permitido configurar más de un impuesto de venta (cliente) "
                          "por producto en %s. El producto '%s' tiene %d.") % (company.name, record.name, len(active_sale_taxes)))

                # Validar impuestos de COMPRA (proveedor) - exactamente 1 por compañía activa
                active_purchase_taxes = record.supplier_taxes_id.filtered(lambda t: t.company_id == company)
                if len(active_purchase_taxes) == 0:
                    raise ValidationError(
                        _("Acuerdo Fiscal: El producto '%s' debe tener exactamente un impuesto de compra (proveedor) "
                          "configurado para %s.") % (record.name, company.name))
                if len(active_purchase_taxes) > 1:
                    raise ValidationError(
                        _("Acuerdo Fiscal: No está permitido configurar más de un impuesto de compra (proveedor) "
                          "por producto en %s. El producto '%s' tiene %d.") % (company.name, record.name, len(active_purchase_taxes)))

    def write(self, vals):
        # Para productos compartidos (sin compañía):
        # 1. Usar sudo para evitar record rules de account.tax
        # 2. Preservar impuestos de otras compañías que el usuario no ve
        tax_field_names = ['taxes_id', 'supplier_taxes_id']
        has_tax_fields = any(f in vals for f in tax_field_names)

        if has_tax_fields:
            allowed_company_ids = self.env.companies.ids
            for record in self:
                if not record.company_id:
                    new_vals = dict(vals)
                    for fname in tax_field_names:
                        if fname in new_vals:
                            # Obtener impuestos actuales de OTRAS compañías (ocultos al usuario)
                            current_taxes = record.sudo()[fname]
                            hidden_tax_ids = current_taxes.filtered(
                                lambda t: t.company_id.id not in allowed_company_ids
                            ).ids
                            # Procesar el comando Many2many
                            cmds = new_vals[fname]
                            if cmds and isinstance(cmds, list):
                                for cmd in cmds:
                                    if isinstance(cmd, (list, tuple)) and cmd[0] == 6:
                                        # Comando (6, 0, ids) = reemplazar todo
                                        # Agregar los impuestos ocultos de vuelta
                                        visible_ids = list(cmd[2])
                                        merged_ids = list(set(visible_ids + hidden_tax_ids))
                                        new_vals[fname] = [(6, 0, merged_ids)]
                                        break
                    super(ProductTemplate, record.sudo()).write(new_vals)
                else:
                    super(ProductTemplate, record).write(vals)
            return True
        return super(ProductTemplate, self).write(vals)

    def read(self, fields=None, load='_classic_read'):
        result = super(ProductTemplate, self.sudo()).read(fields, load)

        # Filtrar impuestos visibles: solo mostrar los de las compañías activas del usuario
        tax_fields = {'taxes_id', 'supplier_taxes_id'}
        if fields and tax_fields & set(fields):
            allowed_company_ids = self.env.companies.ids
            Tax = self.env['account.tax'].sudo()
            for row in result:
                for fname in tax_fields:
                    if fname in row and row[fname]:
                        # row[fname] es una lista de IDs
                        all_tax_ids = row[fname]
                        if all_tax_ids:
                            taxes = Tax.browse(all_tax_ids)
                            visible_taxes = taxes.filtered(
                                lambda t: t.company_id.id in allowed_company_ids
                            )
                            row[fname] = visible_taxes.ids
        return result


    @api.constrains('list_price')
    def _check_price_positive(self):
        for record in self:
            if record.company_id.homologacion_activa and record.list_price <= 0:
                raise ValidationError(_("Acuerdo Fiscal: El precio de venta del producto debe ser mayor a cero."))

class AccountTax(models.Model):
    _inherit = 'account.tax'

    def write(self, vals):
        # Bloquear la modificación de la alícuota correcta
        if self.company_id.homologacion_activa and ('amount' in vals or 'amount_type' in vals):
            raise UserError(_("Acuerdo Fiscal: No está permitido modificar las tasas de los impuestos configurados."))
        return super(AccountTax, self).write(vals)

    def unlink(self):
         # Bloquear eliminación
        if self.company_id.homologacion_activa:
            raise UserError(_("Acuerdo Fiscal: No se permite eliminar impuestos. Archívelos en su lugar."))
        return super(AccountTax, self).unlink()

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    def write(self, vals):
        # Bloquear modificación de tasas históricas (fechas anteriores a hoy)
        if self.env.company.homologacion_activa:
            for record in self:
                if record.name and record.name < fields.Date.context_today(record):
                    raise UserError(_("Acuerdo Fiscal: No está permitido modificar el histórico de tasas cambiarias (BCV)."))
        return super(ResCurrencyRate, self).write(vals)

    def unlink(self):
        # Bloquear eliminación de tasas históricas (fechas anteriores a hoy)
        if self.env.company.homologacion_activa:
            for record in self:
                if record.name and record.name < fields.Date.context_today(record):
                    raise UserError(_("Acuerdo Fiscal: No está permitido eliminar registros del histórico de tasas cambiarias (BCV)."))
        return super(ResCurrencyRate, self).unlink()
