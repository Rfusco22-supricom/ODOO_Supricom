# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Pre-migración (antes de actualizar el módulo).

    Copia `rif` -> `vat` usando SQL.

    Reglas:
    - No sobreescribe `vat` si ya tiene valor.
    - Solo copia si `rif` tiene valor.

    Nota: En Odoo 17, `res.company.vat` es related a `res.partner.vat` (no es columna en res_company),
    por lo que para compañías se actualiza el `vat` del partner asociado a la compañía.
    """

    # Partners: rif -> vat
    cr.execute(
        """
        UPDATE res_partner
           SET vat = rif
         WHERE (vat IS NULL OR vat = '')
           AND rif IS NOT NULL
           AND rif <> ''
        """
    )

    # Compañías: res_company.rif -> res_partner.vat (partner de la compañía)
    cr.execute(
        """
        UPDATE res_partner rp
           SET vat = c.rif
          FROM res_company c
         WHERE rp.id = c.partner_id
           AND (rp.vat IS NULL OR rp.vat = '')
           AND c.rif IS NOT NULL
           AND c.rif <> ''
        """
    )
