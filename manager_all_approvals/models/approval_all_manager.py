

from odoo.exceptions import Warning
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare


class PurchaseOrderInherit(models.Model):
    _inherit = 'purchase.order'

    review_by_id = fields.Many2one('res.users', string='Reviewed By')
    approve_by_id = fields.Many2one('res.users', string='Approved By')

    state = fields.Selection([
        ('draft', 'RFQ'),
        ('sent', 'RFQ Sent'),
        ('to_review', 'Waiting For Review'),
        ('approve', 'Waiting For Approval'),
        ('to approve', 'To Approve'),
        ('purchase', 'Purchase Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected'),
    ], string='Status', readonly=True, index=True, copy=False, default='draft', tracking=True)

    def button_confirm(self):
        self.write({
            'state': 'to_review'
        })

    def button_review(self):
        if self.env.user.has_group('manager_all_approvals.group_review_purchase_order'):
            self.review_by_id = self.env.user.id
        self.write({
            'state': 'approve'
        })

    def action_reset(self):
        self.write({
            'state': 'draft'
        })

    def button_approved(self):
        if self.env.user.has_group('manager_all_approvals.group_approve_purchase_order'):
            self.approve_by_id = self.env.user.id
        for order in self:
            if order.state not in ['draft', 'sent', 'approve']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            if order.company_id.po_double_validation == 'one_step' \
                    or (order.company_id.po_double_validation == 'two_step' \
                        and order.amount_total < self.env.company.currency_id._convert(
                        order.company_id.po_double_validation_amount, order.currency_id, order.company_id,
                        order.date_order or fields.Date.today())) \
                    or order.user_has_groups('purchase.group_purchase_manager'):
                order.button_approve()
            else:
                order.write({'state': 'to approve'})
            if order.partner_id not in order.message_partner_ids:
                order.message_subscribe([order.partner_id.id])
        return True

    def button_reject(self):
        self.write({
            'state': 'rejected'
        })

    def button_approve_reject(self):
        self.write({
            'state': 'rejected'
        })


class SaleOrderInh(models.Model):
    _inherit = 'sale.order'

    review_by_id = fields.Many2one('res.users', string='Reviewed By')
    approve_by_id = fields.Many2one('res.users', string='Approved By')

    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('to_review', 'Waiting For Review'),
        ('approve', 'Waiting For Approval'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=3, default='draft')

    def action_confirm(self):
        self.write({
            'state': 'to_review'
        })

    def button_review(self):
        if self.env.user.has_group('manager_all_approvals.group_review_sale_order'):
            self.review_by_id = self.env.user.id
        self.write({
            'state': 'approve'
        })

    def action_reset(self):
        self.write({
            'state': 'draft'
        })

    def button_approved(self):
        if self.env.user.has_group('manager_all_approvals.group_approve_sale_order'):
            self.approve_by_id = self.env.user.id
        rec = super(SaleOrderInh, self).action_confirm()
        return rec

    def button_reject(self):
        self.write({
            'state': 'rejected'
        })

    def button_approve_reject(self):
        self.write({
            'state': 'rejected'
        })


class AccountMoveInh(models.Model):
    _inherit = 'account.move'

    review_by_id = fields.Many2one('res.users', string='Reviewed By')
    approve_by_id = fields.Many2one('res.users', string='Approved By')

    state = fields.Selection(selection=[
        ('draft', 'Draft'),
        ('to_review', 'Waiting For Review'),
        ('approve', 'Waiting For Approval'),
        ('posted', 'Posted'),
        ('cancel', 'Cancelled'),
        ('rejected', 'Rejected'),
    ], string='Status', required=True, readonly=True, copy=False, tracking=True, default='draft')

    def _create_notification_review(self):
        act_type_xmlid = 'mail.mail_activity_data_todo'
        summary = 'Waiting for Review'
        note = 'Document No ' + str(self.name) + ' is waiting to Review.'
        if act_type_xmlid:
            activity_type = self.sudo().env.ref(act_type_xmlid)
        model_id = self.env['ir.model']._get(self._name).id
        users = self.env['res.users'].search([])
        for rec in users:
            if rec.has_group('manager_all_approvals.group_review_invoice_bill'):
                create_vals = {
                    'activity_type_id': activity_type.id,
                    'summary': summary or activity_type.summary,
                    'automated': True,
                    'note': note,
                    'date_deadline': datetime.today(),
                    'res_model_id': model_id,
                    'res_id': self.id,
                    'user_id': rec.id,
                }
                activities = self.env['mail.activity'].create(create_vals)

    def _create_notification_approval(self):
        act_type_xmlid = 'mail.mail_activity_data_todo'
        summary = 'Waiting for Approval'
        note = 'Document No ' + str(self.name) + ' is waiting for Approval.'
        if act_type_xmlid:
            activity_type = self.sudo().env.ref(act_type_xmlid)
        model_id = self.env['ir.model']._get(self._name).id
        users = self.env['res.users'].search([])
        for rec in users:
            if rec.has_group('manager_all_approvals.group_approve_invoice_bill'):
                create_vals = {
                    'activity_type_id': activity_type.id,
                    'summary': summary or activity_type.summary,
                    'automated': True,
                    'note': note,
                    'date_deadline': datetime.today(),
                    'res_model_id': model_id,
                    'res_id': self.id,
                    'user_id': rec.id,
                }
                activities = self.env['mail.activity'].create(create_vals)

    # def action_posts(self):
    #     if not self.move_type == 'out_invoice':
    #         self._create_notification_review()
    #         self.write({
    #             'state': 'to_review'
    #         })
    #     else:
    #         rec = super(AccountMoveInh, self).action_post()
    #         return rec

    def button_review(self):
        if not self.move_type == 'out_invoice':
            if self.env.user.has_group('manager_all_approvals.group_review_invoice_bill'):
                self.review_by_id = self.env.user.id
            self._create_notification_approval()
            self.write({
                'state': 'approve'
            })

    def action_reset(self):
        self.write({
            'state': 'draft'
        })

    def button_approved(self):
        # if not self.move_type == 'out_invoice':
        if self.env.user.has_group('manager_all_approvals.group_approve_invoice_bill'):
            self.approve_by_id = self.env.user.id
            self._post()

    def button_reject(self):
        if not self.move_type == 'out_invoice':
            self.write({
                'state': 'rejected'
            })

    def button_approve_reject(self):
        if not self.move_type == 'out_invoice':
            self.write({
                'state': 'rejected'
            })


class AccountPaymentInh(models.Model):
    _inherit = 'account.payment'

    review_by_id = fields.Many2one('res.users', string='Reviewed By')
    approve_by_id = fields.Many2one('res.users', string='Approved By')

    # state = fields.Selection([('draft', 'Draft'),
    #                           ('approve', 'Waiting For Approval'),
    #                           ('posted', 'Validated'),
    #                           ('sent', 'Sent'),
    #                           ('reconciled', 'Reconciled'),
    #                           ('cancelled', 'Cancelled'),
    #                           ('reject', 'Reject')
    #                           ], readonly=True, default='draft', copy=False, string="Status")

    # def action_post(self):
    #     # if self.journal_id.type == 'cash':
    #     #     rec = super(AccountPaymentInh, self).action_post()
    #     #     return rec
    #     # else:
    #     self.write({
    #         'state': 'to_review'
    #     })

    def button_review(self):
        if self.env.user.has_group('manager_all_approvals.group_review_payment'):
            self.review_by_id = self.env.user.id
        self.write({
            'state': 'approve'
        })

    def action_reset(self):
        self.write({
            'state': 'draft'
        })

    def button_approved(self):
        if self.env.user.has_group('manager_all_approvals.group_approve_payment'):
            self.approve_by_id = self.env.user.id
        rec = super(AccountPaymentInh, self).action_post()
        return rec

    def button_reject(self):
        self.write({
            'state': 'rejected'
        })

    def button_approve_reject(self):
        self.write({
            'state': 'rejected'
        })


class HrExpenseSheetInh(models.Model):
    _inherit = 'hr.expense.sheet'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('approve', 'Approved'),
        ('review', 'Review'),
        ('approved', 'Approve'),
        ('post', 'Posted'),
        ('done', 'Done'),
        ('cancel', 'Refused')
    ], string='Status', index=True, readonly=True, tracking=True, copy=False, default='draft', required=True,
        help='Expense Report State')

    def action_sheet_move_create(self):
        record = super(HrExpenseSheetInh, self).action_sheet_move_create()
        self.state = 'review'

    def button_review(self):
        self.state = 'approved'

    def button_approved(self):
        self.state = 'post'
