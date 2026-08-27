from odoo import models, fields


class ResPartnerBank(models.Model):
    _inherit = 'res.bank'

    bank_code_vzla = fields.Selection([
        ("1",  "01 - Banco de Venezuela"),
        ("2",  "02 - Citibank"),
        ("3",  "03 - Provincial"),
        ("4",  "04 - Mercantil"),
        ("5",  "05 - Banesco"),
        ("6",  "06 - Venezolano de Crédito"),
        ("7",  "07 - Exterior"),
        ("8",  "08 - Fondo Común"),
        ("9",  "09 - Industrial de Venezuela"),
        ("10", "10 - Corpbanca"),
        ("11", "11 - Del Caribe"),
        ("12", "12 - Federal"),
        ("13", "13 - Nuevo Mundo"),
        ("14", "14 - Banco Central de Venezuela"),
        ("15", "15 - Occidental de Descuento"),
        ("16", "16 - Canarias"),
        ("17", "17 - Sofitasa"),
        ("18", "18 - Banco Nacional de Crédito"),
        ("19", "19 - ABN Ambro Bank"),
        ("20", "20 - Confederado"),
        ("21", "21 - Corp. Andina de Fomento"),
        ("22", "22 - Total Bank"),
        ("23", "23 - De Desarrollo Económico y Social de Venezuela"),
        ("24", "24 - Del Sur"),
        ("25", "25 - Banco Plaza"),
        ("26", "26 - De Comercio Exterior"),
        ("27", "27 - Del Caroní"),
        ("28", "28 - Central Entidad de Ahorro"),
        ("29", "29 - Banfoandes"),
        ("30", "30 - Banpro, C.A. Banco Universal"),
        ("31", "31 - Banco Guayana"),
        ("32", "32 - Banco Activo"),
        ("33", "33 - Banco del Tesoro"),
        ("34", "34 - Banplus"),
        ("35", "35 - Banco Bicentenario"),
        ("36", "36 - Otros Bancos")


    ], string='Codigo Bco. Vzla', help="Este código se usa para generar el archivo del Banco Venezuela, segun la pestaña datos")

   
