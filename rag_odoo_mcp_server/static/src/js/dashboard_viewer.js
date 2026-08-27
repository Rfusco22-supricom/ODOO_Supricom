/** @odoo-module **/
/*
 * Client action `rag_mcp_dashboard.viewer`.
 * Reads a rag.mcp.dashboard record + its widgets, fetches data via the ORM,
 * and renders KPI / chart / table widgets on a 12-column CSS grid.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";

// Chart.js + luxon adapter are bundled by Odoo 17 in this asset bundle.
// loadBundle exposes window.Chart globally.
const CHART_BUNDLE = "web.chartjs_lib";

const CHART_TYPES = ["bar", "line", "pie", "donut"];

const PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5",
];

function _label(value) {
    if (value === false || value === null || value === undefined) {
        return "(empty)";
    }
    if (Array.isArray(value) && value.length === 2) {
        return value[1];
    }
    return String(value);
}

function _firstGroupKey(groupBy) {
    if (!groupBy || !groupBy.length) {
        return null;
    }
    return groupBy[0];
}

function _baseFieldName(spec) {
    // "date_order:month" -> "date_order"
    return (spec || "").split(":")[0];
}

class DashboardWidget extends Component {
    static template = "rag_odoo_mcp_server.DashboardWidget";
    static props = ["widget", "orm", "action"];

    setup() {
        this.canvasRef = useRef("canvas");
        this.state = useState({
            loading: true,
            error: null,
            kpiValue: null,
            kpiLabel: "",
            // Chart inputs are kept in a single token so useEffect deps see a
            // new reference on every successful load.
            chartData: null,
            tableRows: [],
            tableCols: [],
        });
        this._chart = null;

        onWillStart(async () => {
            if (CHART_TYPES.includes(this.props.widget.widget_type)) {
                await loadBundle(CHART_BUNDLE);
            }
        });

        onMounted(() => this.load());

        // Draw / redraw the chart whenever data lands AND the canvas is in
        // the DOM. This must NOT happen inside load() because at that point
        // the t-if/t-elif branch hosting the canvas may not be rendered yet.
        useEffect(
            (canvas, chartData) => {
                if (!canvas || !chartData) {
                    return;
                }
                this._renderChart(canvas, chartData);
            },
            () => [this.canvasRef.el, this.state.chartData],
        );

        onWillUnmount(() => {
            if (this._chart) {
                try {
                    this._chart.destroy();
                } catch (_) {
                    // ignore
                }
                this._chart = null;
            }
        });
    }

    get layoutStyle() {
        const l = this.props.widget.layout || {};
        const x = (l.x || 0) + 1; // CSS grid lines are 1-based
        const w = Math.max(1, l.w || 6);
        const h = Math.max(1, l.h || 4);
        return `grid-column: ${x} / span ${w}; grid-row: span ${h};`;
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const w = this.props.widget;
            switch (w.widget_type) {
                case "kpi":
                    await this._loadKpi(w);
                    break;
                case "bar":
                case "line":
                case "pie":
                case "donut":
                    await this._loadChart(w);
                    break;
                case "table":
                case "pivot":
                    await this._loadTable(w);
                    break;
                default:
                    this.state.error = `Unknown widget type: ${w.widget_type}`;
            }
        } catch (e) {
            this.state.error = (e && e.message) || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    async _loadKpi(w) {
        const agg = w.measure_aggregator || "count";
        if (agg === "count" || !w.measure_field) {
            const n = await this.props.orm.searchCount(w.model, w.domain || []);
            this.state.kpiValue = n;
            this.state.kpiLabel = "records";
            return;
        }
        const measureSpec = `${w.measure_field}:${agg}`;
        const groups = await this.props.orm.readGroup(
            w.model,
            w.domain || [],
            [measureSpec],
            [],
            { lazy: false }
        );
        const row = groups && groups[0];
        let value = row ? row[w.measure_field] : 0;
        if (value === false || value === null || value === undefined) {
            value = 0;
        }
        this.state.kpiValue = value;
        this.state.kpiLabel = `${agg} of ${w.measure_field}`;
    }

    async _loadChart(w) {
        const groupBy = _firstGroupKey(w.group_by);
        if (!groupBy) {
            throw new Error("Chart widget needs at least one group_by field");
        }
        const agg = w.measure_aggregator || "count";
        const measureField = w.measure_field || "id";
        const measureSpec = agg === "count" ? "__count" : `${measureField}:${agg}`;
        const fields = [measureSpec];
        const groups = await this.props.orm.readGroup(
            w.model,
            w.domain || [],
            fields,
            [groupBy],
            { lazy: false }
        );
        const labels = [];
        const values = [];
        const baseField = _baseFieldName(groupBy);
        for (const g of groups) {
            labels.push(_label(g[groupBy] !== undefined ? g[groupBy] : g[baseField]));
            const valKey = agg === "count" ? "__count" : measureField;
            let v = g[valKey];
            if (v === undefined && agg === "count") {
                v = g[`${groupBy}_count`] || 0;
            }
            values.push(v || 0);
        }
        // Store the chart inputs; useEffect will draw once the canvas is
        // mounted (it may not be mounted yet — t-if branches are gated on
        // state.loading, which is still true at this point).
        this.state.chartData = { labels, values, widget: w };
    }

    _renderChart(canvas, data) {
        const ChartCtor = window.Chart;
        if (!ChartCtor) {
            return;
        }
        const w = data.widget || this.props.widget;
        const labels = data.labels || [];
        const values = data.values || [];
        const isBar = w.widget_type === "bar";
        const isLine = w.widget_type === "line";
        const chartType = w.widget_type === "donut" ? "doughnut" : w.widget_type;
        const dsLabel =
            w.measure_aggregator === "count" || !w.measure_field
                ? "Count"
                : `${w.measure_aggregator} of ${w.measure_field}`;
        const dataset = {
            label: dsLabel,
            data: values,
        };
        if (isBar || isLine) {
            dataset.backgroundColor = PALETTE[0];
            dataset.borderColor = PALETTE[0];
            if (isLine) {
                dataset.fill = false;
                dataset.tension = 0.2;
            }
        } else {
            dataset.backgroundColor = labels.map((_, i) => PALETTE[i % PALETTE.length]);
        }
        if (this._chart) {
            try {
                this._chart.destroy();
            } catch (_) {}
            this._chart = null;
        }
        this._chart = new ChartCtor(canvas, {
            type: chartType,
            data: { labels, datasets: [dataset] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: chartType !== "bar" && chartType !== "line" },
                },
            },
        });
    }

    async _loadTable(w) {
        const fields = (w.list_fields && w.list_fields.length) ? w.list_fields : ["display_name"];
        const limit = Math.max(1, Math.min(w.record_limit || 20, 200));
        const records = await this.props.orm.searchRead(
            w.model,
            w.domain || [],
            fields,
            { limit }
        );
        this.state.tableCols = fields;
        this.state.tableRows = records.map((r) => {
            const out = { id: r.id, _cells: [] };
            for (const f of fields) {
                let v = r[f];
                if (Array.isArray(v) && v.length === 2) {
                    v = v[1];
                } else if (v === false || v === null || v === undefined) {
                    v = "";
                }
                out._cells.push(v);
            }
            return out;
        });
    }

    onRowClick(rowId) {
        this.props.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.widget.model,
            res_id: rowId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

export class DashboardViewer extends Component {
    static template = "rag_odoo_mcp_server.DashboardViewer";
    static components = { DashboardWidget };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            error: null,
            spec: null,
            reloadKey: 0,
        });

        onWillStart(async () => {
            await this.fetch();
        });
    }

    get dashboardId() {
        const params = (this.props.action && this.props.action.params) || {};
        return params.dashboard_id;
    }

    async fetch() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const id = this.dashboardId;
            if (!id) {
                throw new Error("Missing dashboard_id");
            }
            const recs = await this.orm.read(
                "rag.mcp.dashboard",
                [id],
                ["name", "description", "is_shared", "created_by_claude"]
            );
            if (!recs || !recs.length) {
                throw new Error("Dashboard not found");
            }
            const widgets = await this.orm.searchRead(
                "rag.mcp.dashboard.widget",
                [["dashboard_id", "=", id]],
                [
                    "title", "widget_type", "model_name", "domain",
                    "measure_field", "measure_aggregator", "group_by",
                    "list_fields", "record_limit",
                    "col_x", "col_y", "col_w", "col_h", "options_json",
                    "sequence",
                ],
                { order: "sequence,id" }
            );
            this.state.spec = {
                id,
                name: recs[0].name,
                description: recs[0].description || "",
                is_shared: recs[0].is_shared,
                created_by_claude: recs[0].created_by_claude,
                widgets: widgets.map((w) => this._normalizeWidget(w)),
            };
        } catch (e) {
            this.state.error = (e && e.message) || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    _normalizeWidget(w) {
        let domain = [];
        try {
            domain = JSON.parse(w.domain || "[]");
        } catch (_) {
            domain = [];
        }
        let options = {};
        try {
            options = JSON.parse(w.options_json || "{}");
        } catch (_) {
            options = {};
        }
        const split = (s) => (s ? s.split(",").map((x) => x.trim()).filter(Boolean) : []);
        return {
            id: w.id,
            title: w.title,
            widget_type: w.widget_type,
            model: w.model_name,
            domain,
            measure_field: w.measure_field || "",
            measure_aggregator: w.measure_aggregator || "count",
            group_by: split(w.group_by),
            list_fields: split(w.list_fields),
            record_limit: w.record_limit || 20,
            layout: {
                x: w.col_x || 0,
                y: w.col_y || 0,
                w: w.col_w || 6,
                h: w.col_h || 4,
            },
            options,
        };
    }

    async onRefresh() {
        this.state.reloadKey += 1;
        await this.fetch();
    }

    onEdit() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "rag.mcp.dashboard",
            res_id: this.dashboardId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("rag_mcp_dashboard.viewer", DashboardViewer);
