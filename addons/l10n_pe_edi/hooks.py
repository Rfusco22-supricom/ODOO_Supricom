# Part of Odoo. See LICENSE file for full copyright and licensing details.


def post_init_hook(env):
    _activate_sunat_unspsc_codes(env)
    for company in env['res.company'].search([('chart_template', '=', 'pe'), ('parent_id', '=', False)]):
        ChartTemplate = env['account.chart.template'].with_company(company)
        tax_group_data = ChartTemplate._get_pe_edi_account_tax_group()
        ChartTemplate._load_data({'account.tax.group': tax_group_data})


def _activate_sunat_unspsc_codes(env):
    # Codes SUNAT requires from 2026-08-01. 11111111 is a SUNAT-only code, not
    # part of the UNSPSC standard.
    sunat_codes = [
        '11101600', '11111600', '11111700', '11121600', '12131500', '20101600',
        '24122000', '26111600', '50111500', '50151600', '50171500', '50202300',
        '50403200', '73121500',
    ]
    UnspscCode = env['product.unspsc.code']
    UnspscCode.search([('active', '=', False), ('code', 'in', sunat_codes)]).active = True
    if not UnspscCode.with_context(active_test=False).search_count([('code', '=', '11111111')]):
        UnspscCode.create({
            'code': '11111111',
            'name': 'Goods subject to IGV due to waiver of exemption',
            'applies_to': 'product',
            'active': True,
        })
