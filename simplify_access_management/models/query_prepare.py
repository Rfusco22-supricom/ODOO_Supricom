from odoo.tools import SQL


def search_data(self, from_model, search_model=False, condition=False, operator=False, limit=0):
    try:
        if from_model:
            model_obj = self.env[from_model]
            model_obj.exists()
            from_model_table = model_obj._table
            company_ids = tuple(self.env.company.ids)
            
            if condition:
                if condition[0] in model_obj._fields:
                    field_name = condition[0]
                    op = condition[1]
                    val = condition[2]
                    
                    if from_model_table == 'access_management':
                        sql_condition = "am.{field} {op} %s".format(field=field_name, op=op)
                        
                        query = """SELECT am.id
                                FROM access_management AS am
                                WHERE am.active = TRUE
                                AND EXISTS (
                                    SELECT 1 FROM access_management_users_rel_ah AS rel 
                                    WHERE rel.access_management_id = am.id AND rel.user_id = %s
                                )
                                AND (
                                    am.is_apply_on_without_company = TRUE
                                    OR EXISTS (
                                        SELECT 1 FROM access_management_comapnay_rel AS rel_com
                                        WHERE rel_com.access_management_id = am.id AND rel_com.company_id IN %s
                                    )
                                )
                                {operator} {condition}""".format(
                                    operator=operator if operator else "",
                                    condition=sql_condition
                                )
                        
                        self._cr.execute(query, (self.env.user.id, company_ids, val))
                        
                        if limit > 0:
                            row = self._cr.fetchone()
                            result = row[0] if row else False
                        else:
                            result = [x[0] for x in self._cr.fetchall()]
                        return model_obj.sudo().browse(result)
                    else:
                        if search_model:
                            search_model_obj = self.env[search_model]
                            search_model_obj.exists()
                            sql_condition = "ft.{field} {op} %s".format(field=field_name, op=op)
                            
                            query = """SELECT ft.id
                                    FROM {table} AS ft
                                    WHERE EXISTS (
                                        SELECT 1
                                        FROM access_management AS am
                                        JOIN access_management_users_rel_ah AS rel_user 
                                        ON am.id = rel_user.access_management_id
                                        WHERE rel_user.user_id = %s
                                        AND am.active
                                        AND am.id = ft.access_management_id
                                    )
                                    AND EXISTS (
                                        SELECT 1
                                        FROM ir_model AS im
                                        WHERE im.id = ft.model_id
                                        AND im.model = %s
                                    )
                                    AND (
                                        (SELECT am.is_apply_on_without_company
                                        FROM access_management am
                                        WHERE am.id = ft.access_management_id)
                                    OR EXISTS (
                                        SELECT 1
                                        FROM access_management_comapnay_rel AS rel_comp 
                                        WHERE rel_comp.access_management_id = ft.access_management_id
                                            AND rel_comp.company_id IN %s
                                    )
                                    )
                                    {operator} {condition}""".format(
                                        table=from_model_table,
                                        operator=operator if operator else "",
                                        condition=sql_condition
                                    )
                            
                            self._cr.execute(query, (self.env.user.id, search_model, company_ids, val))
                            
                            if limit > 0:
                                row = self._cr.fetchone()
                                result = row[0] if row else False
                            else:
                                result = [x[0] for x in self._cr.fetchall()]
                            return model_obj.sudo().browse(result)   

            else:
                if from_model != 'access.management' and search_model:
                    self.env[search_model].exists()
                    query = """SELECT ft.id
                                FROM {table} AS ft
                                WHERE EXISTS (
                                    SELECT 1
                                    FROM access_management AS am
                                    JOIN access_management_users_rel_ah AS rel_user 
                                    ON am.id = rel_user.access_management_id
                                    WHERE rel_user.user_id = %s
                                    AND am.active
                                    AND am.id = ft.access_management_id
                                )
                                AND EXISTS (
                                    SELECT 1
                                    FROM ir_model AS im
                                    WHERE im.id = ft.model_id
                                    AND im.model = %s
                                )
                                AND (
                                    (SELECT am.is_apply_on_without_company
                                    FROM access_management am
                                    WHERE am.id = ft.access_management_id)
                                OR EXISTS (
                                    SELECT 1
                                    FROM access_management_comapnay_rel AS rel_comp 
                                    WHERE rel_comp.access_management_id = ft.access_management_id
                                        AND rel_comp.company_id IN %s
                                )
                                )""".format(table=from_model_table)
                    self._cr.execute(query, (self.env.user.id, search_model, company_ids))
                    if limit > 0:
                        row = self._cr.fetchone()
                        result = row[0] if row else False
                    else:
                        result = [x[0] for x in self._cr.fetchall()]
                    if result:
                        return model_obj.sudo().browse(result)
            return False
    except Exception:
        return False
            