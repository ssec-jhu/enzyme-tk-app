/**
 * Mounts the ALTCHA captcha widget into tool modals and publishes its solved
 * payload where the submit callbacks can read it.
 *
 * Why JavaScript at all: ``<altcha-widget>`` is a custom element, and Dash cannot
 * emit an arbitrary tag.  ``dash/html`` wraps 125 fixed HTML5 tags, the
 * dash-renderer resolves every component through ``window[namespace][type]`` and
 * throws otherwise, and ``html.Div`` rejects any keyword that is not a prop or a
 * ``data-``/``aria-`` wildcard.  So ``create_modal_footer`` renders an empty
 * holder div and this file fills it.
 *
 * Why a MutationObserver rather than a clientside callback on the modal's
 * ``is_open``: dbc.Modal renders its dialog through a mountOnEnter/unmountOnExit
 * transition into a ReactDOM portal on document.body.  Nothing inside a modal
 * exists in the DOM until it is first opened, and it is destroyed again on close.
 * A clientside callback fires from the callback queue and would race React's
 * commit of that portal; the observer fires *because* of the commit, so there is
 * nothing to race.  One observer also covers all six modals.
 *
 * Load order: 11-altcha.js registers the element before this file runs — Dash
 * sorts assets byte-wise per directory and emits every one as a plain
 * ``<script src>`` before the renderer boots.
 */

/* global MutationObserver */

/** Mirrors modal_helpers.CAPTCHA_HOLDER_CLASS. */
var _CAPTCHA_HOLDER_CLASS = "etk-captcha";
/** Mirrors captcha.CHALLENGE_PATH. */
var _CHALLENGE_PATH = "/altcha-challenge";
/** Mirrors the id built by modal_helpers.create_modal_footer. */
var _STORE_ID_PREFIX = "id-store-";
var _HOLDER_ID_PREFIX = "id-div-";

var _CAPTCHA_SELECTOR = "div." + _CAPTCHA_HOLDER_CLASS + ":empty";

/**
 * Publish a solved payload to the tool's dcc.Store.
 *
 * ``dash_clientside.set_props`` is the dash-renderer's own API — it dispatches
 * straight into the redux layout store, so this reaches a server-side ``State``
 * without a DOM node.  That is what lets the carrier be a dcc.Store, which
 * renders null: React owns a real input's ``value``, and for ``type="hidden"``
 * React's isTextInputElement whitelist means no change event ever fires at all.
 *
 * @param {string} holderId - the holder div's id, e.g. "id-div-funce-captcha".
 * @param {?string} payload - base64 ALTCHA payload, or null to clear.
 */
function _publishPayload(holderId, payload) {
    var storeId = _STORE_ID_PREFIX + holderId.slice(_HOLDER_ID_PREFIX.length);
    if (!window.dash_clientside || typeof window.dash_clientside.set_props !== "function") {
        // Nothing sane to fall back to.  Dropping the payload fails closed, which
        // is the right direction for a captcha: the server refuses the submit.
        console.error("ALTCHA: dash_clientside.set_props unavailable; captcha cannot report.");
        return;
    }
    window.dash_clientside.set_props(storeId, { data: payload || null });
}

/**
 * Create one widget inside a holder div.
 *
 * @param {HTMLElement} holder - an empty div.etk-captcha rendered by Dash.
 */
function _mountCaptcha(holder) {
    if (!window.customElements || !window.customElements.get("altcha-widget")) {
        // 11-altcha.js failed to load (blocked, 404, offline).  Say so in the modal
        // rather than leaving an unexplained gap; the server refuses the submit
        // anyway, because no payload is ever published.
        holder.textContent = "Verification could not load. Please reload the page.";
        _publishPayload(holder.id, null);
        return;
    }

    var widget = document.createElement("altcha-widget");
    // Attributes must be set before insertion — the element reads them in
    // connectedCallback.
    widget.setAttribute("challenge", _CHALLENGE_PATH);
    // Solve while the user fills the form, so nobody waits at submit time.
    widget.setAttribute("auto", "onload");
    // NOT optional: .altcha is display:none until the widget calls show(), which
    // only happens for a recognised display mode.  Omit this and the widget
    // solves correctly while remaining permanently invisible.
    widget.setAttribute("display", "standard");
    widget.setAttribute("type", "checkbox");

    // statechange fires on every transition with {payload, state}, where state is
    // one of code|error|verified|verifying|unverified|expired.  One listener
    // therefore covers solve, expiry, error and reset — listening for "verified"
    // alone would leave a stale payload behind after an expiry.
    widget.addEventListener("statechange", function (ev) {
        var detail = ev.detail || {};
        _publishPayload(holder.id, detail.state === "verified" ? detail.payload : null);
    });

    holder.appendChild(widget);
}

/**
 * Mount every not-yet-filled holder currently in the document.
 *
 * The ``:empty`` in the selector makes re-entry a no-op, so the widget's own DOM
 * churn costs one failed querySelectorAll per mutation batch.
 */
function _scanForCaptchaHolders() {
    var holders = document.querySelectorAll(_CAPTCHA_SELECTOR);
    for (var i = 0; i < holders.length; i++) {
        _mountCaptcha(holders[i]);
    }
}

function _startCaptchaObserver() {
    _scanForCaptchaHolders();
    new MutationObserver(_scanForCaptchaHolders).observe(document.body, {
        childList: true,
        subtree: true,
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _startCaptchaObserver);
} else {
    _startCaptchaObserver();
}
