================================================================
Audit Log App
================================================================

The Audit Log Module for Odoo, a tool designed to track and log various user actions such as Create, Read, Update, and Delete (CRUD) operations across different data models.


**Table of contents**
 
.. contents::
   :local:
 
**Key Features**
================================================================

- **Full CRUD Logging**: This feature allows system administrators to define which CRUD (Create, Read, Update, Delete) operations are logged for each data model within Odoo.
- **Log Grouping and Filtering**: Provides administrators with the ability to group and filter logs based on various parameters, such as user sessions, dates, data models, and HTTP requests.
- **Automatic Log Cleanup**: The Automatic Log Cleanup feature ensures that the system automatically deletes logs that are older than six months (or a custom-defined timeframe).
- **Role-Based Access Control (RBAC)**: This feature introduces predefined roles within the audit log system to ensure that only authorized users can view or manage logs.
- **Audit Log Notifications**: This feature sends notifications to system administrators or relevant users when critical actions are logged. Notifications can be triggered for specific actions.

**Summary**
================================================================

The Audit Log Odoo App is designed to meticulously track and log user actions, including Create,Read, Update, and Delete (CRUD) operations across various data models. This module ensures transparency and accountability, providing a comprehensive record of key operations to help maintain data integrity within the Odoo system.


**Installation**
================================================================

1. Download the module from the Odoo App Store or clone the repository.
2. Place the module in your Odoo addons directory.
3. Update your Odoo instance to include the new module.
4. Install the module through the Odoo interface.

**How to use this module:**
================================================================

1. Navigate to the Audit Log app in your Odoo dashboard.
2. **Audit Setting**: Go to Settings / Technical / Audit.
3. **Rule**: Select Model from Log.
4. **Logs**: Check logs in the Settings / Technical / Audit / Logs menu.

Change logs
================================================================

[1.0.0]

* ``Added`` [08-10-2024]- Audit Log App

Support
================================================================
 
`Zehntech Technologies <https://www.zehntech.com/erp-crm/odoo-services/>`_