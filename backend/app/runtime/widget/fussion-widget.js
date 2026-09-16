/* Fussion assistant widget (step B8, FR-110, FR-113).
 *
 * Served by `GET /api/v1/public/widget.js` and loaded on a customer's page with:
 *
 *   <script src="https://<fussion-host>/api/v1/public/widget.js"
 *           data-fussion-key="fk_..."
 *           data-fussion-name="Acme Support"
 *           data-fussion-brand-color="#4338ca"
 *           data-fussion-text-color="#ffffff"
 *           data-fussion-position="BOTTOM_RIGHT"
 *           data-fussion-welcome="Hi! How can I help?"
 *           async></script>
 *
 * The pull request Fussion opens installs exactly that tag (or a small loader that injects it), so
 * one bundle serves every customer and a widget fix ships to all of them at once.
 *
 * Three rules this file exists to honour:
 *
 *   1. Shadow DOM isolation (FR-110). The whole UI lives in a shadow root, so the customer's
 *      stylesheet cannot reach it and ours cannot reach theirs.
 *   2. It reads nothing from the host page (FR-110) — no cookies, no localStorage, no sessionStorage,
 *      no host DOM. The visitor's session id is kept in memory, which is why a reload starts a new
 *      session: that is the intended trade, not an oversight.
 *   3. It degrades visibly. If the API cannot be reached the panel says so, rather than showing a
 *      send button that silently does nothing.
 *
 * The API origin is taken from this script's own `src`, so the same file works against any
 * deployment without configuration.
 */
(function () {
  "use strict";

  var script = document.currentScript || document.querySelector("script[data-fussion-key]");
  if (!script) {
    console.error("[Fussion] could not determine the widget script element.");
    return;
  }
  var config = {
    publicKey: script.getAttribute("data-fussion-key"),
    name: script.getAttribute("data-fussion-name") || "Assistant",
    brandColor: script.getAttribute("data-fussion-brand-color") || "#4338ca",
    textColor: script.getAttribute("data-fussion-text-color") || "#ffffff",
    position: script.getAttribute("data-fussion-position") || "BOTTOM_RIGHT",
    welcome: script.getAttribute("data-fussion-welcome") || "",
  };
  if (!config.publicKey) {
    console.error("[Fussion] widget script is missing its data-fussion-key attribute.");
    return;
  }

  var API = new URL(script.src).origin + "/api/v1/public/chat/stream";
  var SIDE = config.position === "BOTTOM_LEFT" ? "left" : "right";
  var sessionId = null;
  var greeted = false;

  var STYLES = [
    ":host { all: initial; }",
    "* { box-sizing: border-box; }",
    ".launcher, .panel { position: fixed; bottom: 24px; z-index: 2147483000; }",
    ".launcher[data-side='right'], .panel[data-side='right'] { right: 24px; }",
    ".launcher[data-side='left'], .panel[data-side='left'] { left: 24px; }",
    ".launcher { display: flex; align-items: center; gap: 8px; border: 0; cursor: pointer;",
    "  border-radius: 9999px; padding: 14px 20px; font: 600 14px/1.2 system-ui, sans-serif;",
    "  background: var(--fussion-brand); color: var(--fussion-text);",
    "  box-shadow: 0 10px 25px -5px rgba(0,0,0,.35); }",
    ".panel { display: none; flex-direction: column; width: min(360px, calc(100vw - 32px));",
    "  height: min(520px, calc(100vh - 140px)); bottom: 88px; overflow: hidden;",
    "  border-radius: 16px; background: #fff; color: #111827; border: 1px solid #e5e7eb;",
    "  box-shadow: 0 20px 40px -12px rgba(0,0,0,.35);",
    "  font: 400 14px/1.5 system-ui, sans-serif; }",
    ".panel[data-open='true'] { display: flex; }",
    ".header { padding: 14px 16px; background: var(--fussion-brand); color: var(--fussion-text);",
    "  font-weight: 600; }",
    ".log { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex;",
    "  flex-direction: column; gap: 10px; }",
    ".msg { max-width: 85%; padding: 9px 12px; border-radius: 12px; white-space: pre-wrap;",
    "  overflow-wrap: anywhere; }",
    ".msg[data-role='visitor'] { align-self: flex-end; background: var(--fussion-brand);",
    "  color: var(--fussion-text); }",
    ".msg[data-role='assistant'] { align-self: flex-start; background: #f3f4f6; }",
    ".msg[data-role='error'] { align-self: stretch; background: #fef2f2; color: #991b1b;",
    "  border: 1px solid #fecaca; }",
    ".citations { margin-top: 6px; font-size: 12px; color: #6b7280; }",
    ".form { display: flex; gap: 8px; padding: 12px; border-top: 1px solid #e5e7eb; }",
    ".form input { flex: 1; min-width: 0; padding: 10px 12px; border-radius: 10px;",
    "  border: 1px solid #d1d5db; font: inherit; color: inherit; }",
    ".form button { border: 0; border-radius: 10px; padding: 0 16px; cursor: pointer;",
    "  background: var(--fussion-brand); color: var(--fussion-text);",
    "  font: 600 14px/1 system-ui, sans-serif; }",
    ".form button[disabled] { opacity: .5; cursor: default; }",
  ].join("\n");

  var MARKUP = [
    "<button class='launcher' type='button' data-side='" + SIDE + "'",
    " aria-label='Open the assistant' aria-expanded='false'>",
    "<span aria-hidden='true'>&#128172;</span><span class='label'></span></button>",
    "<section class='panel' role='dialog' aria-label='Assistant' aria-hidden='true'",
    " data-open='false' data-side='" + SIDE + "'>",
    "  <header class='header'></header>",
    "  <div class='log' role='log' aria-live='polite'></div>",
    "  <form class='form'><input type='text' placeholder='Ask a question…'",
    "   aria-label='Your message' autocomplete='off' maxlength='2000'>",
    "   <button type='submit'>Send</button></form>",
    "</section>",
  ].join("\n");

  var host = document.createElement("div");
  // Custom properties inherit into the shadow tree, so the tenant's colours are applied without
  // rewriting the stylesheet.
  host.style.setProperty("--fussion-brand", config.brandColor);
  host.style.setProperty("--fussion-text", config.textColor);
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML = "<style>" + STYLES + "</style>" + MARKUP;

  var launcher = root.querySelector(".launcher");
  var panel = root.querySelector(".panel");
  var log = root.querySelector(".log");
  var form = root.querySelector(".form");
  var input = form.querySelector("input");
  var send = form.querySelector("button");

  launcher.querySelector(".label").textContent = config.name;
  root.querySelector(".header").textContent = config.name;

  var open = false;
  launcher.addEventListener("click", function () {
    open = !open;
    panel.setAttribute("data-open", String(open));
    panel.setAttribute("aria-hidden", String(!open));
    launcher.setAttribute("aria-expanded", String(open));
    if (open && !greeted && config.welcome) {
      greeted = true;
      bubble("assistant", config.welcome);
    }
    if (open) input.focus();
  });

  function bubble(role, text) {
    var el = document.createElement("div");
    el.className = "msg";
    el.setAttribute("data-role", role);
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function renderCitations(el, citations) {
    if (!citations || !citations.length) return;
    var note = document.createElement("div");
    note.className = "citations";
    note.textContent =
      "Sources: " +
      citations
        .map(function (citation) {
          return citation.filename;
        })
        .join(", ");
    el.appendChild(note);
  }

  /* Server-sent events: frames are separated by a blank line, and a frame starting with ':' is a
   * keepalive comment the client must ignore. */
  function readFrame(frame, onEvent) {
    if (!frame || frame.charAt(0) === ":") return;
    var name = "message";
    var data = "";
    frame.split("\n").forEach(function (line) {
      if (line.indexOf("event: ") === 0) name = line.slice(7);
      else if (line.indexOf("data: ") === 0) data = line.slice(6);
    });
    if (data) onEvent(name, JSON.parse(data));
  }

  async function sendMessage(text) {
    bubble("visitor", text);
    var reply = bubble("assistant", "");
    var body = { public_key: config.publicKey, message: text };
    if (sessionId) body.session_id = sessionId;

    var response;
    try {
      response = await fetch(API, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (error) {
      reply.setAttribute("data-role", "error");
      reply.textContent =
        "Could not reach the assistant. If this site uses a Content-Security-Policy, allow " +
        new URL(script.src).origin +
        " in connect-src.";
      return;
    }

    if (!response.ok) {
      reply.setAttribute("data-role", "error");
      reply.textContent =
        response.status === 403
          ? "This site is not authorised to use the assistant."
          : "The assistant is unavailable right now. Please try again.";
      return;
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = "";
    var started = false;

    while (true) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buffer += decoder.decode(chunk.value, { stream: true });
      var boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        var frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        readFrame(frame, function (name, payload) {
          if (name === "token") {
            reply.textContent += payload.text;
            started = true;
            log.scrollTop = log.scrollHeight;
          } else if (name === "start") {
            sessionId = payload.session_id;
          } else if (name === "done") {
            renderCitations(reply, payload.citations);
          }
        });
      }
    }

    if (!started && !reply.textContent) {
      reply.setAttribute("data-role", "error");
      reply.textContent = "The assistant did not return an answer. Please try again.";
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";
    send.disabled = true;
    sendMessage(text).finally(function () {
      send.disabled = false;
      input.focus();
    });
  });
})();
