"use strict";

/*
 * Dibujo de las composiciones de escenario (editor visual de escenarios).
 * Lo usan el editor del docente y el simulador del estudiante, así que el lienzo se ve igual en
 * los dos. Las coordenadas de cada capa están en unidades del lienzo; todo se escala con la
 * variable CSS --u (píxeles por unidad), que se recalcula al cambiar el tamaño de la pantalla.
 */

const Composicion = (() => {
  const h = Dom.h.bind(Dom);
  const RUTA_ICONOS = "/app/static/iconos/";
  const ICONOS = [
    "persona",
    "grupo",
    "corazon",
    "mensaje",
    "pregunta",
    "alerta",
    "escudo",
    "reloj",
    "casa",
    "libro",
    "estrella",
    "ojo",
  ];
  const FORMA_ANCHO = 200;
  const FORMA_ALTO = 120;
  const ICONO_TAMANO = 96;
  const ALINEACION = { izquierda: "left", centro: "center", derecha: "right" };
  const SVG = "http://www.w3.org/2000/svg";

  const u = (n) => `calc(var(--u) * ${Number(n) || 0})`;
  const medida = (valor, porDefecto) => {
    if (valor !== null && valor !== undefined) return u(valor);
    return porDefecto !== undefined ? u(porDefecto) : "auto";
  };
  const porOrden = (capas) => [...capas].sort((a, b) => a.orden - b.orden);

  /* ---------- colores: la paleta sale de las variables CSS del proyecto ---------- */

  function aHex(valor) {
    // El navegador resuelve cualquier color CSS a rgb(); de ahí se arma el hexadecimal.
    const muestra = document.createElement("span");
    muestra.style.color = String(valor).trim();
    document.body.append(muestra);
    const [r, g, b] = getComputedStyle(muestra).color.match(/\d+(\.\d+)?/g).map(Number);
    muestra.remove();
    return "#" + [r, g, b].map((n) => Math.round(n).toString(16).padStart(2, "0")).join("");
  }

  function paleta() {
    const estilos = getComputedStyle(document.documentElement);
    return [
      ["Ámbar", "--ambar"],
      ["Naranja", "--naranja"],
      ["Turquesa", "--turquesa"],
      ["Cian", "--cian"],
      ["Blanco", "--blanco"],
      ["Gris azulado", "--texto-suave"],
      ["Violeta", "--tarjeta-2"],
      ["Azul noche", "--fondo"],
    ].map(([nombre, variable]) => ({ nombre, hex: aHex(estilos.getPropertyValue(variable)) }));
  }

  /* ---------- una capa ---------- */

  function aplicarTexto(el, capa) {
    el.textContent = capa.contenido;
    const s = el.style;
    s.fontSize = u(capa.tamano);
    s.color = capa.color;
    s.textAlign = ALINEACION[capa.alineacion] || "left";
    s.fontWeight = capa.negrita ? "700" : "400";
    s.fontStyle = capa.cursiva ? "italic" : "normal";
    s.width = capa.ancho !== null && capa.ancho !== undefined ? u(capa.ancho) : "max-content";
    s.height = medida(capa.alto);
  }

  function aplicarImagen(el, capa) {
    const imagen = el.firstElementChild;
    if (imagen.getAttribute("src") !== capa.url) imagen.setAttribute("src", capa.url || "");
    const ajustes = { cubrir: "cover", contener: "contain", estirar: "fill" };
    imagen.style.objectFit = ajustes[capa.ajuste] || "contain";
    el.style.width = medida(capa.ancho);
    el.style.height = medida(capa.alto);
    imagen.style.width = capa.ancho !== null && capa.ancho !== undefined ? "100%" : "auto";
    imagen.style.height = capa.alto !== null && capa.alto !== undefined ? "100%" : "auto";
    el.style.opacity = String(capa.opacidad);
  }

  function aplicarLinea(el, capa) {
    const grosor = Math.max(capa.borde_grosor || 4, 1);
    const ancho = capa.ancho !== null && capa.ancho !== undefined ? capa.ancho : FORMA_ANCHO;
    const alto = capa.alto || 0;
    const dibujo = document.createElementNS(SVG, "svg");
    dibujo.setAttribute("viewBox", `0 0 ${ancho} ${alto + grosor}`);
    dibujo.setAttribute("preserveAspectRatio", "none");
    const trazo = document.createElementNS(SVG, "line");
    trazo.setAttribute("x1", "0");
    trazo.setAttribute("y1", String(grosor / 2));
    trazo.setAttribute("x2", String(ancho));
    trazo.setAttribute("y2", String(alto + grosor / 2));
    trazo.setAttribute("stroke-width", String(grosor));
    trazo.setAttribute("stroke-linecap", "round");
    trazo.style.stroke = capa.borde_color || capa.relleno || "currentColor";
    dibujo.append(trazo);
    el.replaceChildren(dibujo);
    el.style.width = u(ancho);
    el.style.height = u(alto + grosor);
    el.style.opacity = String(capa.opacidad);
  }

  function aplicarForma(el, capa) {
    const s = el.style;
    el.classList.toggle("cmp-linea", capa.forma === "linea");
    if (capa.forma === "linea") {
      aplicarLinea(el, capa);
      return;
    }
    el.replaceChildren();
    s.width = medida(capa.ancho, FORMA_ANCHO);
    s.height = medida(capa.alto, FORMA_ALTO);
    s.backgroundColor = capa.relleno || "transparent";
    s.border = capa.borde_grosor && capa.borde_color ? `${u(capa.borde_grosor)} solid ${capa.borde_color}` : "none";
    s.opacity = String(capa.opacidad);
    if (capa.forma === "circulo") s.borderRadius = "50%";
    else s.borderRadius = capa.forma === "rectangulo_redondeado" ? u(capa.radio) : "0";
  }

  function aplicarIcono(el, capa) {
    const s = el.style;
    const ancho = capa.ancho !== null && capa.ancho !== undefined ? capa.ancho : ICONO_TAMANO;
    const alto = capa.alto !== null && capa.alto !== undefined ? capa.alto : ancho;
    const archivo = `url("${RUTA_ICONOS}${encodeURIComponent(capa.icono)}.svg")`;
    s.width = u(ancho);
    s.height = u(alto);
    s.backgroundColor = capa.color;
    s.webkitMaskImage = s.maskImage = archivo;
    s.opacity = String(capa.opacidad);
  }

  function aplicar(el, capa) {
    el.style.left = u(capa.x);
    el.style.top = u(capa.y);
    el.style.zIndex = String(capa.orden);
    if (capa.tipo === "texto") aplicarTexto(el, capa);
    else if (capa.tipo === "imagen") aplicarImagen(el, capa);
    else if (capa.tipo === "forma") aplicarForma(el, capa);
    else if (capa.tipo === "icono") aplicarIcono(el, capa);
  }

  function crearCapa(capa) {
    const el = h("div", { clase: `cmp-capa cmp-${capa.tipo}`, "data-capa-id": capa.id });
    if (capa.tipo === "imagen") el.append(h("img", { alt: "", draggable: "false" }));
    aplicar(el, capa);
    return el;
  }

  /* ---------- lienzo en página (editor y vistas previas) ---------- */

  function montar(contenedor, composicion) {
    const lienzo = h("div", { clase: "cmp-lienzo" });
    const capas = new Map();
    const ajustar = () => lienzo.style.setProperty("--u", `${lienzo.clientWidth / composicion.ancho}px`);
    const observador = new ResizeObserver(ajustar);

    function redibujar(nueva) {
      if (nueva) composicion = nueva;
      lienzo.style.aspectRatio = `${composicion.ancho} / ${composicion.alto}`;
      lienzo.style.setProperty("--razon", String(composicion.ancho / composicion.alto));
      lienzo.style.backgroundColor = composicion.fondo_color;
      capas.clear();
      lienzo.replaceChildren();
      porOrden(composicion.capas).forEach((capa) => {
        const el = crearCapa(capa);
        capas.set(capa.id, el);
        lienzo.append(el);
      });
      ajustar();
    }

    contenedor.append(lienzo);
    observador.observe(lienzo);
    redibujar();
    return {
      lienzo,
      capas,
      redibujar,
      ajustar,
      destruir() {
        observador.disconnect();
        lienzo.remove();
      },
    };
  }

  /* ---------- fondo del simulador: ocupa toda la pantalla, detrás del contenido ---------- */

  function montarFondo(composicion) {
    const lienzo = h("div", { clase: "cmp-lienzo cmp-lienzo-fondo" });
    porOrden(composicion.capas).forEach((capa) => lienzo.append(crearCapa(capa)));
    lienzo.style.backgroundColor = composicion.fondo_color;
    const el = h("div", { clase: "cmp-fondo", "aria-hidden": "true" }, lienzo);
    el.style.backgroundColor = composicion.fondo_color;

    // Con pantalla ancha el lienzo cubre todo (recorta lo que sobra); en un celular vertical
    // se ajusta al ancho y se pega arriba, con el color de fondo rellenando el resto.
    function ajustar() {
      const ancho = window.innerWidth;
      const alto = window.innerHeight;
      const cubrir = ancho / alto >= (composicion.ancho / composicion.alto) * 0.7;
      const escala = cubrir
        ? Math.max(ancho / composicion.ancho, alto / composicion.alto)
        : ancho / composicion.ancho;
      const w = composicion.ancho * escala;
      const hh = composicion.alto * escala;
      lienzo.style.width = `${w}px`;
      lienzo.style.height = `${hh}px`;
      lienzo.style.left = `${(ancho - w) / 2}px`;
      lienzo.style.top = cubrir ? `${(alto - hh) / 2}px` : "0px";
      lienzo.style.setProperty("--u", `${escala}px`);
    }

    ajustar();
    window.addEventListener("resize", ajustar);
    return {
      el,
      destruir() {
        window.removeEventListener("resize", ajustar);
        el.remove();
      },
    };
  }

  /* Claridad 0..1 del fondo (para oscurecer el panel de preguntas), o null si no se puede
     saber: con una imagen de por medio no se conoce su claridad, así que se asume lo peor. */
  function claridad(composicion) {
    if (composicion.capas.some((capa) => capa.tipo === "imagen" && capa.opacidad > 0.3)) return null;
    const hex = composicion.fondo_color;
    const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  }

  return {
    ICONOS,
    RUTA_ICONOS,
    FORMA_ANCHO,
    FORMA_ALTO,
    ICONO_TAMANO,
    aHex,
    paleta,
    aplicar,
    crearCapa,
    montar,
    montarFondo,
    claridad,
  };
})();
