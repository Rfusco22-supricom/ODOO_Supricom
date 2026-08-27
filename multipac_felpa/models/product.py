# -*- coding: utf-8 -*-
#################################################################################
# Author      : Rodrigo Contreras (<mrdc.tech>)
# Copyright(c): 2024
# All Rights Reserved.
#
# This module is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#################################################################################

from odoo import api, models, fields, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_panama_company = fields.Boolean(
        string='Is Panama Company',
        compute='_compute_is_panama_company',
        store=False,
    )

    @api.depends_context('company')
    def _compute_is_panama_company(self):
        is_pa = self.env.company.country_id.code == 'PA'
        for rec in self:
            rec.is_panama_company = is_pa

    # Compatibility fields for other modules
    # Brand field (removed from Venezuelan implementation)
    brand_id = fields.Integer(string='Brand ID', help='Compatibility field - stores brand ID from previous implementation')

    # Inventory/Stock fields
    allow_negative_stock = fields.Boolean(string='Allow Negative Stock', default=False, help='Compatibility field')
    allow_out_of_stock_order = fields.Boolean(string='Allow Out Of Stock Order', default=False, help='Compatibility field')
    available_threshold = fields.Float(string='Available Threshold', help='Compatibility field')
    show_availability = fields.Boolean(string='Show Availability', default=False, help='Compatibility field')
    to_weight = fields.Boolean(string='To Weight', default=False, help='Compatibility field')
    tracking = fields.Selection([
        ('none', 'No Tracking'),
        ('lot', 'By Lots'),
        ('serial', 'By Unique Serial Number')
    ], string='Tracking', help='Compatibility field')
    
    # POS fields
    available_in_pos = fields.Boolean(string='Available In POS', default=False, help='Compatibility field')
    
    # Product classification
    base_unit_count = fields.Float(string='Base Unit Count', help='Compatibility field')
    
    # Pricing fields
    compare_list_price = fields.Float(string='Compare List Price', help='Compatibility field')
    list_price_usd = fields.Float(string='List Price USD', help='Compatibility field')
    list_price_vat = fields.Float(string='List Price VAT', help='Compatibility field')
    list_price_vat_usd = fields.Float(string='List Price VAT USD', help='Compatibility field')
    min_price = fields.Float(string='Min Price', help='Compatibility field')
    standard_price_usd = fields.Float(string='Standard Price USD', help='Compatibility field')
    
    # Product type and policy fields
    # detailed_type = fields.Selection([
    #     ('consu', 'Consumable'),
    #     ('service', 'Service'),
    #     ('product', 'Storable Product'),
    #     ('booking_fees', 'Booking Fees')
    # ], string='Product Type', help='Compatibility field')
    expense_policy = fields.Selection([
        ('no', 'No'),
        ('cost', 'At cost'),
        ('sales_price', 'At sales price')
    ], string='Expense Policy', help='Compatibility field')
    invoice_policy = fields.Selection([
        ('order', 'Ordered quantities'),
        ('delivery', 'Delivered quantities')
    ], string='Invoice Policy', help='Compatibility field')
    service_type = fields.Selection([
        ('manual', 'Manually set quantities on order'),
        ('timesheet', 'Timesheets on tasks')
    ], string='Service Type', help='Compatibility field')
    service_tracking = fields.Selection([
        ('no', 'Nothing'),
        ('task_global_project', 'Task in global project'),
        ('task_in_project', 'Project & Task'),
        ('project_only', 'Project')
    ], string='Service Tracking', help='Compatibility field')
    purchase_method = fields.Selection([
        ('purchase', 'On ordered quantities'),
        ('receive', 'On received quantities')
    ], string='Purchase Method', help='Compatibility field')
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', help='Compatibility field')
    
    # Purchase fields
    purchase_ok = fields.Boolean(string='Can be Purchased', default=False, help='Compatibility field')
    purchase_line_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Purchase Line Warning', help='Compatibility field')
    purchase_line_warn_msg = fields.Text(string='Purchase Line Warning Message', help='Compatibility field')
    
    # Sales fields
    sale_ok = fields.Boolean(string='Can be Sold', default=False, help='Compatibility field')
    sale_line_warn = fields.Selection([
        ('no-message', 'No Message'),
        ('warning', 'Warning'),
        ('block', 'Block')
    ], string='Sale Line Warning', help='Compatibility field')
    sale_line_warn_msg = fields.Text(string='Sale Line Warning Message', help='Compatibility field')
    
    # Commission fields
    is_special_commission = fields.Boolean(string='Is Special Commission', default=False, help='Compatibility field')
    x_comision_fija_producto = fields.Float(string='Fixed Product Commission', help='Compatibility field')
    
    # Website/E-commerce fields
    is_published = fields.Boolean(string='Is Published', default=False, help='Compatibility field')
    
    # Logistics fields
    landed_cost_ok = fields.Boolean(string='Landed Cost OK', default=False, help='Compatibility field')
    # split_method_landed_cost = fields.Selection([
    #     ('equal', 'Equal'),
    #     ('by_quantity', 'By Quantity'),
    #     ('by_current_cost_price', 'By Current Cost Price'),
    #     ('by_weight', 'By Weight'),
    #     ('by_volume', 'By Volume'),
    # ], string='Método de división predeterminado', help='Método de división para costos aterrizados')
    hs_code = fields.Char(string='HS Code', help='Compatibility field')
    volume = fields.Float(string='Volume', help='Compatibility field')
    weight = fields.Float(string='Weight', help='Compatibility field')
    
    # Planning fields
    planning_enabled = fields.Boolean(string='Planning Enabled', default=False, help='Compatibility field')
    
    # Repair field
    create_repair = fields.Boolean(string='Create Repair', default=False, help='Compatibility field')
    
    fel_pa_unspsc_category_id = fields.Many2one("fel_pa.tools.product_unspsc_category", string="Panamá UNSPSC Category")
    fel_pa_info_item = fields.Text(string="Panamá Information Item")
    fel_pa_product_type = fields.Selection([('goods_service', "Goods/Service"),
                                            ('vehicle', "Vehicle"),
                                            ('medicine', "Medicine"),
                                            ], string="Panamá Product Type", default='goods_service')
    
    fel_pa_chassis = fields.Char(string='Chassis')
    fel_pa_color_code = fields.Char(string='Color Code')
    fel_pa_color_name = fields.Char(string='Color Name')
    fel_pa_engine_power = fields.Char(string='Engine Power (CV)')
    fel_pa_engine_capacity = fields.Char(string='Engine Capacity (in liters)')
    fel_pa_net_weight = fields.Char(string='Net Weight (in TON)')
    fel_pa_gross_weight = fields.Char(string='Gross Weight')
    fel_pa_fuel_type = fields.Selection([
        ('01', 'Gasoline'),
        ('02', 'Diesel'),
        ('03', 'Ethanol'),
        ('08', 'Electric'),
        ('09', 'Gasoline/Electric'),
        ('99', 'Other')
    ], string='Fuel Type')
    fel_pa_fuel_type_nodef = fields.Char(string='Fuel Type Nodef')
    fel_pa_engine_number = fields.Char(string='Engine Number')
    fel_pa_traction_capacity = fields.Char(string='Traction Capacity')
    fel_pa_axle_distance = fields.Char(string='Axle Distance (m)')
    fel_pa_model_year = fields.Char(string='Model Year')
    fel_pa_manufacture_year = fields.Char(string='Manufacture Year')
    fel_pa_paint_type = fields.Selection([
        ('1', 'Solid'),
        ('2', 'Metallic'),
        ('3', 'Pearl'),
        ('4', 'Matte'),
        ('9', 'Other')
    ], string='Paint Type')
    fel_pa_paint_nodef = fields.Char(string='Paint Nodef')
    fel_pa_vehicle_type = fields.Selection([
        ('1', 'Motorcycle'),
        ('2', 'Bus'),
        ('3', 'Truck'),
        ('4', 'Sedan'),
        ('5', 'SUV'),
        ('6', 'Pickup'),
        ('7', 'Mini Pickup'),
        ('8', 'Pickup Truck'),
        ('9', 'Hatchback'),
        ('27', 'Tricycle'),
        ('31', 'Trailer'),
        ('33', 'Tow Trailer')
    ], string='Vehicle Type')
    fel_pa_vehicle_usage = fields.Selection([
        ('1', 'Commercial'),
        ('2', 'Private'),
        ('3', 'Diplomatic'),
        ('4', 'Official'),
        ('5', 'Special')
    ], string='Vehicle Usage')
    fel_pa_vehicle_condition = fields.Selection([
        ('1', 'Finished'),
        ('2', 'Partially-finished'),
        ('3', 'Unfinished')
    ], string='Vehicle Condition')
    fel_pa_passenger_capacity = fields.Char(string='Passenger Capacity')
    fel_pa_exclude_from_invoice = fields.Boolean(string='Exclude from Invoice')
    

class ProductProduct(models.Model):
    _inherit = "product.product"

    is_panama_company = fields.Boolean(
        string='Is Panama Company',
        compute='_compute_is_panama_company',
        store=False,
    )

    @api.depends_context('company')
    def _compute_is_panama_company(self):
        is_pa = self.env.company.country_id.code == 'PA'
        for rec in self:
            rec.is_panama_company = is_pa

    # Compatibility fields for other modules
    brand_id = fields.Integer(string='Brand ID', help='Compatibility field - stores brand ID from previous implementation')

    # Compatibility fields - same as template
    fel_pa_unspsc_category_id = fields.Many2one("fel_pa.tools.product_unspsc_category", string="Panamá UNSPSC Category", related='product_tmpl_id.fel_pa_unspsc_category_id', readonly=False)
    fel_pa_info_item = fields.Text(string="Panamá Information Item", related='product_tmpl_id.fel_pa_info_item', readonly=False)
    fel_pa_product_type = fields.Selection(string="Panamá Product Type", related='product_tmpl_id.fel_pa_product_type', readonly=False)
    fel_pa_chassis = fields.Char(string='Chassis', size=17, related='product_tmpl_id.fel_pa_chassis', readonly=False)
    fel_pa_color_code = fields.Char(string='Color Code', size=4, related='product_tmpl_id.fel_pa_color_code', readonly=False)
    fel_pa_color_name = fields.Char(string='Color Name', size=40, related='product_tmpl_id.fel_pa_color_name', readonly=False)
    fel_pa_engine_power = fields.Char(string='Engine Power (CV)', related='product_tmpl_id.fel_pa_engine_power', readonly=False)
    fel_pa_engine_capacity = fields.Char(string='Engine Capacity (in liters)', related='product_tmpl_id.fel_pa_engine_capacity', readonly=False)
    fel_pa_net_weight = fields.Char(string='Net Weight (in TON)', related='product_tmpl_id.fel_pa_net_weight', readonly=False)
    fel_pa_gross_weight = fields.Char(string='Gross Weight', related='product_tmpl_id.fel_pa_gross_weight', readonly=False)
    fel_pa_fuel_type_nodef = fields.Char(string='Fuel Type Nodef', related='product_tmpl_id.fel_pa_fuel_type_nodef', readonly=False)
    fel_pa_fuel_type = fields.Selection(string='Fuel Type', related='product_tmpl_id.fel_pa_fuel_type', readonly=False)
    fel_pa_engine_number = fields.Char(string='Engine Number', size=21, related='product_tmpl_id.fel_pa_engine_number', readonly=False)
    fel_pa_traction_capacity = fields.Char(string='Traction Capacity', related='product_tmpl_id.fel_pa_traction_capacity', readonly=False)
    fel_pa_axle_distance = fields.Char(string='Axle Distance (m)', related='product_tmpl_id.fel_pa_axle_distance', readonly=False)
    fel_pa_model_year = fields.Char(string='Model Year', related='product_tmpl_id.fel_pa_model_year', readonly=False)
    fel_pa_manufacture_year = fields.Char(string='Manufacture Year', related='product_tmpl_id.fel_pa_manufacture_year', readonly=False)
    fel_pa_paint_type = fields.Selection(string='Paint Type', related='product_tmpl_id.fel_pa_paint_type', readonly=False)
    fel_pa_paint_nodef = fields.Char(string='Paint Nodef', related='product_tmpl_id.fel_pa_paint_nodef', readonly=False)
    fel_pa_vehicle_type = fields.Selection(string='Vehicle Type', related='product_tmpl_id.fel_pa_vehicle_type', readonly=False)
    fel_pa_vehicle_usage = fields.Selection(string='Vehicle Usage', related='product_tmpl_id.fel_pa_vehicle_usage', readonly=False)
    fel_pa_vehicle_condition = fields.Selection(string='Vehicle Condition', related='product_tmpl_id.fel_pa_vehicle_condition', readonly=False)
    fel_pa_passenger_capacity = fields.Char(string='Passenger Capacity', related='product_tmpl_id.fel_pa_passenger_capacity', readonly=False)
    fel_pa_exclude_from_invoice = fields.Boolean(string='Exclude from Invoice', related='product_tmpl_id.fel_pa_exclude_from_invoice', readonly=False)