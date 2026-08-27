# -*- coding: utf-8 -*-
{
    "name": "G3C C.A dual currency custom",
    "version": "1.0.1",
    "category": "Account",
    "author": "G3C C.A",
    "contributors": [
        "Ing. Luis Marcano-luismarcano.gucoma@gmail.com",
    ],
    "summary": "dual currency custom - Fix amount_usd in partial reconciliation",
    "description": """
        dual currency custom
        
        Changelog:
        - v1.0.1: Fix amount_usd calculation in account.partial.reconcile when reconciling invoices and payments
    """,
    "depends": [
        "account_dual_currency",
    ],
    "data": [
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
