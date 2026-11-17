"""Tab-local draft and example actions for the scenario form."""
import streamlit as st


_SCRIPT = """<script>
(() => {
    // Streamlit keeps native textareas and the original form submit button.
    const bridge = Symbol.for('ticket-agent.scenario-drafts');
    if (document[bridge]) {
        document[bridge]();
        return;
    }

    const fields = new Map([['ai_scenario_objective', 4000], ['ai_scenario_constraints', 2000]]);
    const memory = new Map();
    const initialized = new WeakSet();
    const setValue = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    const selector = key => `.st-key-${key} textarea`;
    const storageKey = key => `ticket-agent.scenario-draft:${key}`;

    function remember(key, value) {
        memory.set(key, value);
        try {
            sessionStorage.setItem(storageKey(key), value);
        } catch {
            // The current page can still keep drafts if browser storage is disabled.
        }
    }

    function draft(key) {
        if (memory.has(key)) return memory.get(key);
        try {
            return sessionStorage.getItem(storageKey(key));
        } catch {
            return null;
        }
    }

    function write(textarea, value) {
        if (textarea.value === value) return;
        // Bypass the React value tracker so Streamlit receives a normal input change.
        setValue.call(textarea, value);
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function restore() {
        for (const [key, limit] of fields) {
            const textarea = document.querySelector(selector(key));
            if (!textarea || initialized.has(textarea)) continue;
            initialized.add(textarea);
            const value = draft(key);
            if (value !== null && value.length <= limit) write(textarea, value);
        }
    }

    document.addEventListener('input', event => {
        if (!(event.target instanceof HTMLTextAreaElement)) return;
        for (const [key, limit] of fields) {
            if (event.target.matches(selector(key)) && event.target.value.length <= limit) {
                remember(key, event.target.value);
                return;
            }
        }
    });

    document.addEventListener('click', event => {
        const button = event.target.closest('button[data-scenario-action]');
        const card = button?.closest('.ta-scenario-example[data-scenario-target]');
        const key = card?.dataset.scenarioTarget;
        if (!fields.has(key)) return;
        const textarea = document.querySelector(selector(key));
        if (!textarea || textarea.disabled) return;
        const value = button.dataset.scenarioAction === 'fill' ? card.dataset.scenarioExample : '';
        remember(key, value);
        write(textarea, value);
        textarea.focus();
    });

    document[bridge] = restore;
    new MutationObserver(restore).observe(document.body, { childList: true, subtree: true });
    restore();
})();
</script>"""


def mount_drafts():
    st.html(_SCRIPT, unsafe_allow_javascript=True)
