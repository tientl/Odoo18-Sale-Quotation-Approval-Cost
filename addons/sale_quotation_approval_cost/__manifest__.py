{
    'name': 'Sale Quotation Approval Cost',
    'version': '1.0',
    'summary': 'A custom module for Odoo',
    'description': 'This is a Sale Quotation Approval Cost module.',
    'author': 'TienLT',
    'depends': ['sale'],
    'data': [
        # 'security/sale_approval_security.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'assets': {
        'web.assets_backend': [
            'sale_quotation_approval_cost/static/src/components/**/*'
        ]
    },
}