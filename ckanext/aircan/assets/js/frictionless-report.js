/**
 * CKAN JS Module: Validation Report
 *
 * Renders a Frictionless Data validation report with grouped errors,
 * full messages, and data tables highlighting affected cells.
 *
 * Usage in a Jinja2 template:
 *
 *   <div data-module="validation-report"
 *        data-module-report='{{ report_json }}'>
 *   </div>
 *
 * Make sure to register the JS and CSS as CKAN assets (webassets).
 */
ckan.module("validation-report", function ($) {
  "use strict";

  return {
    options: {
      report: null,
    },

    initialize: function () {
      var report = this.options.report;

      if (typeof report === "string") {
        try {
          report = JSON.parse(report);
        } catch (e) {
          console.error("validation-report: invalid JSON", e);
          this.el.html(
            '<div class="alert alert-warning">Unable to parse validation report.</div>'
          );
          return;
        }
      }

      if (!report || !report.tasks) {
        this.el.html(
          '<div class="alert alert-info">No validation report available.</div>'
        );
        return;
      }

      this.el.addClass("validation-report");
      this.el.html(this._renderReport(report));

      // initial state: expand first group, collapse the rest
      this.el.find(".vr-error-group").each(function (idx) {
        var $group = $(this);
        var isFirst = idx === 0;
        $group.toggleClass("vr-collapsed", !isFirst);
        $group.find(".vr-group-toggle").attr("aria-expanded", isFirst ? "true" : "false");
      });

      // collapse/expand groups when the toggle button is clicked
      this.el.on("click", ".vr-group-header .vr-group-toggle", function (e) {
        e.preventDefault();
        var $btn = $(this);
        var $grp = $btn.closest(".vr-error-group");
        var expanded = $btn.attr("aria-expanded") === "true";
        $btn.attr("aria-expanded", expanded ? "false" : "true");
        $grp.toggleClass("vr-collapsed", expanded);
      });
    },

    /* ═══════════════════════════════════════════
       Main render
       ═══════════════════════════════════════════ */
    _renderReport: function (report) {
      var html = "";
      html += this._renderStatusBanner(report);

      for (var t = 0; t < report.tasks.length; t++) {
        html += this._renderTask(report.tasks[t]);
      }

      return html;
    },

    /* ─── Status banner ─── */
    _renderStatusBanner: function (report) {
      var valid = report.valid;
      var s = report.stats;
      var cls = valid ? "alert-success" : "alert-danger";
      var icon = valid ? "fa-check-circle" : "fa-times-circle";
      var label = valid ? "Valid" : "Invalid";

      return (
        '<div class="alert ' + cls + ' vr-status-banner">' +
          '<i class="fa ' + icon + '"></i> ' +
          "<strong>" + label + "</strong> &mdash; " +
          s.errors + " error(s), " + s.warnings + " warning(s)" +
          '<small class="pull-right">Validated in ' + s.seconds + "s</small>" +
        "</div>"
      );
    },

    /* ─── Single task ─── */
    _renderTask: function (task) {
      var html = "";

      // Errors grouped by type
      var grouped = this._groupByType(task.errors || []);
      for (var type in grouped) {
        if (!grouped.hasOwnProperty(type)) continue;
        html += this._renderErrorGroup(grouped[type], task.labels || []);
      }

      // Warnings
      if (task.warnings && task.warnings.length) {
        html += this._renderWarnings(task.warnings);
      }

      return html;
    },

    /* ─── Group errors by type ─── */
    _groupByType: function (errors) {
      var groups = {};
      for (var i = 0; i < errors.length; i++) {
        var key = errors[i].type || "unknown-error";
        if (!groups[key]) groups[key] = [];
        groups[key].push(errors[i]);
      }
      return groups;
    },

    /* ═══════════════════════════════════════════
       Render one error‑type group
       ═══════════════════════════════════════════ */
    _renderErrorGroup: function (errors, labels) {
      var title = errors[0].title || this._humanize(errors[0].type);
      var description = errors[0].description || "";
      var count = errors.length;

      var html =
        '<div class="vr-error-group vr-group--error">' +

        // ── Count + badge + toggle ──
        '<div class="vr-group-header">' +
          '<span class="vr-count" aria-label="' + count + ' errors">' + count + "</span> " +
          '<span class="vr-badge vr-badge--error">' + this._esc(title) + "</span>" +
          '<button class="vr-group-toggle" aria-expanded="true" title="Collapse/expand"><i class="fa fa-chevron-down"></i></button>' +
        "</div>" +

        // ── Collapsible body start ──
        '<div class="vr-group-body">' +

        // ── Description box ──
        '<div class="vr-box vr-box--top vr-border--error">' +
          '<p class="vr-description">' + this._esc(description) + "</p>" +
        "</div>" +

        // ── "Full list" heading ──
        '<div class="vr-box vr-box--heading vr-border--error">' +
          "<p><strong>The full list of error messages:</strong></p>" +
        "</div>" +

        // ── Message list ──
        '<div class="vr-box vr-box--messages vr-border--error-bottom">';

      for (var i = 0; i < errors.length; i++) {
        html += '<p class="vr-message">' + this._esc(errors[i].message) + "</p>";
      }

      html += "</div>";

      // ── Data table ──
      html += this._renderTable(errors, labels);

      html += "</div>"; // .vr-group-body

      html += "</div>"; // .vr-error-group
      return html;
    },

    /* ═══════════════════════════════════════════
       Data table for affected rows
       ═══════════════════════════════════════════ */
    _renderTable: function (errors, labels) {
      if (!errors.length || !labels.length) return "";

      // Build a map: rowNumber → { cells, errorFields }
      var rowMap = {};
      for (var i = 0; i < errors.length; i++) {
        var e = errors[i];
        var rn = e.rowNumber;
        if (!rowMap[rn]) {
          rowMap[rn] = { cells: e.cells || [], errorFields: {} };
        }
        rowMap[rn].errorFields[e.fieldNumber] = true;
      }

      var html =
        '<div class="vr-table-wrap">' +
        '<table class="table table-bordered table-condensed vr-table">' +
        "<thead><tr>" +
        '<th class="vr-row-num"></th>';

      for (var l = 0; l < labels.length; l++) {
        html += "<th>" + this._esc(labels[l]) + "</th>";
      }
      html += "</tr></thead><tbody>";

      // Sort row numbers
      var rowNums = Object.keys(rowMap).sort(function (a, b) {
        return Number(a) - Number(b);
      });

      for (var r = 0; r < rowNums.length; r++) {
        var rn = rowNums[r];
        var row = rowMap[rn];

        html += "<tr>";
        html += '<td class="vr-row-num"><strong>' + rn + "</strong></td>";

        for (var c = 0; c < labels.length; c++) {
          var fieldNum = c + 1; // fieldNumber is 1‑based
          var cellVal = row.cells[c] !== undefined ? String(row.cells[c]) : "";
          var isError = row.errorFields.hasOwnProperty(fieldNum);
          html +=
            '<td class="' + (isError ? "vr-cell--error" : "") + '">' +
            this._esc(cellVal) +
            "</td>";
        }
        html += "</tr>";
      }

      // Empty hint row (next row number)
      var nextRow = rowNums.length
        ? Number(rowNums[rowNums.length - 1]) + 1
        : "";
      html += '<tr class="vr-empty-row">';
      html += '<td class="vr-row-num">' + nextRow + "</td>";
      for (var x = 0; x < labels.length; x++) html += "<td></td>";
      html += "</tr>";

      html += "</tbody></table></div>";
      return html;
    },

    /* ═══════════════════════════════════════════
       Warnings
       ═══════════════════════════════════════════ */
    _renderWarnings: function (warnings) {
      var html =
        '<div class="vr-error-group vr-group--warning">' +
        '<div class="vr-group-header">' +
          '<span class="vr-count" aria-label="' + warnings.length + ' warnings">' + warnings.length + "</span> " +
          '<span class="vr-badge vr-badge--warning">Warning</span>' +
          '<button class="vr-group-toggle" aria-expanded="true" title="Collapse/expand"><i class="fa fa-chevron-down"></i></button>' +
        "</div>" +
        '<div class="vr-group-body">' +
        '<div class="vr-box vr-box--messages vr-border--warning">';

      for (var i = 0; i < warnings.length; i++) {
        var msg = warnings[i].message || JSON.stringify(warnings[i]);
        html += '<p class="vr-message">' + this._esc(msg) + "</p>";
      }

      html += "</div></div>";
      return html;
    },

    /* ═══════════════════════════════════════════
       Helpers
       ═══════════════════════════════════════════ */
    _humanize: function (str) {
      return (str || "")
        .replace(/[-_]/g, " ")
        .replace(/\b\w/g, function (c) {
          return c.toUpperCase();
        });
    },

    _esc: function (str) {
      var d = document.createElement("div");
      d.appendChild(document.createTextNode(str || ""));
      return d.innerHTML;
    },
  };
});