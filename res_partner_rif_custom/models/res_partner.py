from odoo import models, fields, api
from lxml import etree

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Campo base que persistirá la información
    rif = fields.Char(string='RIF')

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == 'form':
            # 1. Aseguramos country_code para las condiciones dinámicas
            if not arch.xpath("//field[@name='country_code']"):
                for name_node in arch.xpath("//field[@name='name']"):
                    name_node.addprevious(etree.Element('field', {'name': 'country_code', 'invisible': '1'}))

            # 2. Ocultamos todos los campos 'vat' y 'rif' existentes y sus etiquetas
            for field_name in ['vat', 'rif']:
                for node in arch.xpath(f"//field[@name='{field_name}']"):
                    node.set('invisible', '1')
                    node.set('nolabel', '1')
                for label in arch.xpath(f"//label[@for='{field_name}']"):
                    label.set('invisible', '1')

            # 3. Inyectamos nuestro campo 'rif' envuelto en un o_row con ancho expandido
            vat_nodes = arch.xpath("//field[@name='vat']")
            if vat_nodes:
                target = vat_nodes[0]
                parent = target.getparent()
                if parent is not None:
                    # Usamos o_row con flex para que ocupe el espacio disponible
                    row_div = etree.Element('div', {'class': 'o_row', 'style': 'width: 100%; display: flex; align-items: center;'})
                    
                    # Definimos el patrón: Label + Field para cada caso
                    l_style = 'font-weight: bold; margin-right: 8px; white-space: nowrap;'
                    f_style = 'flex: 1; min-width: 150px;'
                    
                    # 1. PANAMÁ (RUC)
                    l_pa = etree.Element('label', {'for': 'rif', 'string': 'RUC', 'invisible': "country_code != 'PA'", 'style': l_style})
                    f_pa = etree.Element('field', {'name': 'rif', 'nolabel': '1', 'invisible': "country_code != 'PA'", 'style': f_style})
                    
                    # 2. VENEZUELA (RIF)
                    l_ve = etree.Element('label', {'for': 'rif', 'string': 'RIF', 'invisible': "country_code != 'VE'", 'style': l_style})
                    f_ve = etree.Element('field', {'name': 'rif', 'nolabel': '1', 'invisible': "country_code != 'VE'", 'style': f_style})
                    
                    # 3. OTROS (NIF)
                    l_other = etree.Element('label', {'for': 'rif', 'string': 'NIF', 'invisible': "country_code in ['PA', 'VE']", 'style': l_style})
                    f_other = etree.Element('field', {'name': 'rif', 'nolabel': '1', 'invisible': "country_code in ['PA', 'VE']", 'style': f_style})
                    
                    # Añadimos todo al div
                    row_div.append(l_pa)
                    row_div.append(f_pa)
                    row_div.append(l_ve)
                    row_div.append(f_ve)
                    row_div.append(l_other)
                    row_div.append(f_other)
                    
                    # Insertamos el div después del target oculto
                    idx = parent.index(target)
                    parent.insert(idx + 1, row_div)
                    
        return arch, view
