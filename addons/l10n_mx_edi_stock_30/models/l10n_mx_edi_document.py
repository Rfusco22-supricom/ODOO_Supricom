from odoo import api, models


class L10nMxEdiDocument(models.Model):
    _inherit = 'l10n_mx_edi.document'

    @api.model
    def _decode_cfdi_attachment(self, cfdi_data):
        # EXTENDS 'l10n_mx_edi'
        def get_node(node, xpath):
            nodes = node.xpath(xpath)
            return nodes[0] if nodes else None

        cfdi_infos = super()._decode_cfdi_attachment(cfdi_data)
        if not cfdi_infos:
            return cfdi_infos

        cfdi_node = cfdi_infos['cfdi_node']

        carta_porte_node = get_node(cfdi_node, "//*[local-name()='CartaPorte']")
        if carta_porte_node is None:
            return cfdi_infos

        cfdi_infos.update({
            'carta_porte_node': carta_porte_node,
            'carta_porte_idccp': carta_porte_node.get('IdCCP', ''),
        })
        return cfdi_infos
