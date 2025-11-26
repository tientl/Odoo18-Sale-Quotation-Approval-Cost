import copy
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


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
    approval_default_domain = fields.Boolean(
        compute="_compute_approval_default_domain",
        search="_search_approval_default_domain",
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
        percent = 50  # 50% of total_cost
        for order in self:
            percent_number = (order.total_cost / 100) * percent
            rule = 'none'
            if order.order_line:
                amount_total = order.amount_total or 0.0
                total_cost = order.total_cost or 0.0
                if amount_total <= total_cost:
                    rule = 'full'
                elif amount_total <= total_cost + percent_number:
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
            self._notify_role('team_leader')

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
        # Auto notify the next approver if applicable
        next_role_map = {
            'wait_manager': 'manager',
            'wait_finance': 'finance',
        }
        next_role = next_role_map.get(self.state)
        if next_role:
            self._notify_role(next_role)
        # If approved, notify the salesperson.
        if self.state == 'approved':
            self._notify_salesperson()

    def action_reject(self):
        self.ensure_one()
        self._check_stage_permission(_('rejected'))
        self.state = 'draft'

    def _notify_role(self, role):
        """Send an in-app notification to the corresponding approval role."""
        self.ensure_one()
        state_role_map = {
            'team_leader': 'wait_lead',
            'manager': 'wait_manager',
            'finance': 'wait_finance',
        }
        expected_state = state_role_map.get(role)
        if expected_state and self.state != expected_state:
            return False

        partners = self._get_role_partners(role)
        if not partners:
            return False

        role_label = {
            'team_leader': _('Team Leader'),
            'manager': _('Sales Manager'),
            'finance': _('Finance Manager'),
        }.get(role, _('Approver'))

        link_html = self._build_record_link()
        body_html = _("Please review quotation %s for approval.<br/>Customer: %s<br/>Total: %s") % (
            self.name,
            self.partner_id.display_name,
            (self.currency_id and ("%s %.2f" % (
                self.currency_id.symbol, self.amount_total))
             ) or self.amount_total
        )
        if link_html:
            body_html = "%s<br/><br/>%s" % (body_html, link_html)
        body = Markup(body_html)
        # Avoid emails; send in-app notifications only.
        author_partner = self._get_odoobot_partner() or False
        self.with_context(mail_notify_noemail=True, mail_notify_force_send=False).message_post(
            body=body,
            subject=_('%s approval needed: %s') % (role_label, self.name),
            partner_ids=partners.ids,
            subtype_xmlid='mail.mt_comment',
            message_type='comment',
            author_id=author_partner.id if author_partner else False,
        )
        # Additionally push a direct chat to the team leader.
        if role == 'team_leader':
            leader_partner = partners[:1]
            if leader_partner:
                self._send_chat_to_partner(
                    leader_partner,
                    body=body,
                    subject=_('%s approval needed: %s') % (role_label, self.name),
                )
        # For manager/finance, notify each approver who has the role.
        if role in ('manager', 'finance'):
            subject = _('%s approval needed: %s') % (role_label, self.name)
            for partner in partners:
                self._send_chat_to_partner(partner, body=body, subject=subject)
        return True

    def _get_odoobot_partner(self):
        """Return OdooBot partner if available."""
        odoobot = self.env.ref('base.partner_root', raise_if_not_found=False)
        return odoobot

    def _get_role_partners(self, role):
        """Return partner recordset for a given approval role."""
        self.ensure_one()
        partners = self.env['res.partner']
        if role == 'team_leader':
            leader = self.team_id.user_id
            if leader and leader.partner_id:
                partners |= leader.partner_id
        elif role == 'manager':
            managers = self.env.ref('sales_team.group_sale_manager').users
            partners |= managers.mapped('partner_id')
        elif role == 'finance':
            finance_users = self.env.ref('account.group_account_manager').users
            partners |= finance_users.mapped('partner_id')
        return partners

    def _notify_salesperson(self):
        """Notify the salesperson when the quotation is approved."""
        self.ensure_one()
        partner = self.user_id.partner_id
        if not partner:
            return False
        link_html = self._build_record_link()
        body_html = _("Quotation %s has been approved.<br/>Customer: %s<br/>Total: %s") % (
            self.name,
            self.partner_id.display_name,
            (self.currency_id and ("%s %.2f" % (
                self.currency_id.symbol, self.amount_total))
             ) or self.amount_total
        )
        if link_html:
            body_html = "%s<br/><br/>%s" % (body_html, link_html)
        body = Markup(body_html)
        author_partner = self._get_odoobot_partner() or False
        self.with_context(mail_notify_noemail=True,
                          mail_notify_force_send=False).message_post(
            body=body,
            subject=_('Quotation approved: %s') % self.name,
            partner_ids=[partner.id],
            subtype_xmlid='mail.mt_comment',
            message_type='comment',
            author_id=author_partner.id if author_partner else False,
        )
        self._send_chat_to_partner(
            partner,
            body=body,
            subject=_('Quotation approved: %s') % self.name,
        )
        return True

    def _build_record_link(self):
        """Return HTML button linking to the quotation."""
        base_url = self.get_base_url()
        if not base_url:
            return False
        url = "%s/web#id=%s&model=%s&view_type=form" % (
            base_url, self.id, self._name)
        return '<a href="%s" class="btn btn-primary" ' \
               'style="padding:6px 12px; text-decoration:none;">%s</a>' % (
                   url, _("Open Quotation"))

    def _send_chat_to_partner(self, partner, body, subject=None):
        """Send a direct chat message (Discuss) to the given partner
        (mirrors mail_bot._init_odoobot).
        """
        self.ensure_one()
        if not partner:
            return False
        if 'discuss.channel' not in self.env:
            return False
        requester_partner = self.env.user.partner_id
        if not requester_partner:
            return False

        partner_ids = {partner.id, requester_partner.id}
        channel = self.env['discuss.channel'].sudo().channel_get(
            list(partner_ids))
        author_partner = self._get_odoobot_partner() or requester_partner
        channel.sudo().message_post(
            author_id=author_partner.id,
            body=body if isinstance(body, Markup) else Markup(body),
            subject=subject or False,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        return True

    def _check_stage_permission(self, action_label):
        stage_rules = {
            'wait_lead': (
                'Team Leader',
                lambda order: order.env.user == order.team_id.user_id
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

    def _compute_approval_default_domain(self):
        for order in self:
            order.approval_default_domain = True

    @api.model
    def _search_approval_default_domain(self, operator, value):
        """Build a default domain that adapts to the user's approval role."""
        user = self.env.user
        # Start from the user's own quotations.
        domains = [[('user_id', '=', user.id)]]
        # Team leader approvals assigned to the user.
        domains.append([('team_id.user_id', '=', user.id),
                        ('state', '=', 'wait_lead')])
        # Sales manager approvals.
        if user.has_group('sales_team.group_sale_manager'):
            domains.append([('state', '=', 'wait_manager')])
        # Finance manager approvals.
        if user.has_group('account.group_account_manager'):
            domains.append([('state', '=', 'wait_finance')])

        domains = [domain for domain in domains if domain]
        if not domains:
            return [('id', '=', 0)] if value else []

        combined = domains[0]
        for domain in domains[1:]:
            combined = expression.OR([combined, domain])

        if operator in ('!=', '<>'):
            value = not value
        return combined if value else ['!', combined]
