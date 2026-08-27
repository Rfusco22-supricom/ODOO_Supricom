from odoo import models, fields, api, _

class CurrencyExchangeConfig(models.Model):
    _name = 'currency.exchange.config'
    _description = 'Configuracion de Compra/Transferencia'
    _rec_name = 'company_id'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, default=lambda self: self.env.company)
    
    transfer_account_id = fields.Many2one('account.account', string='Cuenta Puente/Transitoria', required=True, 
                                          help="Cuenta usada para el transito de dinero.")
    profit_loss_account_id = fields.Many2one('account.account', string='Cuenta Diferencial', 
                                             help="Cuenta para registrar Ganancia/Perdida por cambio.")
    
    journal_id = fields.Many2one('account.journal', string='Diario de Diferencial', 
                                 domain=[('type', 'in', ('general', 'bank', 'cash'))],
                                 help="Diario opcional para el asiento de diferencial.")
    
    _sql_constraints = [
        ('company_uniq', 'unique(company_id)', _('Ya existe una configuración para esta compañía.'))
    ]
