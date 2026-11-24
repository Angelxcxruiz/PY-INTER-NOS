"use strict";

/*
 * Utilidades de interfaz compartidas: creación segura de DOM, fechas,
 * avisos (toasts), diálogo de confirmación y campana de notificaciones.
 * Todo el texto del usuario entra por textContent, nunca por innerHTML.
 */

const Dom = {
  h(etiqueta, atributos = {}, ...hijos) {
    const el = document.createElement(etiqueta);
    Object.entries(atributos || {}).forEach(([clave, valor]) => {
      if (valor === null || valor === undefined || valor === false) return;
      if (clave === "clase") el.className = valor;
      else if (clave === "texto") el.textContent = valor;
      else if (clave.startsWith("on") && typeof valor === "function") {
        el.addEventListener(clave.slice(2), valor);
      } else el.setAttribute(clave, valor === true ? "" : valor);
    });
    hijos.flat(Infinity).forEach((hijo) => {
      if (hijo === null || hijo === undefined || hijo === false) return;
      el.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
    });
    return el;
  },

  $(selector, raiz = document) {
    return raiz.querySelector(selector);
  },

  reemplazar(contenedor, ...nodos) {
    contenedor.replaceChildren(...nodos.flat().filter(Boolean));
  },
};

const ZONA_HORARIA = "America/Bogota";

const Fechas = {
  // La API entrega UTC; MySQL puede omitir la "Z", así que se asume UTC.
  aUtc(valor) {
    if (!valor) return null;
    const texto = String(valor);
    return new Date(/(Z|[+-]\d\d:?\d\d)$/i.test(texto) ? texto : texto + "Z");
  },

  formatear(valor) {
    const fecha = this.aUtc(valor);
    if (!fecha || Number.isNaN(fecha.getTime())) return "—";
    return new Intl.DateTimeFormat("es-CO", {
      timeZone: ZONA_HORARIA,
      dateStyle: "medium",
      timeStyle: "short",
    }).format(fecha);
  },

  // Convierte el valor de <input type="datetime-local"> (hora de Bogotá) a ISO UTC.
  deBogotaAIso(valorLocal) {
    // Colombia no usa horario de verano: UTC-5 fijo.
    return new Date(valorLocal + ":00-05:00").toISOString();
  },

  // Fecha y hora de Bogotá "dentro de n minutos" en formato datetime-local.
  bogotaEn(minutos) {
    const fecha = new Date(Date.now() + minutos * 60000 - 5 * 3600000);
    return fecha.toISOString().slice(0, 16);
  },
};

const Aviso = {
  mostrar(tipo, mensaje, duracionMs = 5000) {
    const iconos = { error: "⚠", exito: "✓", info: "ℹ" };
    const contenedor = document.getElementById("avisos");
    const aviso = Dom.h(
      "div",
      { clase: `aviso aviso-${tipo}`, role: tipo === "error" ? "alert" : "status" },
      Dom.h("span", { clase: "aviso-icono", "aria-hidden": "true" }, iconos[tipo] || "ℹ"),
      Dom.h("span", { clase: "aviso-texto" }, mensaje),
      Dom.h("button", {
        type: "button",
        clase: "aviso-cerrar",
        "aria-label": "Cerrar aviso",
        texto: "×",
        onclick: () => cerrar(),
      }),
    );
    const cerrar = () => {
      aviso.classList.add("saliendo");
      setTimeout(() => aviso.remove(), 250);
    };
    contenedor.append(aviso);
    setTimeout(cerrar, duracionMs);
  },
  error(mensaje) {
    this.mostrar("error", mensaje, 7000);
  },
  exito(mensaje) {
    this.mostrar("exito", mensaje, 3500);
  },
  info(mensaje) {
    this.mostrar("info", mensaje);
  },
  deError(error) {
    this.error(Api.mensajeDe(error));
  },
};

const Modal = {
  /* Muestra un diálogo y resuelve true/false. */
  confirmar({ titulo, mensaje, textoConfirmar = "Confirmar", textoCancelar = "Cancelar", peligro = false }) {
    return new Promise((resolver) => {
      const cerrar = (valor) => {
        fondo.classList.add("saliendo");
        setTimeout(() => fondo.remove(), 200);
        document.removeEventListener("keydown", alTeclear);
        resolver(valor);
      };
      const alTeclear = (evento) => {
        if (evento.key === "Escape") cerrar(false);
      };
      const fondo = Dom.h(
        "div",
        { clase: "modal-fondo", onclick: (e) => e.target === fondo && cerrar(false) },
        Dom.h(
          "div",
          { clase: "modal tarjeta elevada", role: "dialog", "aria-modal": "true" },
          Dom.h("h3", { clase: "titulo-tarjeta" }, titulo),
          Dom.h("p", { clase: "texto-suave" }, mensaje),
          Dom.h(
            "div",
            { clase: "modal-acciones" },
            Dom.h("button", {
              type: "button",
              clase: "boton boton-fantasma",
              texto: textoCancelar,
              onclick: () => cerrar(false),
            }),
            Dom.h("button", {
              type: "button",
              clase: `boton ${peligro ? "boton-peligro" : "boton-principal"}`,
              texto: textoConfirmar,
              onclick: () => cerrar(true),
            }),
          ),
        ),
      );
      document.addEventListener("keydown", alTeclear);
      document.body.append(fondo);
      fondo.querySelector(".boton-principal, .boton-peligro").focus();
    });
  },

  /* Hoja inferior (en celular) o diálogo (en escritorio) con contenido libre. */
  hoja(titulo, contenido) {
    const cerrar = () => {
      fondo.classList.add("saliendo");
      setTimeout(() => fondo.remove(), 200);
    };
    const fondo = Dom.h(
      "div",
      { clase: "modal-fondo", onclick: (e) => e.target === fondo && cerrar() },
      Dom.h(
        "div",
        { clase: "modal hoja tarjeta elevada", role: "dialog", "aria-modal": "true" },
        Dom.h(
          "div",
          { clase: "hoja-cabecera" },
          Dom.h("h3", { clase: "titulo-tarjeta" }, titulo),
          Dom.h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-icono",
            "aria-label": "Cerrar",
            texto: "×",
            onclick: cerrar,
          }),
        ),
        contenido,
      ),
    );
    document.body.append(fondo);
    return { cerrar };
  },
};

const Campana = {
  _intervalo: null,

  montar(contenedor) {
    const insignia = Dom.h("span", { clase: "campana-insignia oculto", "aria-hidden": "true" }, "0");
    const boton = Dom.h(
      "button",
      {
        type: "button",
        clase: "boton boton-fantasma boton-icono campana",
        "aria-label": "Notificaciones",
        onclick: () => this.abrir(),
      },
      Dom.h("span", { "aria-hidden": "true" }, "🔔"),
      insignia,
    );
    contenedor.append(boton);
    this._insignia = insignia;
    this._boton = boton;
    this.actualizar();
    this._intervalo = setInterval(() => this.actualizar(), 60000);
  },

  async actualizar() {
    try {
      const { contador } = await Api.get("/notificaciones/contador");
      this._insignia.textContent = contador > 99 ? "99+" : String(contador);
      this._insignia.classList.toggle("oculto", contador === 0);
      this._boton.setAttribute(
        "aria-label",
        contador ? `Notificaciones: ${contador} sin leer` : "Notificaciones",
      );
    } catch (_) {
      // La campana es secundaria: un fallo aquí no debe molestar al usuario.
    }
  },

  async abrir() {
    const lista = Dom.h(
      "div",
      { clase: "lista-notificaciones" },
      Dom.h("p", { clase: "texto-suave" }, Dom.h("span", { clase: "icono-carga" }), " Cargando…"),
    );
    const hoja = Modal.hoja("Notificaciones", lista);
    try {
      const notificaciones = await Api.get("/notificaciones", { limite: 30 });
      if (!notificaciones.length) {
        Dom.reemplazar(lista, Dom.h("p", { clase: "texto-suave" }, "Aún no tienes notificaciones."));
        return;
      }
      const pintar = () =>
        Dom.reemplazar(
          lista,
          Dom.h("button", {
            type: "button",
            clase: "boton boton-fantasma boton-chico",
            texto: "Marcar todas como leídas",
            onclick: async () => {
              try {
                await Api.post("/notificaciones/leer-todas");
                notificaciones.forEach((n) => (n.leida_en = n.leida_en || new Date().toISOString()));
                pintar();
                this.actualizar();
              } catch (error) {
                Aviso.deError(error);
              }
            },
          }),
          notificaciones.map((n) =>
            Dom.h(
              "article",
              { clase: `notificacion ${n.leida_en ? "" : "no-leida"}` },
              Dom.h("strong", {}, n.titulo),
              Dom.h("p", {}, n.mensaje),
              Dom.h("small", { clase: "texto-suave" }, Fechas.formatear(n.creada_en)),
            ),
          ),
        );
      pintar();
    } catch (error) {
      hoja.cerrar();
      Aviso.deError(error);
    }
  },
};
