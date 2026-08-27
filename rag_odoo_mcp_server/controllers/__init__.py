# -*- coding: utf-8 -*-

from . import controllers
from . import mcp_controller
# OAuth 2.1 authorization server for the native (mcp-remote-free) Streamable HTTP
# connector. Imported after mcp_controller because it reuses helpers from it.
from . import mcp_oauth
# Access Manager: web/action hook that hides restricted views/actions in the UI.
from . import access_action
