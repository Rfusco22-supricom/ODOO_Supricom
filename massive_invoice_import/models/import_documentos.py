from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import logging
import pandas as pd
import math
import itertools

_logger = logging.getLogger(__name__)


class ImportDocumentos(models.Model):
    _name = "import.documentos"
    _description = "Importación Masiva de Documentos"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Referencia",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    excel_file = fields.Binary(string="Archivo Excel", required=True, tracking=True)
    filename = fields.Char(string="Nombre de Archivo")

    import_type = fields.Selection([
        ('out_invoice', 'Clientes (Ventas)'),
        ('in_invoice', 'Proveedores (Compras)')
    ], string='Tipo de Importación', default='out_invoice', required=True, tracking=True)

    state = fields.Selection(
        [
            ("draft", "Borrador"),
            ("processing", "Procesando"),
            ("done", "Hecho"),
            ("failed", "Falló"),
        ],
        string="Estado",
        default="draft",
        tracking=True,
    )

    progress = fields.Float(string="Progreso", default=0.0, readonly=True)
    log_notes = fields.Html(string="Registro de Log", readonly=True)
    
    # Async Processing Fields
    last_processed_index = fields.Integer(string="Último Índice Procesado", default=0, help="Índice del último grupo de documentos procesado.")
    total_records_count = fields.Integer(string="Total de Documentos", default=0, help="Total de grupos de documentos para calcular progreso.")
    initial_log_notes = fields.Html(string="Log Inicial (Validación)", help="Log de la validación inicial antes del proceso asíncrono.")

    # Configuration
    product_id = fields.Many2one(
        "product.product", string="Producto por Defecto (Fallback)", required=False,
        help="Si una línea del Excel no tiene un ID de producto válido, se usará este producto. Si se deja vacío, la línea dará error."
    )
    fallback_tax_id = fields.Many2one(
        "account.tax",
        string="Impuesto por Defecto (Fallback)",
        domain=[("type_tax_use", "in", ("sale", "purchase"))],
        help="Si el producto no tiene impuestos configurados, se usará este impuesto.",
    )
    journal_fiscal_id = fields.Many2one(
        "account.journal",
        string="Diario Fiscal",
        domain=[("type", "in", ("sale", "purchase"))],
        required=True,
    )
    journal_entrega_id = fields.Many2one(
        "account.journal",
        string="Diario Notas de Entrega",
        domain=[("type", "in", ("sale", "purchase"))],
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency", 
        string="Moneda de Factura", 
        required=True, 
        default=lambda self: self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
    )

    # Column Mapping Fields
    col_doc_num = fields.Char(
        string="Columna No. Documento", required=True, default="#Docum"
    )
    col_type = fields.Char(string="Columna Tipo", required=True, default="#Tipo")
    col_rif = fields.Char(string="Columna RIF", required=True, default="Rif")
    col_name = fields.Char(
        string="Columna Nombre Cliente", required=True, default="Nombre Cliente odoo"
    )
    col_date = fields.Char(string="Columna Fecha", required=True, default="VenFecha")
    # col_total kept for backward compatibility or removal
    col_total = fields.Char(string="Columna Total", required=True, default="Total")
    
    # New Line Columns
    col_prod_id = fields.Char(string='Columna ID Producto', required=True, default='id de producto')
    col_qty = fields.Char(string='Columna Cantidad', required=True, default='Cant')
    col_price = fields.Char(string='Columna Precio', required=True, default='Precio')
    col_discount = fields.Char(string='Columna Descuento', required=True, default='$Dcto')
    col_tax = fields.Char(string='Columna IVA', required=True, default='Iva')
    
    col_nro_ctrl = fields.Char(
        string="No. Control (#Fiscal)", required=True, default="#Fiscal"
    )
    col_company = fields.Char(string="ID Compañía", required=True, default="#empresa")
    col_vendedor = fields.Char(string="Columna Vendedor", required=True, default="Vendedor")

    # Odoo Target Fields Mapping
    odoo_field_nro_ctrl = fields.Char(
        string="Campo Odoo No. Control",
        required=True,
        default="nro_ctrl",
        help="Nombre técnico del campo en Odoo donde se guardará el Número de Control (ej: nro_ctrl, l10n_ve_document_number, x_nro_control)",
    )

    @api.model
    def create(self, vals):
        if vals.get("name", _("New")) == _("New"):
            vals["name"] = self.env["ir.sequence"].next_by_code(
                "import.documentos"
            ) or _("New")
        return super(ImportDocumentos, self).create(vals)

    def action_process_file(self):
        """Inicia el proceso, valida columnas y deja en estado 'processing' para el Cron."""
        self.ensure_one()
        
        # 1. Validación Inicial y Preparación
        try:
            file_content = base64.b64decode(self.excel_file)
            data = io.BytesIO(file_content)
            # Leer solo columnas para validar rápido
            df_header = pd.read_excel(data, nrows=5) 
        except Exception as e:
            raise UserError(_("Error al leer el archivo Excel: %s") % str(e))

        # Validación de Columnas
        self._validate_columns(df_header)

        # Contar total de grupos para el progreso
        try:
            # Leer todo para agrupar y contar (es rápido en memoria, lo lento es crear las facturas)
            data.seek(0)
            df = pd.read_excel(data)
            # Normalizar columnas
            df.columns = df.columns.astype(str).str.strip()
            
            # Agrupar para saber cuántos documentos son
            grouped = df.groupby(self.col_doc_num)
            total_groups = len(grouped)
        except Exception as e:
            raise UserError(_("Error al analizar estructura del Excel: %s") % str(e))

        # 2. Actualizar Estado
        self.write({
            "state": "processing", 
            "progress": 0.0, 
            "log_notes": "",
            "last_processed_index": 0,
            "total_records_count": total_groups,
            "initial_log_notes": f"<p style='color:blue'>Iniciando proceso para {total_groups} documentos...</p>"
        })
        
        # 3. Disparar Cron Manualmente (opcional)
        try:
            self.env.ref('massive_invoice_import.ir_cron_import_documentos_queue')._trigger()
        except ValueError:
            pass 
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_process_batch_manually(self):
        """Permite procesar el siguiente lote manualmente desde la vista."""
        self.ensure_one()
        if self.state == 'processing':
            self.with_context(manual_trigger=True)._process_import_batch()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _validate_columns(self, df):
        """Valida que existan las columnas requeridas"""
        required_columns = [
            self.col_doc_num, self.col_type, self.col_rif, self.col_name,
            self.col_date, self.col_nro_ctrl, self.col_company,
            self.col_prod_id, self.col_qty, self.col_price, self.col_tax,
            self.col_vendedor,
        ]
        # Strip whitespace setup
        df.columns = df.columns.astype(str).str.strip()
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise UserError(
                _("El archivo Excel no tiene las columnas configuradas: %s")
                % ", ".join(missing_columns)
            )

    @api.model
    def _cron_process_imports(self):
        """Método llamado por el Cron para procesar lotes"""
        records = self.search([('state', '=', 'processing')], limit=1)
        for record in records:
            record._process_import_batch()

    def _process_import_batch(self):
        """Procesa un lote de registros manteniendo estado"""
        self.ensure_one()
        
        # --- LOCKING MECHANISM ---
        try:
            self.env.cr.execute("SELECT last_processed_index, state FROM import_documentos WHERE id = %s FOR UPDATE NOWAIT", [self.id])
            self.invalidate_recordset(['last_processed_index', 'state', 'total_records_count'])
        except Exception:
            _logger.warning(f"Importación {self.id} bloqueada por otro proceso. Saltando ejecución.")
            if self.env.context.get('manual_trigger'):
                raise UserError(_("El proceso ya está en ejecución en segundo plano. Por favor espere o intente nuevamente en unos segundos."))
            return

        if self.state != 'processing':
            return

        BATCH_LIMIT = 500  # Aumentado a 500 para mayor rendimiento con create_multi
        
        try:
            # 1. Preparar Datos (Leer Batch)
            file_content = base64.b64decode(self.excel_file)
            data = io.BytesIO(file_content)
            df = pd.read_excel(data)
            df.columns = df.columns.astype(str).str.strip()
            
            grouped = df.groupby(self.col_doc_num)
            
            start = self.last_processed_index
            end = start + BATCH_LIMIT
            
            batch_groups = list(itertools.islice(grouped, start, end))
            
            if not batch_groups:
                if start >= self.total_records_count or self.last_processed_index > 0:
                     self.write({'state': 'done', 'progress': 100.0, 'log_notes': (self.log_notes or "") + "<p style='color:green; font-weight:bold'>Proceso Finalizado Exitosamente.</p>"})
                     return

            # 2. Pre-fetch Optimization (Partners)
            # Recolectar todos los RIFs del batch para hacer una sola búsqueda
            rifs_to_search = set()
            names_to_search = set()
            for _, group in batch_groups:
                try: 
                    row = group.iloc[0]
                    rif = str(row[self.col_rif]).strip() if pd.notna(row[self.col_rif]) else ""
                    if rif: rifs_to_search.add(rif)
                    name = str(row[self.col_name]).strip() if pd.notna(row[self.col_name]) else ""
                    if name: names_to_search.add(name)
                except: pass
            
            # Buscar Partners existentes en lote
            partner_map = {} # key: rif or name -> partner_id
            if rifs_to_search:
                partners_rif = self.env["res.partner"].search([
                    ("vat", "in", list(rifs_to_search)),
                    "|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)
                ])
                for p in partners_rif:
                    partner_map[p.vat] = p
                    if "rif" in p._fields and p.rif: partner_map[p.rif] = p
            
            # 2b. Pre-fetch Optimization (Users/Salespersons)
            user_map = {} # key: name.lower() -> user_id
            if batch_groups:
                user_names = set()
                for _, group in batch_groups:
                    try:
                        row = group.iloc[0]
                        v_name = str(row[self.col_vendedor]).strip() if pd.notna(row[self.col_vendedor]) else ""
                        if v_name: user_names.add(v_name)
                    except: pass
                if user_names:
                    # Search by name. We use 'in' for efficiency, and then map in Python for case-insensitivity.
                    users = self.env["res.users"].search([("name", "in", list(user_names))])
                    for u in users:
                        user_map[u.name.strip().lower()] = u.id
                    
                    # Also try to find those that didn't match exactly by name (relaxed search if few names)
                    remaining = [n for n in user_names if n.lower() not in user_map]
                    if remaining and len(remaining) < 50:
                        domain = ['|'] * (len(remaining) - 1) + [('name', '=ilike', n) for n in remaining]
                        relaxed_users = self.env["res.users"].search(domain)
                        for u in relaxed_users:
                            user_map[u.name.strip().lower()] = u.id
            
            # 3. Construir Vals List
            vals_list = []
            doc_numbers_in_batch = []
            
            # Mapeo temporal para errores específicos si falla el bullk
            vals_map_debug = {} 

            processed_in_this_batch = 0
            new_errors = []

            for doc_number, group in batch_groups:
                try:
                    row = group.iloc[0]
                    
                    # --- Header Parsing ---
                    doc_type_raw = row[self.col_type]
                    doc_type = str(doc_type_raw).strip().upper() if pd.notna(doc_type_raw) else ""
                    
                    rif_raw = row[self.col_rif]
                    rif = str(rif_raw).strip() if pd.notna(rif_raw) else ""
                    
                    name_raw = row[self.col_name]
                    partner_name = str(name_raw).strip() if pd.notna(name_raw) else ""
                    
                    nro_ctrl_raw = row[self.col_nro_ctrl]
                    nro_ctrl = str(nro_ctrl_raw).strip() if pd.notna(nro_ctrl_raw) else False
                    
                    date_invoice = row[self.col_date]
                    company_raw = row.get(self.col_company)
                    vendedor_raw = row[self.col_vendedor]
                    vendedor_name = str(vendedor_raw).strip() if pd.notna(vendedor_raw) else ""
                    
                    # --- Salesperson Lookup ---
                    v_id = False
                    if vendedor_name:
                        v_id = user_map.get(vendedor_name.lower())
                        if not v_id:
                            # Final attempt: direct search if not in map (should be rare now)
                            user = self.env["res.users"].search([("name", "=ilike", vendedor_name)], limit=1)
                            if user:
                                v_id = user.id
                                user_map[vendedor_name.lower()] = v_id
                            else:
                                new_errors.append(f"Doc {doc_number}: Vendedor '{vendedor_name}' no encontrado en Odoo")
                    
                    # --- Company Check ---
                    if pd.notna(company_raw):
                        try:
                            if int(float(company_raw)) != self.env.company.id:
                                processed_in_this_batch += 1; continue
                        except: pass
                    
                    # --- Journal Logic ---
                    journal_id = False
                    
                    base_type = "out" if self.import_type == 'out_invoice' else "in"
                    
                    if doc_type in ("FAC", "FC"): journal_id = self.journal_fiscal_id.id; move_type = f"{base_type}_invoice"
                    elif doc_type in ("CRE", "NC"): journal_id = self.journal_fiscal_id.id; move_type = f"{base_type}_refund"
                    elif doc_type == "ENT": journal_id = self.journal_entrega_id.id; move_type = f"{base_type}_invoice"
                    elif doc_type == "END": journal_id = self.journal_entrega_id.id; move_type = f"{base_type}_refund"
                    else:
                        new_errors.append(f"Doc {doc_number}: Tipo '{doc_type}' desconocido"); processed_in_this_batch += 1; continue

                    # --- Partner Logic ---
                    partner = partner_map.get(rif)
                    if not partner and partner_name:
                         # Fallback simple search by name if not in map (could be improved)
                         partner = self.env["res.partner"].search([
                             ("name", "=", partner_name),
                             "|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)
                         ], limit=1)
                    
                    if not partner:
                        # Crear al vuelo (esto sí es write y es lento, pero necesario si no existe)
                        rank_field = "customer_rank" if self.import_type == 'out_invoice' else "supplier_rank"
                        vals_create = {
                            "name": partner_name or "Cliente Desconocido", 
                            "vat": rif, 
                            rank_field: 1,
                            "company_id": self.env.company.id
                        }
                        if rif and "rif" in self.env["res.partner"]._fields: vals_create["rif"] = rif
                        partner = self.env["res.partner"].create(vals_create)
                        if rif: partner_map[rif] = partner # Cache for next loop

                    # --- Lines Logic ---
                    invoice_lines = []
                    for index, line_row in group.iterrows():
                        prod_id_val = line_row.get(self.col_prod_id)
                        product = False
                        
                        # Product Search (should be optimized with cache too, but keeping simple for now)
                        if pd.notna(prod_id_val):
                            prod_str = str(prod_id_val).strip()
                            # Handle pandas parsing ints as floats (e.g. 1234.0)
                            if prod_str.endswith(".0"):
                                prod_str = prod_str[:-2]
                            
                            # 1. Primary search by Internal Reference or Barcode
                            local_product = self.env['product.product'].search([
                                '|', ('default_code', '=', prod_str), ('barcode', '=', prod_str),
                                '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id)
                            ], limit=1)
                            
                            if local_product:
                                product = local_product
                            else:
                                # 2. Secondary search by Database ID
                                try:
                                    original_product = self.env['product.product'].browse(int(float(prod_id_val)))
                                    if original_product.exists():
                                        if original_product.company_id and original_product.company_id != self.env.company:
                                            # Try to find a local company product with the same name
                                            local_p = self.env['product.product'].search([
                                                ('name', '=', original_product.name),
                                                '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id)
                                            ], limit=1)
                                            product = local_p if local_p else original_product
                                        else:
                                            product = original_product
                                except: pass
                        
                        if not product:
                            if self.product_id: 
                                product = self.product_id
                            else: 
                                new_errors.append(f"Doc {doc_number}: Sin producto válido ni default."); continue

                        qty = float(line_row.get(self.col_qty, 1.0)) if pd.notna(line_row.get(self.col_qty)) else 1.0
                        price = float(line_row.get(self.col_price, 0.0)) if pd.notna(line_row.get(self.col_price)) else 0.0
                        
                        # Odoo siempre espera montos positivos en las líneas de factura.
                        # El tipo de documento (in_refund / out_refund) es el que determina el impacto contable.
                        qty = abs(qty)
                        price = abs(price)
                        
                        # Discount
                        discount = 0.0
                        disc_val = line_row.get(self.col_discount)
                        if pd.notna(disc_val):
                            if isinstance(disc_val, str):
                                try: discount = float(disc_val.replace('%', '').replace(',', '.').strip())
                                except: discount = 0.0
                            else: discount = float(disc_val)

                        # Tax
                        tax_val_raw = line_row.get(self.col_tax, 0.0)
                        tax_amount_excel = 0.0
                        try: tax_amount_excel = float(tax_val_raw)
                        except: pass
                        
                        tax_ids = []
                        if not math.isclose(tax_amount_excel, 0.0, abs_tol=0.01) and product:
                             use_fallback = not product.taxes_id or all(t.amount == 0 for t in product.taxes_id)
                             found_taxes = self.fallback_tax_id if (use_fallback and self.fallback_tax_id) else product.taxes_id
                             tax_ids = [t.id for t in found_taxes if not t.company_id or t.company_id == self.env.company]

                        if product:
                            invoice_lines.append((0, 0, {
                                'product_id': product.id,
                                'name': product.name,
                                'quantity': qty,
                                'price_unit': price,
                                'discount': discount,
                                'tax_ids': [(6, 0, tax_ids)],
                            }))

                    if not invoice_lines:
                         if not any(e.startswith(f"Doc {doc_number}") for e in new_errors):
                             new_errors.append(f"Doc {doc_number}: Sin líneas válidas")
                         processed_in_this_batch += 1
                         continue

                    # --- Invoice Vals ---
                    invoice_vals = {
                        "move_type": move_type,
                        "journal_id": journal_id,
                        "partner_id": partner.id,
                        "invoice_date": date_invoice,
                        "currency_id": self.currency_id.id,
                        "invoice_user_id": v_id,
                        "ref": f"Importación Masiva - {doc_type} {doc_number}",
                        "invoice_line_ids": invoice_lines,
                    }
                    if nro_ctrl and self.odoo_field_nro_ctrl:
                         invoice_vals[self.odoo_field_nro_ctrl] = nro_ctrl
                    
                    vals_list.append(invoice_vals)
                    doc_numbers_in_batch.append(doc_number)
                    processed_in_this_batch += 1

                except Exception as e:
                    new_errors.append(f"Doc {doc_number} (Preparación): {str(e)}")
                    processed_in_this_batch += 1 # Contamos como procesado (fallido) para avanzar índice
            
            # 4. BULK CREATE
            created_moves = self.env['account.move']
            if vals_list:
                try:
                    # Intento masivo (rápido)
                    created_moves = self.env['account.move'].create(vals_list)
                except Exception as e:
                    # Fallback paso a paso (lento pero seguro)
                    _logger.warning(f"Batch Create failed ({e}). Retrying one by one for robustness.")
                    for idx, val in enumerate(vals_list):
                        try:
                            m = self.env['account.move'].create(val)
                            created_moves += m
                        except Exception as inner_e:
                            doc_ref = doc_numbers_in_batch[idx]
                            new_errors.append(f"Doc {doc_ref} (Creación BD): {str(inner_e)}")
            
            # 5. POST BATCH
            # Postear también en lote (o uno a uno si falla)
            self._post_batch_moves(created_moves, new_errors)

            # 6. Actualizar Progreso
            new_index = start + processed_in_this_batch
            
            progress_val = 100.0
            if self.total_records_count > 0:
                progress_val = (new_index / self.total_records_count) * 100
                if progress_val > 99.0 and new_index < self.total_records_count: progress_val = 99.0 
            
            log_chunk = ""
            if new_errors:
                 log_chunk = "<ul>" + "".join([f"<li>{err}</li>" for err in new_errors]) + "</ul>"
            
            vals_write = {
                'last_processed_index': new_index,
                'progress': progress_val,
                'log_notes': (self.log_notes or "") + f"<p style='color:green; font-size: 0.9em'>[{fields.Datetime.now()}] Procesado Lote: {start}-{new_index} ({int(progress_val)}%)</p>" + log_chunk
            }

            done = False
            if new_index >= self.total_records_count or not batch_groups:
                vals_write['state'] = 'done'
                vals_write['progress'] = 100.0
                vals_write['log_notes'] += "<p style='color:green; font-weight:bold'>Proceso Finalizado Exitosamente.</p>"
            
            self.write(vals_write)
            self.env.cr.commit()

        except Exception as e:
            self.env.cr.rollback()
            _logger.exception("Error en Cron de Importación Masiva")
            self.write({
                'state': 'failed',
                'log_notes': (self.log_notes or "") + f"<p style='color:red'>Crash del Sistema: {str(e)}</p>"
            })
            self.env.cr.commit()

    def _post_batch_moves(self, moves, errors):
        """Helper to post a batch of moves. If batch fails, try one by one."""
        if not moves:
            return
        
        try:
            # Try to post all at once (Fastest)
            moves.action_post()
        except Exception as batch_e:
            _logger.warning(f"Batch post failed, retrying one by one: {batch_e}")
            # Fallback: Post one by one to find the specific error
            for move in moves:
                try:
                    move.action_post()
                except Exception as e:
                    errors.append(f"Doc {move.ref}: Error al confirmar factura: {str(e)}")

    # _process_file_logic is deprecated/replaced
    pass
