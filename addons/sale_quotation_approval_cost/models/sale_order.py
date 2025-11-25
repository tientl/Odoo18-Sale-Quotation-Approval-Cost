import copy
from odoo import api, fields, models, _
from odoo.exceptions import UserError

SALE_ORDER_STATE = [
    ('draft', "Quotation"),
    ('to_approve', "To Approve"),
    ('approved', "Approved"),
    ('sent', "Quotation Sent"),
    ('sale', "Sales Order"),
    ('cancel', "Cancelled"),
]

class SaleOrder(models.Model):
    _inherit = "sale.order"

    total_cost = fields.Monetary(
        string="Total Cost",
        compute="_compute_total_cost",
        store=True,
        currency_field="currency_id",
        tracking=5
    )
    approval_rule = fields.Selection(
        [
            ("none", "No Approval"),
            ("team_leader", "Team Leader Only"),
            ("full", "Team Leader + Manager + Finance"),
        ],
        string="Approval Rule",
        compute="_compute_approval_rule",
        store=True,
    )
    state = fields.Selection(selection=SALE_ORDER_STATE)

    @api.depends("order_line.cost")
    def _compute_total_cost(self):
        for order in self:
            order.total_cost = sum(order.order_line.mapped("cost"))

    @api.depends_context('lang')
    @api.depends('order_line.price_subtotal', 'currency_id', 'company_id',
                 'payment_term_id', 'total_cost')
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for order in self:
            if not order.tax_totals:
                continue
            tax_totals = copy.deepcopy(order.tax_totals)
            tax_totals['total_cost'] = order.total_cost or 0.0
            order.tax_totals = tax_totals

    @api.depends('amount_total', 'total_cost')
    def _compute_approval_rule(self):
        for order in self:
            percent_unit = 1.5
            amount_total = order.amount_total
            total_cost = order.total_cost
            if amount_total <= total_cost:
                order.approval_rule = 'full'
            elif amount_total <= total_cost * percent_unit:
                order.approval_rule = 'team_leader'
            else:
                order.approval_rule = 'none'

    def action_submit_for_approval(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_salesman'):
            raise UserError(
                _('You do not have permission to submit for approval.'))
        elif not self.order_line:
            raise UserError(
                _('Please ensure all order line information is complete before submitting for approval.'))
        for order in self:
            order.state = 'to_approve'

    # @api.constrains('account_type', 'reconcile')
    # def _check_approval_constraints(self):
    #     for order in self:

    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Approval State', default='draft', tracking=True)

    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    rejected_by = fields.Many2one('res.users', string='Rejected By', readonly=True)
    rejected_date = fields.Datetime(string='Rejected Date', readonly=True)

    def action_approve(self):
        if not (self.env.user.has_group('sales_team.group_sale_salesman_all_leads') or \
                self.env.user.has_group('sales_team.group_sale_manager') or \
                self.env.user.has_group('account.group_account_manager')):
            raise UserError(_('You do not have permission to approve.'))
        for order in self:
            order.approval_state = 'approved'
            order.approved_by = self.env.user
            order.approved_date = fields.Datetime.now()

    def action_reject(self):
        if not (self.env.user.has_group('sales_team.group_sale_salesman_all_leads') or \
                self.env.user.has_group('sales_team.group_sale_manager') or \
                self.env.user.has_group('account.group_account_manager')):
            raise UserError(_('You do not have permission to reject.'))
        for order in self:
            order.approval_state = 'rejected'
            order.rejected_by = self.env.user
            order.rejected_date = fields.Datetime.now()