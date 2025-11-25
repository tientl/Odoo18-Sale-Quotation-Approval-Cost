import copy
from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
    )
    state = fields.Selection(
        selection_add=[('wait_lead', "Approving: Team Leader"),
                       ('wait_manager', "Approving: Manager"),
                       ('wait_finance', "Approving: Finance"),
                       ('approved', "Approved"), ('sent',)]
    )

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
        percent = 1.5 # 50% of total_cost
        for order in self:
            rule = 'none'
            if order.order_line:
                amount_total = order.amount_total or 0.0
                total_cost = order.total_cost or 0.0
                if amount_total <= total_cost:
                    rule = 'full'
                elif amount_total <= total_cost * percent:
                    rule = 'team_leader'
            order.approval_rule = rule

    def action_submit_for_approval(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_salesman'):
            raise UserError(
                _('You do not have permission to submit for approval.'))
        elif not self.order_line:
            raise UserError(
                _('Please ensure all order line information is complete before submitting for approval.'))
        else:
            self.state = 'wait_lead'

    def action_approve(self):
        self.ensure_one()
        transitions = {
            ('wait_lead', 'team_leader'): 'approved',
            ('wait_lead', 'full'): 'wait_manager',
            ('wait_manager', 'full'): 'wait_finance',
            ('wait_finance', 'full'): 'approved',
        }

        self._check_stage_permission(_('approved'))

        next_state = transitions.get((self.state, self.approval_rule))
        if not next_state:
            raise UserError(_('Approval flow is not defined for this stage.'))

        self.state = next_state

    def action_reject(self):
        self.ensure_one()
        self._check_stage_permission(_('rejected'))
        self.state = 'draft'

    def _check_stage_permission(self, action_label):
        stage_rules = {
            'wait_lead': ('Team Leader', lambda order:
                          order.env.user == order.team_id.user_id
            ),
            'wait_manager': (
                'Sales Manager',
                lambda order: order.env.user.has_group(
                    'sales_team.group_sale_manager'
                )
            ),
            'wait_finance': (
                'Finance Manager',
                lambda order: order.env.user.has_group(
                    'account.group_account_manager'
                )
            ),
        }
        rule = stage_rules.get(self.state)
        if not rule:
            raise UserError(_('This quotation is not in an approval stage.'))
        label, checker = rule
        if not checker(self):
            raise UserError(
                _('This stage can only be %s by %s.') % (action_label, label)
            )
        return True

    def write(self, vals):
        # Only allow modification of order lines in 'draft' or 'cancel' states
        order_editable_states = {'draft', 'cancel'}
        if 'order_line' in vals:
            target_state = vals.get('state')
            invalid_orders = self.filtered(
                lambda order: (target_state or order.state)
                not in order_editable_states
            )
            if invalid_orders:
                raise UserError(_("You can't modify when that in approval process."))
        return super().write(vals)

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        if self.env.context.get('mark_so_as_sent'):
            self.filtered(lambda o: o.state == 'approved').with_context(
                tracking_disable=True).write({'state': 'sent'})
        return super(SaleOrder, self).message_post(**kwargs)
