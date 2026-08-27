from odoo import models, api, tools

class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        """
        Sobrescribe la carga de menús de Odoo para la sesión actual y oculta dinámicamente
        todos los menús relacionados a la localización venezolana si la compañía actual 
        NO tiene la marca is_ve_company.
        """
        # Obtenemos el diccionario desde el cache o desde Odoo base
        menus = super(IrUiMenu, self).load_menus(debug)
        
        if self.env.company and getattr(self.env.company, 'is_ve_company', False) is False:
            # Lista de nombres estáticos conocidos de la localización a ocultar
            ve_menu_names = [
                'Informes de Venezuela', 
                'Ide Venezuela', 
                'Retenciones', 
                'Listado de IGTF Percibido',
                'Generar TXT IVA',
                'Generar archivo XML',
                'Libro Fiscal de Compra',
                'Libro Fiscal de Venta',
                'Libro de Inventario',
                'Resumen de ventas y compras',
                'Listado Retención ISLR',
                'Listado Retención IVA'
            ]

            import copy
            menus_copy = copy.deepcopy(menus)
            
            # Recorrer todos los elementos para remover los prohibidos en Odoo 16/17
            # Estructura: root tiene 'childrenTree', cada uno tiene id, name, childrenTree
            def _filter_ve_menus(node_list):
                if not node_list:
                    return []
                filtered_list = []
                for child in node_list:
                    if isinstance(child, dict) and child.get('name') not in ve_menu_names:
                        if 'childrenTree' in child:
                            child['childrenTree'] = _filter_ve_menus(child.get('childrenTree', []))
                        filtered_list.append(child)
                return filtered_list

            for key, menu_dict in menus_copy.items():
                if isinstance(menu_dict, dict) and 'childrenTree' in menu_dict:
                    menu_dict['childrenTree'] = _filter_ve_menus(menu_dict['childrenTree'])
                    
            return menus_copy
        
        return menus
