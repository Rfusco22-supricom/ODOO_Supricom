# -*- coding: utf-8 -*-
import base64
import io
import csv
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

try:
    import openpyxl
except ImportError:
    openpyxl = None


class ImportSerialsSalesWizard(models.TransientModel):
    _name = 'import.serials.sales.wizard'
    _description = 'Asistente de Importación Masiva de Seriales para Ventas y Despachos'

    picking_id = fields.Many2one('stock.picking', string='Despacho / Transferencia')
    move_id = fields.Many2one('account.move', string='Factura de Venta')
    import_type = fields.Selection([
        ('picking', 'Despacho (stock.picking)'),
        ('invoice', 'Factura de Venta (account.move)'),
    ], string='Tipo de Documento', default='picking', required=True)

    excel_file = fields.Binary(string='Archivo Excel / CSV', required=True)
    file_name = fields.Char(string='Nombre del Archivo')

    has_header = fields.Boolean(string='Tiene Encabezado', default=True, help='Indica si la primera fila contiene los títulos de columna.')
    auto_create_lots = fields.Boolean(
        string='Crear Lotes/Seriales Inexistentes',
        default=False,
        help='Si el serial no existe en inventario, lo crea automáticamente. Si está desmarcado, arrojará un error.'
    )

    template_file = fields.Binary(string='Plantilla Descargable', readonly=True)
    template_name = fields.Char(string='Nombre Plantilla', default='plantilla_seriales_ventas.xlsx')

    state = fields.Selection([
        ('draft', 'Selección de Archivo'),
        ('done', 'Resultado'),
    ], default='draft')
    log_output = fields.Text(string='Resultado del Proceso', readonly=True)

    def _parse_file(self):
        """Lee el archivo base64 (Excel .xlsx o CSV) y retorna una lista de tuplas (product_ref, serial_str)"""
        self.ensure_one()
        if not self.excel_file:
            raise UserError(_("Por favor, seleccione un archivo Excel o CSV."))

        file_bytes = base64.b64decode(self.excel_file)
        rows_data = []

        is_csv = self.file_name and self.file_name.lower().endswith('.csv')

        if is_csv:
            try:
                content = file_bytes.decode('utf-8-sig', errors='ignore')
                csv_reader = csv.reader(io.StringIO(content))
                for row in csv_reader:
                    if not row or not any(row):
                        continue
                    rows_data.append([str(cell).strip() for cell in row])
            except Exception as e:
                raise UserError(_("Error al leer el archivo CSV: %s") % str(e))
        else:
            if not openpyxl:
                raise UserError(_("La librería 'openpyxl' no está disponible en el servidor Odoo para leer archivos .xlsx."))
            try:
                wb = openpyxl.load_workbook(filename=io.BytesIO(file_bytes), data_only=True)
                sheet = wb.active
                for row in sheet.iter_rows(values_only=True):
                    if not row or not any(row):
                        continue
                    rows_data.append([str(cell).strip() if cell is not None else '' for cell in row])
            except Exception as e:
                raise UserError(_("Error al abrir el archivo Excel: %s") % str(e))

        if not rows_data:
            raise UserError(_("El archivo está vacío o no contiene filas válidas."))

        if self.has_header and len(rows_data) > 1:
            rows_data = rows_data[1:]

        parsed_items = []
        for line_idx, row in enumerate(rows_data, start=2 if self.has_header else 1):
            if len(row) >= 2:
                product_ref = row[0].strip()
                serial_num = row[1].strip()
            elif len(row) == 1:
                product_ref = ''
                serial_num = row[0].strip()
            else:
                continue

            if serial_num:
                parsed_items.append((product_ref, serial_num, line_idx))

        if not parsed_items:
            raise UserError(_("No se encontraron números de serie válidos en el archivo cargado."))

        return parsed_items

    def action_import_serials(self):
        self.ensure_one()
        parsed_items = self._parse_file()
        logs = []

        if self.import_type == 'picking' and self.picking_id:
            logs = self._process_picking_serials(parsed_items)
        elif self.import_type == 'invoice' and self.move_id:
            logs = self._process_invoice_serials(parsed_items)
        else:
            raise UserError(_("No se ha especificado un documento válido para importar seriales."))

        self.write({
            'state': 'done',
            'log_output': '\n'.join(logs)
        })

        return {
            'name': _('Resultado de Importación de Seriales'),
            'type': 'ir.actions.act_window',
            'res_model': 'import.serials.sales.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _find_product(self, ref):
        """Busca producto por referencia interna (default_code), código de barras o nombre exacto"""
        if not ref:
            return False
        Product = self.env['product.product']
        prod = Product.search([('default_code', '=', ref)], limit=1)
        if not prod:
            prod = Product.search([('barcode', '=', ref)], limit=1)
        if not prod:
            prod = Product.search([('name', '=', ref)], limit=1)
        return prod

    def _process_picking_serials(self, parsed_items):
        picking = self.picking_id
        if picking.state in ('done', 'cancel'):
            raise UserError(_("No se pueden agregar seriales a un despacho en estado Realizado o Cancelado."))

        logs = [f"=== Procesando Despacho {picking.name} ==="]
        processed_count = 0
        created_lots_count = 0

        # Obtener los movimientos del despacho
        moves = picking.move_ids_without_package
        if not moves:
            moves = picking.move_ids

        tracked_moves = moves.filtered(lambda m: m.product_id and m.product_id.tracking in ('serial', 'lot'))
        if not tracked_moves:
            raise UserError(_("El despacho %s no contiene productos configurados con seguimiento por Lote/Serial.") % picking.name)

        # Mapeo de productos a movimientos
        prod_move_map = {m.product_id.id: m for m in tracked_moves}

        missing_lots = []

        for prod_ref, serial_num, line_idx in parsed_items:
            product = self._find_product(prod_ref)

            # Si no se especificó producto en la fila pero solo hay 1 movimiento rastreado en el despacho
            if not product and len(tracked_moves) == 1:
                product = tracked_moves[0].product_id
            elif not product:
                logs.append(f"[Fila {line_idx}] ERROR: Producto '{prod_ref}' no encontrado en el sistema.")
                continue

            if product.id not in prod_move_map:
                logs.append(f"[Fila {line_idx}] ADVERTENCIA: El producto '{product.display_name}' no pertenece a los ítems de este despacho.")
                continue

            move = prod_move_map[product.id]

            # Buscar o crear el lote/serial
            Lot = self.env['stock.lot']
            lot = Lot.search([
                ('product_id', '=', product.id),
                ('name', '=', serial_num),
                ('company_id', '=', picking.company_id.id)
            ], limit=1)

            if not lot:
                if self.auto_create_lots:
                    lot = Lot.create({
                        'name': serial_num,
                        'product_id': product.id,
                        'company_id': picking.company_id.id,
                    })
                    created_lots_count += 1
                    logs.append(f"[Fila {line_idx}] Creado nuevo serial '{serial_num}' para {product.default_code or product.name}")
                else:
                    missing_lots.append(f"Fila {line_idx}: Serial '{serial_num}' (Producto: {product.display_name})")
                    continue

            # Asignar a stock.move.line
            existing_sml = move.move_line_ids.filtered(lambda ml: ml.lot_id.id == lot.id)
            if existing_sml:
                existing_sml.quantity = 1.0
                logs.append(f"[Fila {line_idx}] Serial '{serial_num}' ya estaba asignado a este despacho. Se actualizó la cantidad a 1.")
            else:
                # Buscar una línea sin serial asignado
                empty_sml = move.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.quantity == 0.0)
                if empty_sml:
                    empty_sml[:1].write({
                        'lot_id': lot.id,
                        'quantity': 1.0,
                    })
                else:
                    self.env['stock.move.line'].create({
                        'picking_id': picking.id,
                        'move_id': move.id,
                        'product_id': product.id,
                        'product_uom_id': move.product_uom.id,
                        'location_id': move.location_id.id,
                        'location_dest_id': move.location_dest_id.id,
                        'lot_id': lot.id,
                        'quantity': 1.0,
                    })
                logs.append(f"[Fila {line_idx}] Asignado serial '{serial_num}' a {product.display_name}")

            processed_count += 1

        if missing_lots and not self.auto_create_lots:
            raise ValidationError(_("Los siguientes seriales no existen en el inventario:\n\n%s\n\nActive la opción 'Crear Lotes/Seriales Inexistentes' si desea crearlos automáticamente.") % '\n'.join(missing_lots))

        logs.append(f"\n[RESUMEN]: Se asignaron exitosamente {processed_count} serial(es). Lotes creados: {created_lots_count}.")

        # Actualizar estado de picked en el despacho
        for m in tracked_moves:
            if m.move_line_ids:
                m.picked = True

        return logs

    def _process_invoice_serials(self, parsed_items):
        move = self.move_id
        if move.state != 'draft':
            raise UserError(_("Solo se pueden asociar seriales a facturas en borrador."))

        logs = [f"=== Procesando Factura {move.name or 'NUEVA'} ==="]
        processed_count = 0

        invoice_lines = move.invoice_line_ids.filtered(lambda l: l.product_id and l.product_id.tracking in ('serial', 'lot'))
        if not invoice_lines:
            raise UserError(_("La factura no contiene productos con seguimiento por Lote/Serial."))

        prod_line_map = {l.product_id.id: l for l in invoice_lines}
        product_serials_dict = {}

        for prod_ref, serial_num, line_idx in parsed_items:
            product = self._find_product(prod_ref)
            if not product and len(invoice_lines) == 1:
                product = invoice_lines[0].product_id
            elif not product:
                logs.append(f"[Fila {line_idx}] ERROR: Producto '{prod_ref}' no encontrado.")
                continue

            if product.id not in prod_line_map:
                logs.append(f"[Fila {line_idx}] ADVERTENCIA: El producto '{product.display_name}' no pertenece a la factura.")
                continue

            if product.id not in product_serials_dict:
                product_serials_dict[product.id] = []
            product_serials_dict[product.id].append(serial_num)
            processed_count += 1

        # Actualizar las líneas de factura incorporando los seriales a la descripción o notas
        for prod_id, serials in product_serials_dict.items():
            inv_line = prod_line_map[prod_id]
            serials_str = ", ".join(serials)
            current_desc = inv_line.name or ''
            if "Seriales:" in current_desc:
                new_desc = current_desc.split("\nSeriales:")[0] + f"\nSeriales: {serials_str}"
            else:
                new_desc = current_desc + f"\nSeriales: {serials_str}"

            inv_line.write({'name': new_desc})

            # Si la factura está vinculada a despachos/move_line_ids, asociar a los stock.move
            if hasattr(inv_line, 'move_line_ids') and inv_line.move_line_ids:
                for sm in inv_line.move_line_ids:
                    for s_num in serials:
                        lot = self.env['stock.lot'].search([
                            ('product_id', '=', prod_id),
                            ('name', '=', s_num),
                            ('company_id', '=', move.company_id.id)
                        ], limit=1)
                        if not lot and self.auto_create_lots:
                            lot = self.env['stock.lot'].create({
                                'name': s_num,
                                'product_id': prod_id,
                                'company_id': move.company_id.id,
                            })
                        if lot:
                            empty_sml = sm.move_line_ids.filtered(lambda ml: not ml.lot_id)
                            if empty_sml:
                                empty_sml[:1].write({'lot_id': lot.id, 'quantity': 1.0})
                            else:
                                self.env['stock.move.line'].create({
                                    'picking_id': sm.picking_id.id if sm.picking_id else False,
                                    'move_id': sm.id,
                                    'product_id': prod_id,
                                    'product_uom_id': sm.product_uom.id,
                                    'location_id': sm.location_id.id,
                                    'location_dest_id': sm.location_dest_id.id,
                                    'lot_id': lot.id,
                                    'quantity': 1.0,
                                })

            logs.append(f"Línea '{inv_line.product_id.display_name}': Se agregaron {len(serials)} serial(es) en la descripción y movimientos.")

        logs.append(f"\n[RESUMEN]: Se procesaron {processed_count} serial(es) en la factura.")
        return logs

    def action_download_template(self):
        """Genera un archivo Excel de ejemplo con los productos del documento activo."""
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("La librería 'openpyxl' no está disponible para generar plantillas Excel."))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Plantilla_Seriales"

        # Encabezados
        ws.append(["Código Producto / Referencia", "Número de Serie / Lote"])

        # Prellenar con los productos del documento activo si existen
        products = []
        if self.import_type == 'picking' and self.picking_id:
            moves = self.picking_id.move_ids_without_package or self.picking_id.move_ids
            products = moves.mapped('product_id').filtered(lambda p: p.tracking in ('serial', 'lot'))
        elif self.import_type == 'invoice' and self.move_id:
            products = self.move_id.invoice_line_ids.mapped('product_id').filtered(lambda p: p.tracking in ('serial', 'lot'))

        if products:
            for p in products:
                ref = p.default_code or p.barcode or p.name
                ws.append([ref, "SN-00001"])
                ws.append([ref, "SN-00002"])
        else:
            ws.append(["REF-PRODUCTO-01", "SN-10001"])
            ws.append(["REF-PRODUCTO-01", "SN-10002"])

        out_io = io.BytesIO()
        wb.save(out_io)
        out_io.seek(0)

        file_b64 = base64.b64encode(out_io.read())
        self.write({
            'template_file': file_b64,
            'template_name': 'plantilla_seriales_ventas.xlsx'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=import.serials.sales.wizard&id={self.id}&field=template_file&filename={self.template_name}&download=true',
            'target': 'self',
        }
