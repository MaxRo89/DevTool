/* Se inyecta en cada página que pasa por /proxy (app.py reemplaza
   __FRAME__ y __DEVICE__). Hace que todo lo que la página pida a su sitio
   —enlaces, formularios (GET y POST), fetch y XMLHttpRequest— vuelva a
   pasar por el proxy. Así:
     - se envía con el User-Agent del dispositivo,
     - las cookies (por ejemplo la sesión al iniciar sesión) quedan en el
       frasco de esta pantalla,
     - las respuestas no traen X-Frame-Options, que haría que Chrome diga
       "rechazó la conexión" dentro del iframe. */
(function () {
  "use strict";
  var F = __FRAME__, D = __DEVICE__;
  var ORIGIN = location.origin;

  function abs(u) {
    try { return new URL(u, document.baseURI).href; } catch (_e) { return null; }
  }
  function proxiable(u) {
    return !!u && /^https?:/i.test(u) && new URL(u).origin !== ORIGIN;
  }
  function via(u) {
    return ORIGIN + "/proxy?frame=" + encodeURIComponent(F) +
      "&device=" + encodeURIComponent(D) + "&url=" + encodeURIComponent(u);
  }

  // ---------- Enlaces ----------
  // En fase de burbuja sobre window: si la página maneja el clic ella misma
  // (por ejemplo un router de una SPA), ya llamó a preventDefault y no tocamos nada.
  window.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.hasAttribute("download")) return;
    if (a.target && a.target !== "_self") return;
    var href = a.href;
    if (!proxiable(href)) return;
    var here = document.baseURI.split("#")[0];
    if (href.split("#")[0] === here && href.indexOf("#") > -1) return; // ancla en la misma página
    e.preventDefault();
    location.href = via(href);
  });

  // ---------- Formularios ----------
  function formInfo(form, submitter) {
    var attr = function (name, fallback) {
      return (submitter && submitter.getAttribute("form" + name)) || form.getAttribute(name) || fallback;
    };
    var target = attr("target", "");
    if (target && target !== "_self") return null;
    var action = abs(attr("action", document.baseURI));
    if (!proxiable(action)) return null;
    return { method: attr("method", "get").toLowerCase(), action: action };
  }

  function sendForm(form, submitter, info) {
    if (info.method === "get") {
      // El navegador borraría la query del action al enviar por GET, así que
      // armamos la URL a mano.
      var data;
      try { data = new FormData(form, submitter || undefined); } catch (_e) { data = new FormData(form); }
      var u = new URL(info.action);
      u.search = new URLSearchParams(data).toString();
      location.href = via(u.href);
      return true;
    }
    // POST (u otro): el navegador lo envía tal cual (archivos, enctype…),
    // pero a nuestro proxy en lugar de directo al sitio.
    if (submitter && submitter.hasAttribute("formaction")) submitter.setAttribute("formaction", via(info.action));
    form.setAttribute("action", via(info.action));
    return false;
  }

  window.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return;          // la página lo envía con JavaScript
    var info = formInfo(e.target, e.submitter);
    if (info && sendForm(e.target, e.submitter, info)) e.preventDefault();
  });

  // form.submit() no dispara el evento "submit".
  var nativeSubmit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () {
    var info = formInfo(this, null);
    if (info && sendForm(this, null, info)) return;
    return nativeSubmit.call(this);
  };

  // ---------- fetch y XMLHttpRequest ----------
  var nativeFetch = window.fetch;
  if (nativeFetch) {
    window.fetch = function (input, init) {
      try {
        var isReq = typeof Request !== "undefined" && input instanceof Request;
        var target = abs(isReq ? input.url : String(input));
        if (proxiable(target)) input = isReq ? new Request(via(target), input) : via(target);
      } catch (_e) {}
      return nativeFetch.call(this, input, init);
    };
  }

  var nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    var target = abs(url);
    if (proxiable(target)) arguments[1] = via(target);
    return nativeOpen.apply(this, arguments);
  };

  // ---------- Aviso al visor ----------
  // Para que Refrescar recargue la página donde está esta pantalla.
  try { parent.postMessage({ type: "rv:navigated", frame: F, url: document.baseURI }, ORIGIN); } catch (_e) {}
})();
