# -*- coding: utf-8 -*-

import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.warning("\n**** Pre update whatsapp_connector from version %s to 0.0.0 ****" % version)

    cr.execute('''UPDATE acrux_chat_conversation 
                  SET conv_type='normal' 
                  WHERE conv_type='none' 
               ''')
