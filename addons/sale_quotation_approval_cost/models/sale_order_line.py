from odoo import api, fields, models, _


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    cost = fields.Monetary(
        string="Cost",
        compute="_compute_cost",
        store=True,
        currency_field="currency_id",
    )

    @api.depends(
        "product_uom_qty",
        "product_id",
        "product_id.standard_price",
        "order_id.currency_id",
        "order_id.company_id",
        "order_id.date_order",
    )
    def _compute_cost(self):
        for line in self:
            if not line.product_id or line.product_uom_qty <= 0:
                line.cost = 0.0
                continue
            company = line.order_id.company_id or self.env.company
            company_currency = company.currency_id
            order_currency = line.order_id.currency_id or company_currency

            base_cost = line.product_id.standard_price * line.product_uom_qty
            if company_currency and order_currency:
                line.cost = company_currency._convert(
                    base_cost, order_currency, company,
                    line.order_id.date_order or fields.Date.today())
            else:
                line.cost = base_cost
