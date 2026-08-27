from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import logging
import pandas as pd

_logger = logging.getLogger(__name__)


class ImportDocumentosWizard(models.TransientModel):
    _name = "import.documentos.wizard"
    _description = "Wizard Importación Masiva de Documentos"

    excel_file = fields.Binary(string="Archivo Excel", required=True)
    import_type = fields.Selection([
        ('out_invoice', 'Clientes (Ventas)'),
        ('in_invoice', 'Proveedores (Compras)')
    ], string='Tipo de Importación', default='out_invoice', required=True)
    product_id = fields.Many2one(
        "product.product", string="Producto de Servicio", required=True
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
    col_total = fields.Char(string="Columna Total", required=True, default="Total")
    col_company = fields.Char(string="Columna Compañía", required=True, default="Emp")
    col_vendedor = fields.Char(string="Columna Vendedor", required=True, default="Vendedor")

    def import_file(self):
        self.ensure_one()
        try:
            file_content = base64.b64decode(self.excel_file)
            data = io.BytesIO(file_content)
            df = pd.read_excel(data)
        except Exception as e:
            raise UserError(_("Error al leer el archivo Excel: %s") % str(e))

        # Required columns validation dynamic
        required_columns = [
            self.col_doc_num,
            self.col_type,
            self.col_rif,
            self.col_name,
            self.col_date,
            self.col_date,
            self.col_total,
            self.col_company,
            self.col_vendedor,
        ]

        # Strip whitespace from excel columns for safer matching
        df.columns = df.columns.astype(str).str.strip()

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise UserError(
                _("El archivo Excel no tiene las columnas configuradas: %s")
                % ", ".join(missing_columns)
            )

        # Group by Document Number
        grouped = df.groupby(self.col_doc_num)

        success_count = 0
        error_count = 0
        success_count = 0
        skipped_count = 0
        errors = []

        # Determine Taxes to apply (Global for the wizard run)
        product = self.product_id
        use_fallback = False
        if not product.taxes_id:
            use_fallback = True
        elif all(t.amount == 0 for t in product.taxes_id):
            use_fallback = True
            
        final_tax_ids = []
        if use_fallback and self.fallback_tax_id:
            final_tax_ids = self.fallback_tax_id.ids
        else:
            final_tax_ids = product.taxes_id.ids

        for doc_number, group in grouped:
            try:
                # Use the first row for header data
                row = group.iloc[0]
                doc_type = str(row[self.col_type]).strip().upper()
                rif = str(row[self.col_rif]).strip()
                partner_name = str(row[self.col_name]).strip()
                date_invoice = row[self.col_date]
                salesperson_name = str(row[self.col_vendedor]).strip() if pd.notna(row[self.col_vendedor]) else ""

                # Salesperson Search
                user_id = False
                if salesperson_name:
                    user = self.env["res.users"].search([("name", "=ilike", salesperson_name)], limit=1)
                    if user:
                        user_id = user.id
                    else:
                        errors.append(f"Doc {doc_number}: Vendedor '{salesperson_name}' no encontrado en Odoo")

                # Logic for Journal and Move Type
                journal_id = False
                base_type = "out" if self.import_type == 'out_invoice' else "in"

                if doc_type in ("FAC", "FC"):
                    journal_id = self.journal_fiscal_id.id
                    move_type = f"{base_type}_invoice"
                elif doc_type in ("CRE", "NC"):
                    journal_id = self.journal_fiscal_id.id
                    move_type = f"{base_type}_refund"
                elif doc_type == "ENT":
                    journal_id = self.journal_entrega_id.id
                    move_type = f"{base_type}_invoice"
                elif doc_type == "END":
                    journal_id = self.journal_entrega_id.id
                    move_type = f"{base_type}_refund"
                else:
                    _logger.warning(
                        "Tipo de documento desconocido '%s' para documento %s. Saltando.",
                        doc_type,
                        doc_number,
                    )
                    error_count += 1
                    errors.append(f"Doc {doc_number}: Tipo '{doc_type}' desconocido")
                    continue

                # Company Validation
                company_raw = row.get(self.col_company)
                company_name = str(company_raw).strip() if pd.notna(company_raw) else ""
                current_company = self.env.company.name

                if company_name and company_name.lower() != current_company.lower():
                    if (
                        current_company.lower() not in company_name.lower()
                        and company_name.lower() not in current_company.lower()
                    ):
                        skipped_count += 1
                        continue

                # Partner Logic
                partner = self.env["res.partner"].search([("vat", "=", rif)], limit=1)
                if not partner:
                    partner = self.env["res.partner"].search(
                        [("name", "=", partner_name)], limit=1
                    )

                if not partner:
                    # Create partner if not found
                    rank_field = "customer_rank" if self.import_type == 'out_invoice' else "supplier_rank"
                    partner = self.env["res.partner"].create(
                        {
                            "name": partner_name,
                            "vat": rif,
                            rank_field: 1,
                        }
                    )

                # Calculate Total Amount
                total_amount = group[self.col_total].sum()

                # Handle negative total for Refund (Credit Note)
                # Odoo expects positive amounts in lines, creating a Credit Note (refund) flips the sign logically.
                if move_type in ("out_refund", "in_refund"):
                    total_amount = abs(total_amount)

                # Create Invoice
                invoice_vals = {
                    "move_type": move_type,
                    "journal_id": journal_id,
                    "partner_id": partner.id,
                    "invoice_date": date_invoice,
                    "invoice_user_id": user_id,
                    "ref": f"Importación Masiva - {doc_type} {doc_number}",
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": self.product_id.id,
                                "name": f"Importación Masiva - {doc_type} {doc_number}",
                                "price_unit": total_amount,
                                "quantity": 1.0,
                                "tax_ids": [(6, 0, final_tax_ids)],
                            },
                        )
                    ],
                }
                self.env["account.move"].create(invoice_vals)
                success_count += 1

            except Exception as e:
                msg = f"Error procesando documento {doc_number}: {str(e)}"
                _logger.error(msg)
                error_count += 1
                errors.append(msg)

        # Show result message
        message = f"Proceso completado.\nImportados: {success_count}\nOmitidos (Otra Cía): {skipped_count}\nErrores: {error_count}"
        if errors:
            message += "\n\nDetalle de Errores (primeros 10):\n" + "\n".join(
                errors[:10]
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Importación Finalizada"),
                "message": message,
                "sticky": True,
                "type": "warning" if error_count > 0 else "success",
            },
        }
