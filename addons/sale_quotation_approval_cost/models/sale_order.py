import copy
from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    total_cost = fields.Monetary(
        string="Total Cost",
        compute="_compute_total_cost",
        store=True,
        currency_field="currency_id",
        tracking=5
    )
    
    @api.depends("order_line.cost")
    def _compute_total_cost(self):
        for order in self:
            order.total_cost = sum(order.order_line.mapped("cost"))

    @api.depends_context('lang')
    @api.depends( 'order_line.price_subtotal', 'currency_id', 'company_id',
        'payment_term_id', 'total_cost')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if not order.tax_totals:
                continue
            tax_totals = copy.deepcopy(order.tax_totals)
            tax_totals['total_cost'] = order.total_cost or 0.0
            order.tax_totals = tax_totals