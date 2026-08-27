# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.exceptions import ValidationError

from odoo.tests import tagged, HttpCase
from odoo.addons.helpdesk.tests.common import HelpdeskCommon

@tagged('-at_install', 'post_install')
class TestHelpdeskKnowledgeTour(HttpCase, HelpdeskCommon):

    def test_helpdesk_knowledge_article_constrains(self):
        Article = self.env['knowledge.article']
        Article.search([]).unlink()
        help_article, other_article = Article.create([{
            'name': 'Helpdesk Article',
            'is_published': True,
            'body': 'help',
        }, {
            'name': 'Other Article',
            'is_published': True,
            'body': 'other',
        }])
        self.test_team.write({
            'use_website_helpdesk_knowledge': True,
            'website_article_id': help_article.id,
        })
        with self.assertRaises(ValidationError):
            help_article.write({
                'is_published': False,
            })
        with self.assertRaises(ValidationError):
            help_article.write({
                'parent_id': other_article.id,
            })
        with self.assertRaises(ValidationError):
            help_article.write({
                'active': False,
            })

    def test_helpdesk_knowledge_article_only_list_linked_articles(self):
        """
        Test Case:
        ==========
        - have multiple published articles
        - check that only the linked article  or its children are proposed as "latest article" for the team
        """
        Article = self.env['knowledge.article']
        Article.search([]).unlink()
        help_article, _unused = Article.create([{
            'name': 'Helpdesk Article',
            'is_published': True,
            'body': 'help',
        }, {
            'name': 'Other Article',
            'is_published': True,
            'body': 'other',
        }])
        child_article = Article.create({
            'name': 'Child Article',
            'is_published': True,
            'parent_id': help_article.id,
        })
        self.test_team.write({
            'use_website_helpdesk_knowledge': True,
            'website_article_id': help_article.id,
        })
        self.assertEqual(self.test_team.website_latest_articles, help_article + child_article)
