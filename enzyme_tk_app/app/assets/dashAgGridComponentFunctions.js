/**
 * Custom cell renderers for dash-ag-grid (v31+).
 *
 * Dash AG Grid discovers components exported on
 * ``window.dashAgGridComponentFunctions``.  Each property is a
 * function(props) that receives the cell params and returns a React
 * element via ``React.createElement``.
 *
 * See: https://dash.plotly.com/dash-ag-grid/cell-renderer-components
 */

/* global React */
var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
    window.dashAgGridComponentFunctions || {});

/* ------------------------------------------------------------------ */
/*  Helper: full-screen image overlay (click or Escape to close)       */
/* ------------------------------------------------------------------ */
function _openSvgOverlay(src) {
    // Backdrop
    var overlay = document.createElement("div");
    overlay.className = "svg-overlay";

    // Close button (×)
    var closeBtn = document.createElement("span");
    closeBtn.className = "svg-overlay-close";
    closeBtn.textContent = "\u00D7"; // ×
    overlay.appendChild(closeBtn);

    // Large image
    var img = document.createElement("img");
    img.src = src;
    img.alt = "molecule (enlarged)";
    overlay.appendChild(img);

    // Close on click anywhere or Escape key
    function close() {
        document.removeEventListener("keydown", onKey);
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    function onKey(e) {
        if (e.key === "Escape") close();
    }
    overlay.addEventListener("click", close);
    document.addEventListener("keydown", onKey);

    document.body.appendChild(overlay);
}

/* ------------------------------------------------------------------ */
/*  SvgRenderer — thumbnail with click-to-enlarge                      */
/* ------------------------------------------------------------------ */
/**
 * Renders a base64-encoded SVG data URI as an <img> thumbnail.
 * Clicking the image opens a full-screen overlay with the larger
 * version; click anywhere or press Escape to close.
 *
 * Usage in columnDefs:
 *   {"field": "molecule_svg", "cellRenderer": "SvgRenderer"}
 *
 * The cell value should be a data URI string
 * (e.g. "data:image/svg+xml;base64,...").
 */
dagcomponentfuncs.SvgRenderer = function (props) {
    if (!props.value) {
        return null;
    }
    return React.createElement(
        "div",
        {
            style: {
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                cursor: "pointer",
            },
            title: "Click to enlarge",
        },
        React.createElement("img", {
            src: props.value,
            style: {
                maxWidth: "100%",
                maxHeight: "150px",
                objectFit: "contain",
            },
            alt: "molecule",
            onClick: function () {
                _openSvgOverlay(props.value);
            },
        })
    );
};

/* ------------------------------------------------------------------ */
/*  StatusBadgeRenderer — colored status badge with FontAwesome icon   */
/* ------------------------------------------------------------------ */
/**
 * Renders a job status value as a colored badge with a FontAwesome icon,
 * matching the badge styling used on the My Tasks HTML table.
 *
 * Usage in columnDefs:
 *   {"field": "status", "cellRenderer": "StatusBadgeRenderer"}
 *
 * The cell value should be the status string (e.g. "PENDING", "SUCCESS").
 * Applies CSS classes: badge-status badge-{STATUS}
 */
dagcomponentfuncs.StatusBadgeRenderer = function (props) {
    if (!props.value) {
        return null;
    }

    // Map status values to FontAwesome icon classes (mirrors icons.py).
    var iconMap = {
        PENDING: "fa-solid fa-clock",
        STARTED: "fa-solid fa-gear",
        SUCCESS: "fa-solid fa-circle-check",
        FAILURE: "fa-solid fa-circle-xmark",
        REVOKED: "fa-solid fa-ban",
        TIMEOUT: "fa-solid fa-hourglass-end",
    };

    var status = props.value;
    var iconClass = iconMap[status] || "fa-solid fa-question";

    return React.createElement(
        "span",
        { className: "badge-status badge-" + status },
        React.createElement("i", {
            className: iconClass + " badge-status-icon",
        }),
        " " + status
    );
};
