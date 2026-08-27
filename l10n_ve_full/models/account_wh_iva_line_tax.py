# coding: utf-8
import time
from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError



class AccountWhIvaLineTax(models.Model):
    _name = 'account.wh.iva.line.tax'
    _description = 'Impuestos de lineas de retención de IVA'

    move_id = fields.Many2one('account.move',string='Invoice', required=True,
        ondelete='restrict', help="Withholding invoice")
    id_tax = fields.Integer('hola')

    inv_tax_id = fields.Many2one(
        'account.tax', string='Impuesto de factura',
        ondelete='set null', help="Tax Line")
    wh_vat_line_id = fields.Many2one(
        'account.wh.iva.line', string='VAT Withholding Line', required=True,
        ondelete='cascade', help="Line withholding VAT")
    tax_id = fields.Many2one(
        'account.tax', string='Tax',
        related='inv_tax_id.tax_id', store=True, readonly=True,
        ondelete='set null', help="Tax")
    name = fields.Char(
        string='Nombre del Impuesto', size=256,
        related='inv_tax_id.name', store=True, readonly=True,
        ondelete='set null', help=" Tax Name")
    base = fields.Float(string='Base de la factura',  store=True, compute='_get_base_amount', help="Tax Base")
    amount = fields.Float(string='Cantidad gravada', digits=(16, 2), store=True, compute='_get_base_amount', help="Withholding tax amount")
    amount_ret = fields.Float(string='Cantidad gravada retenida', store=True, compute='_get_base_amount', digits=(16, 2), readonly=False, help="Importe de retención de IVA")
    company_id = fields.Many2one(
        'res.company', string='Company',
        related='inv_tax_id.company_id', store=True, readonly=True,
        ondelete='set null', help="Company")
    alicuota = fields.Float('% Alicuota del impuesto')
    purchase_not_taxed = fields.Float(string="Compras sin derecho a credito fiscal")


    @api.depends('inv_tax_id', 'wh_vat_line_id.wh_iva_rate')
    def _get_base_amount(self):
        """ Return withholding amount"""
        for record in self:
            currency_id = record.wh_vat_line_id.retention_id.currency_id
            if record.inv_tax_id.appl_type == 'exento':
                record.base = 0.0
                record.amount = 0.0
                record.amount_ret = 0.0
            else:
                tax_ids = record.move_id.line_ids.filtered(lambda l: l.display_type == 'tax' and l.tax_line_id.id == record.id_tax)
                if record.move_id.currency_id != record.move_id.company_id.currency_id and tax_ids:
                    record.base = currency_id.round(sum(abs(l.amount_currency) for l in record.move_id.invoice_line_ids.filtered(lambda x: record.inv_tax_id.id in x.tax_ids.ids)))
                    record.amount = currency_id.round(sum(abs(l.amount_currency) for l in tax_ids))
                else:
                    record.base = currency_id.round(sum(tax_ids.mapped('tax_base_amount')))
                    record.amount = currency_id.round(abs(sum(tax_ids.mapped('balance'))))
                record.amount_ret = currency_id.round(record.amount * (record.wh_vat_line_id.wh_iva_rate / 100.0))

    def _set_amount_ret(self):
        """ Change withholding amount into iva line
        @param value: new value for retention amount
        """
        # NOTE: use ids argument instead of id for fix the pylint error W0622.
        # Redefining built-in 'id'
        for record in self:
            if record.wh_vat_line_id.retention_id.type != 'out_invoice':
                continue
            if not record.amount_ret:
                continue
            sql_str = """UPDATE account_wh_iva_line_tax set
                    amount_ret='%s'
                    WHERE id=%d """ % (record.amount_ret, record.id)
            self._cr.execute(sql_str)
        return True


    @api.depends('amount', 'wh_vat_line_id.wh_iva_rate')
    def _get_amount_ret(self):
        """ Return withholding amount
        """
        for record in self:
            # TODO: THIS NEEDS REFACTORY IN ORDER TO COMPLY WITH THE SALE
            # WITHHOLDING
            ret = (record.amount * record.wh_vat_line_id.wh_iva_rate / 100.0)
            ret = str(ret)
            ret1,ret2 = ret.split('.')
            ret2 = ret2[:2]
            ret = ret1 + '.' + ret2
            record.amount_ret = float(ret)

