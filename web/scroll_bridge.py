"""Small same-origin bridge that steers only the chat scroll container.

Streamlit strips ``<script>`` from markdown, so the only supported way to run a
few lines of DOM code is a component iframe. Streamlit renders those iframes
with ``allow-same-origin``, so the script can reach ``window.parent.document``.

Rules the script implements (all inside the chat container, never the page):

* a new explicit request (token change) scrolls to bottom or to the run anchor;
* otherwise a reader who was at the bottom follows new content;
* a reader who scrolled up keeps their position and gets a "new message" pill;
* the last position lives in ``sessionStorage`` so a Streamlit rerun does not
  reset the reader to the top or the bottom;
* the conversation height is measured so the composer stays on screen.

Known limits, also documented in the report: the bridge runs after the DOM is
committed and retries briefly, so a very fast run may finish before the scroll
is visible; ``sessionStorage`` is per browser tab, so a new tab starts at the
bottom.
"""
import json

import streamlit as st
import streamlit.components.v1 as components

ACTIONS = ("none", "top", "bottom", "run")
CHAT_KEY = "user_chat_scroll"
NONCE_KEY = "scroll_nonce"
ACTION_KEY = "scroll_action"
ANCHOR_KEY = "scroll_anchor"


def request(action, anchor="", *, scope=None):
    """Queue one explicit scroll request; only this bumps the bridge token."""
    if action not in ACTIONS:
        raise ValueError("unknown scroll action")
    st.session_state[NONCE_KEY] = int(st.session_state.get(NONCE_KEY, 0)) + 1
    st.session_state[ACTION_KEY] = action
    st.session_state[ANCHOR_KEY] = anchor if action == "run" else ""
    st.session_state['scroll_scope'] = scope if scope is not None else st.session_state.get('user_compose_session','')


def current_request():
    """The request the bridge should execute on this render."""
    return {
        "nonce": int(st.session_state.get(NONCE_KEY, 0)),
        "action": st.session_state.get(ACTION_KEY, "none"),
        "anchor": st.session_state.get(ANCHOR_KEY, ""),
        "scope": st.session_state.get('scroll_scope',''),
    }


def scroll_token(nonce, action, anchor=""):
    """Token changes only when an explicit request was made."""
    action = action if action in ACTIONS else "none"
    return f"{int(nonce)}:{action}:{anchor}"


BRIDGE_JS = r"""
(function () {
  var CFG = __CFG__;
  var doc = null;
  try { doc = window.parent.document; } catch (err) { return; }
  if (!doc) return;
  var SELECTOR = '.st-key-' + CFG.chatKey;

  function pickScroller(root) {
    var nodes = [root].concat([].slice.call(root.querySelectorAll('*')));
    var fallback = null;
    for (var i = 0; i < nodes.length; i += 1) {
      var style = window.parent.getComputedStyle(nodes[i]);
      var over = style.overflowY;
      if (over !== 'auto' && over !== 'scroll') continue;
      if (!fallback) fallback = nodes[i];
      if (nodes[i].scrollHeight > nodes[i].clientHeight + 4) return nodes[i];
    }
    return fallback || root;
  }

  function fit() {
    // Grid/Flex owns all container sizing. Only expose the dynamic visual
    // viewport (including the mobile keyboard) as a CSS input.
    try {
      var viewport = window.parent.visualViewport;
      if (viewport && viewport.height < window.parent.innerHeight - 1) {
        doc.documentElement.style.setProperty('--ta-viewport-height', viewport.height + 'px');
      } else { doc.documentElement.style.removeProperty('--ta-viewport-height'); }
      var root = doc.querySelector(SELECTOR);
      return root ? pickScroller(root) : null;
    } catch (err) { return null; }
  }

  function scheduleFit() {
    // Streamlit has not finished laying out the header/run summary when the
    // bridge iframe first mounts. Re-fit after the next frame and after the
    // short transition so the composer never starts below the mobile viewport.
    try { window.parent.requestAnimationFrame(function () { fit(); }); } catch (err) {}
    window.parent.setTimeout(function () { fit(); }, 180);
    window.parent.setTimeout(function () { fit(); }, 600);
    window.parent.setTimeout(function () { fit(); }, 1500);
    window.parent.setTimeout(function () { fit(); }, 2600);
  }

  // A callback created in an unmounted component iframe can stop receiving
  // events. Rebind from this active iframe, removing the previous listener.
  window.parent.__taFit = fit;
  var resize = function () { fit(); };
  if (window.parent.__taResizeHandler) {
    window.parent.removeEventListener('resize', window.parent.__taResizeHandler);
    if (window.parent.visualViewport) {
      window.parent.visualViewport.removeEventListener('resize', window.parent.__taResizeHandler);
    }
  }
  window.parent.__taResizeHandler = resize;
  window.parent.addEventListener('resize', resize, { passive: true });
  if (window.parent.visualViewport) {
    window.parent.visualViewport.addEventListener('resize', resize, { passive: true });
  }

  function run(root) {
    var box = fit() || pickScroller(root);
    var store = window.parent.sessionStorage;
    var KEY = 'ta-scroll:' + CFG.chatKey + ':' + CFG.scope;
    var saved = {};
    try { saved = JSON.parse(store.getItem(KEY) || '{}') || {}; } catch (err) { saved = {}; }
    var lastToken = null;
    try { lastToken = store.getItem(KEY + ':token'); } catch (err) { lastToken = null; }

    function setState(value) {
      try { store.setItem(KEY, JSON.stringify(value)); } catch (err) {}
    }
    function nearBottom(el) {
      return (el.scrollHeight - el.scrollTop - el.clientHeight) < 48;
    }
    function toBottom() { box.scrollTop = box.scrollHeight; }
    function markBottom() {
      setState({ top: box.scrollTop, atBottom: true, height: box.scrollHeight, turns: CFG.turns });
    }

    var badge = null;
    function hideBadge() {
      if (badge && badge.parentNode) { badge.parentNode.removeChild(badge); }
      badge = null;
    }
    function showBadge() {
      if (badge) return;
      badge = doc.createElement('button');
      badge.type = 'button';
      badge.className = 'ta-newmsg';
      badge.textContent = '有新消息 · 回到最新';
      badge.addEventListener('click', function () { toBottom(); hideBadge(); markBottom(); });
      box.appendChild(badge);
    }

    if (!box.dataset.taScrollBound) {
      box.dataset.taScrollBound = '1';
    }
    // Delegated on the parent document: React replaces the container element on
    // rerun, so a listener bound to one node stops reporting the reader position.
    window.parent.__taScroll = function (target) {
      if (!target || target.clientHeight < 40) return;
      if (target.scrollHeight <= target.clientHeight + 4) return;
      setState({ top: target.scrollTop, atBottom: nearBottom(target),
                 height: target.scrollHeight, turns: CFG.turns });
      if (nearBottom(target)) { hideBadge(); }
    };
    if (doc.__taScrollDelegated) { doc.removeEventListener('scroll', doc.__taScrollDelegated, true); }
    doc.__taScrollDelegated = function (event) {
      var target = event.target;
      if (target && target.classList && target.classList.contains('st-key-' + CFG.chatKey)) {
        if (window.parent.__taScroll) { window.parent.__taScroll(target); }
      }
    };
    doc.addEventListener('scroll', doc.__taScrollDelegated, true);
    // Reruns replace the element while this iframe is torn down; a light poll
    // keeps the last reader position accurate between mounts. It dies with the
    // iframe, so at most one poller exists at a time.
    var lastTop = null;
    window.setInterval(function () {
      var target = doc.querySelector(SELECTOR);
      if (!target || target.clientHeight < 40) return;
      if (lastTop !== null && Math.abs(target.scrollTop - lastTop) < 1) return;
      lastTop = target.scrollTop;
      if (window.parent.__taScroll) { window.parent.__taScroll(target); }
    }, 400);

    var explicit = CFG.token !== lastToken;
    if (explicit) { try { store.setItem(KEY + ':token', CFG.token); } catch (err) {} }

    if (explicit && CFG.action === 'top') {
      box.scrollTop = 0;
      setState({ top: 0, atBottom: false, height: box.scrollHeight, turns: CFG.turns });
      return;
    }
    if (explicit && CFG.action === 'bottom') {
      toBottom(); hideBadge(); markBottom(); return;
    }
    if (explicit && CFG.action === 'run' && CFG.anchor) {
      var anchor = doc.querySelector('.st-key-' + CFG.anchor);
      if (anchor) {
        var delta = anchor.getBoundingClientRect().top - box.getBoundingClientRect().top;
        box.scrollTop = box.scrollTop + delta - 8;
        anchor.classList.add('ta-flash');
        window.parent.setTimeout(function () { anchor.classList.remove('ta-flash'); }, 1600);
        setState({ top: box.scrollTop, atBottom: nearBottom(box), height: box.scrollHeight });
        return;
      }
      toBottom(); markBottom(); return;
    }

    if (CFG.turns === 0 && saved.top === undefined) {
      box.scrollTop = 0;
      setState({ top: 0, atBottom: false, height: box.scrollHeight, turns: 0 });
    } else if (saved.atBottom || saved.top === undefined) {
      toBottom(); hideBadge(); markBottom();
    } else {
      box.scrollTop = saved.top;
      // New turns while the reader is up the history: never yank, just offer a jump.
      var grew = (CFG.turns || 0) > (saved.turns || 0);
      if (grew || box.scrollHeight > (saved.height || 0) + 8) { showBadge(); }
    }
  }

  var tries = 0;
  function boot() {
    var root = doc.querySelector(SELECTOR);
    var composer = doc.querySelector('.st-key-user_compose');
    if (!root || !composer) {
      tries += 1;
      if (tries < 50) { window.setTimeout(boot, 80); }
      return;
    }
    run(root);
    // Follow streamed DOM changes only while the reader was already following.
    if (window.parent.__taScrollObserver) window.parent.__taScrollObserver.disconnect();
    var observer = new MutationObserver(function () {
      var box = pickScroller(root), saved = {};
      try { saved = JSON.parse(window.parent.sessionStorage.getItem('ta-scroll:' + CFG.chatKey + ':' + CFG.scope) || '{}'); } catch (err) {}
      if (saved.atBottom) box.scrollTop = box.scrollHeight;
    });
    observer.observe(root, { childList: true, subtree: true, characterData: true });
    window.parent.__taScrollObserver = observer;
    scheduleFit();
  }
  boot();
})();
"""


def bridge_html(chat_key, token, action, anchor, nonce, max_height=None, turns=0, scope=""):
    config = json.dumps({"chatKey": chat_key, "token": token, "action": action,
                         "anchor": anchor, "nonce": nonce, "maxHeight": max_height,
                         "turns": int(turns), "scope": str(scope)})
    script = BRIDGE_JS.replace("__CFG__", config)
    return ("<!doctype html><html><head><meta charset='utf-8'></head><body>"
            "<script>" + script + "</script></body></html>")


def mount(chat_key=CHAT_KEY, height=0, max_height=None, turns=0, scope=""):
    """Render the bridge; safe to call on every rerun."""
    pending = current_request()
    if pending['scope'] and pending['scope'] != scope:
        pending = dict(nonce=0,action='none',anchor='')
    token = scroll_token(pending["nonce"], pending["action"], pending["anchor"])
    components.html(
        bridge_html(chat_key, token, pending["action"], pending["anchor"], pending["nonce"],
                    max_height, turns, scope),
        height=height, scrolling=False)
