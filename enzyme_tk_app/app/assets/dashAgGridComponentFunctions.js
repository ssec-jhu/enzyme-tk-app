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
/*  Helper: full-screen lightbox — query beside the clicked result     */
/* ------------------------------------------------------------------ */

/** Mirrors results_helpers.QUERY_PREVIEW_CLASS / QUERY_SMILES_ATTR. */
var _QUERY_PREVIEW_CLASS = "jobs-params-preview";
var _QUERY_SMILES_ATTR = "data-smiles";

/**
 * Build one labelled panel of the compare lightbox.
 *
 * @param {string} label - "Query" / "Result"; "" renders the image bare.
 * @param {string} src - a data:image/svg+xml;base64,... URI.
 * @param {string} smiles - SMILES shown under the image; "" omits the line.
 * @returns {HTMLElement} a <figure> holding caption, image and SMILES.
 */
function _comparePanel(label, src, smiles) {
    var panel = document.createElement("figure");
    panel.className = "svg-compare-panel";

    if (label) {
        var caption = document.createElement("figcaption");
        caption.className = "svg-compare-label";
        caption.textContent = label;
        panel.appendChild(caption);
    }

    var img = document.createElement("img");
    img.src = src;
    img.alt = (label || "structure") + " (enlarged)";
    panel.appendChild(img);

    if (smiles) {
        var code = document.createElement("code");
        code.className = "svg-compare-smiles";
        code.textContent = smiles;
        panel.appendChild(code);
    }

    return panel;
}

/** Aspect ratio (w/h) above which panels stack instead of sitting side by side. */
var _STACK_ASPECT_RATIO = 2.5;

/**
 * Stack the compare panels when a structure is much wider than it is tall.
 *
 * Reaction canvases are 250 px per template on a 200 px-high canvas
 * (utils/smiles_rendering.reaction_to_svg_data_uri), so the narrowest real
 * reaction — one reactant, one product — is 750x200 (3.75), while molecules are
 * 500x300 (1.67); 2.5 is the geometric midpoint of that gap.  Side by side a
 * 1250x200 reaction draws 644 px wide; stacked it gets 1232 px.
 *
 * A data: URI has no naturalWidth until it decodes, so the check re-runs on
 * every load event; the up-front call only pays off for an image the browser
 * already holds.
 *
 * Ceiling: the threshold assumes the 200 px reaction height both call sites
 * pass.  Draw reactions taller and a 1-to-1 stops clearing 2.5 — re-measure a
 * rendered pair and move the constant.
 *
 * @param {HTMLElement} compare - the .svg-compare wrapper holding the panels.
 */
function _stackWideImages(compare) {
    var imgs = compare.querySelectorAll("img");

    function measure() {
        for (var i = 0; i < imgs.length; i++) {
            var img = imgs[i];
            if (img.naturalHeight && img.naturalWidth / img.naturalHeight > _STACK_ASPECT_RATIO) {
                compare.classList.add("svg-compare-stacked");
                return;
            }
        }
    }

    for (var j = 0; j < imgs.length; j++) {
        imgs[j].addEventListener("load", measure);
    }
    measure();
}

/**
 * Open the full-screen lightbox for a clicked grid image.
 *
 * The results page already renders the job's query structure above the
 * grid, so the query panel is read straight out of the DOM rather than
 * plumbed through columnDefs — a second copy of the URI would be exported
 * into the CSV and repeated ~20 KB per row.  No query image on the page
 * (tool has no SMILES param, or RDKit could not draw it) means the result
 * shows alone and unlabelled, exactly as before.
 *
 * Ceiling: querySelector takes the first match, which is exact while
 * results_helpers._SMILES_PARAM_KEYS holds one key.  Grow that set and
 * this needs to know which preview belongs to the clicked column.
 *
 * @param {string} src - the clicked cell's data URI.
 * @param {string} smiles - the clicked row's SMILES, or "" if unknown.
 */
function _openSvgOverlay(src, smiles) {
    // Backdrop
    var overlay = document.createElement("div");
    overlay.className = "svg-overlay";

    // Close button (×)
    var closeBtn = document.createElement("span");
    closeBtn.className = "svg-overlay-close";
    closeBtn.textContent = "\u00D7"; // ×
    overlay.appendChild(closeBtn);

    // Query (left) beside result (right); no query image → result alone.
    var queryImg = document.querySelector("img." + _QUERY_PREVIEW_CLASS);
    var compare = document.createElement("div");
    compare.className = "svg-compare";
    if (queryImg) {
        compare.appendChild(
            _comparePanel(
                "Query",
                queryImg.src,
                queryImg.getAttribute(_QUERY_SMILES_ATTR) || ""
            )
        );
    }
    compare.appendChild(_comparePanel(queryImg ? "Result" : "", src, smiles || ""));
    overlay.appendChild(compare);
    _stackWideImages(compare);

    // Close on backdrop click, on ×, or Escape.  Clicks inside the panels are
    // swallowed: two structures cover most of the viewport, so "click anywhere
    // closes" would shut the lightbox the moment a user reaches for the thing
    // they opened it to look at — or tries to select a SMILES to copy.
    function close() {
        document.removeEventListener("keydown", onKey);
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }
    function onKey(e) {
        if (e.key === "Escape") close();
    }
    compare.addEventListener("click", function (e) {
        e.stopPropagation();
    });
    overlay.addEventListener("click", close);
    document.addEventListener("keydown", onKey);

    document.body.appendChild(overlay);
}

/* ------------------------------------------------------------------ */
/*  SvgRenderer — thumbnail with click-to-compare                      */
/* ------------------------------------------------------------------ */
/**
 * Renders a base64-encoded SVG data URI as an <img> thumbnail.
 * Clicking the image opens a full-screen lightbox showing the job's query
 * structure beside this row's; click the backdrop, the × or press Escape
 * to close.
 *
 * Usage in columnDefs:
 *   {"field": "molecule_svg", "cellRenderer": "SvgRenderer",
 *    "cellRendererParams": {"smilesField": "molecule_smiles"}}
 *
 * The cell value should be a data URI string
 * (e.g. "data:image/svg+xml;base64,...").  The optional smilesField names
 * the row column holding this structure's SMILES, captioned under the
 * image in the lightbox; omit it and the caption is simply left off.
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
                // props.data is the whole row, so the SMILES column need not
                // be one of the grid's visible columns.
                _openSvgOverlay(
                    props.value,
                    props.smilesField ? props.data[props.smilesField] : ""
                );
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
