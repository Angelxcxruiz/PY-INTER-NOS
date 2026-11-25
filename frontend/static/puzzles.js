"use strict";

/*
 * Puzzles lógicos del simulador (Fase 13). Cuatro tipos, todos jugables con el dedo:
 *   ORDENAR_SECUENCIA · EMPAREJAR_CONCEPTOS · PIEZA_FALTANTE · CLASIFICAR
 *
 * Reglas:
 * - Un puzzle NO puntúa y nunca bloquea: se puede saltar, fallar o dejar acabar el tiempo.
 * - La solución no está en el navegador: la comprobación la hace el servidor (`verificar`),
 *   que solo responde si acertó. Aquí tampoco se muestra qué era lo correcto.
 * - Todo el texto entra por textContent (Dom.h), nunca por innerHTML.
 */

const Puzzles = (() => {
  const h = Dom.h.bind(Dom);

  const NOMBRES = {
    ORDENAR_SECUENCIA: "Ordena la secuencia",
    EMPAREJAR_CONCEPTOS: "Empareja conceptos",
    PIEZA_FALTANTE: "La pieza que falta",
    CLASIFICAR: "Clasifica",
  };
  const ICONOS = {
    ORDENAR_SECUENCIA: "🔢",
    EMPAREJAR_CONCEPTOS: "🔗",
    PIEZA_FALTANTE: "🧩",
    CLASIFICAR: "🗂️",
  };
  const AYUDAS = {
    ORDENAR_SECUENCIA: "Arrastra ⠿ (o usa ▲ ▼) para poner los pasos en el orden correcto.",
    EMPAREJAR_CONCEPTOS: "Toca un término y luego su definición. Toca una pareja para deshacerla.",
    PIEZA_FALTANTE: "Toca la opción que completa la serie.",
    CLASIFICAR: "Toca un elemento y luego su categoría, o arrástralo hasta ella.",
  };
  const RESULTADOS = {
    acerto: { icono: "🧠", titulo: "¡Mente ágil!", texto: "Lo resolviste. Sigamos con la historia." },
    fallo: { icono: "💪", titulo: "Sigamos, ya entrenaste", texto: "No era esa combinación, pero el puzle no cuenta para tu nota." },
    salto: { icono: "💪", titulo: "Sigamos, ya entrenaste", texto: "Saltaste el puzle: no pasa nada, no cuenta para tu nota." },
    tiempo: { icono: "⏳", titulo: "Sigamos, ya entrenaste", texto: "Se acabó el tiempo del puzle. No cuenta para tu nota." },
  };

  const boton = (texto, atributos = {}) =>
    h("button", { type: "button", texto, ...atributos });

  /* ---------- 1. ordenar la secuencia ---------- */

  function crearOrdenar(datos, avisar) {
    const lista = h("ol", { clase: "puzle-ordenar", "aria-label": "Pasos por ordenar" });

    const numerar = () =>
      [...lista.children].forEach((li, i) => {
        li.querySelector(".puzle-num").textContent = String(i + 1);
      });
    const mover = (li, direccion) => {
      const vecino = direccion < 0 ? li.previousElementSibling : li.nextElementSibling;
      if (!vecino) return;
      if (direccion < 0) lista.insertBefore(li, vecino);
      else lista.insertBefore(vecino, li);
      numerar();
      avisar();
    };

    function arrastrar(evento, li, asa) {
      evento.preventDefault();
      asa.setPointerCapture(evento.pointerId);
      li.classList.add("arrastrando");
      const alMover = (e) => {
        const bajo = document.elementFromPoint(e.clientX, e.clientY);
        const otra = bajo && bajo.closest(".puzle-ficha");
        if (!otra || otra === li || otra.parentElement !== lista) return;
        const caja = otra.getBoundingClientRect();
        const despues = e.clientY > caja.top + caja.height / 2;
        lista.insertBefore(li, despues ? otra.nextSibling : otra);
        numerar();
      };
      const fin = () => {
        li.classList.remove("arrastrando");
        asa.removeEventListener("pointermove", alMover);
        asa.removeEventListener("pointerup", fin);
        asa.removeEventListener("pointercancel", fin);
        avisar();
      };
      asa.addEventListener("pointermove", alMover);
      asa.addEventListener("pointerup", fin);
      asa.addEventListener("pointercancel", fin);
    }

    datos.elementos.forEach((texto) => {
      const asa = h("span", { clase: "puzle-asa", "aria-hidden": "true" }, "⠿");
      const li = h(
        "li",
        { clase: "puzle-ficha", "data-texto": texto },
        h("span", { clase: "puzle-num" }, ""),
        asa,
        h("span", { clase: "puzle-texto" }, texto),
        h(
          "span",
          { clase: "puzle-flechas" },
          boton("▲", { clase: "boton boton-fantasma boton-icono", "aria-label": "Subir", onclick: () => mover(li, -1) }),
          boton("▼", { clase: "boton boton-fantasma boton-icono", "aria-label": "Bajar", onclick: () => mover(li, 1) }),
        ),
      );
      asa.addEventListener("pointerdown", (e) => arrastrar(e, li, asa));
      lista.append(li);
    });
    numerar();

    return {
      elemento: lista,
      respuesta: () => ({ orden: [...lista.children].map((li) => li.dataset.texto) }),
    };
  }

  /* ---------- 2. emparejar conceptos ---------- */

  function crearEmparejar(datos, avisar) {
    const pares = new Map(); // término -> definición
    let seleccion = null; // { lado, valor }
    const botones = { terminos: new Map(), definiciones: new Map() };

    const definicionEmparejada = (definicion) => [...pares.values()].includes(definicion);
    const numeroDe = (lado, valor) => {
      const claves = [...pares.keys()];
      if (lado === "terminos") return claves.indexOf(valor) + 1;
      return claves.findIndex((termino) => pares.get(termino) === valor) + 1;
    };

    function pintar() {
      ["terminos", "definiciones"].forEach((lado) => {
        botones[lado].forEach((b, valor) => {
          const numero = numeroDe(lado, valor);
          const elegido = seleccion && seleccion.lado === lado && seleccion.valor === valor;
          b.classList.toggle("emparejado", numero > 0);
          b.classList.toggle("elegido", Boolean(elegido));
          b.querySelector(".puzle-insignia").textContent = numero > 0 ? String(numero) : "";
        });
      });
    }

    function tocar(lado, valor) {
      const emparejado = lado === "terminos" ? pares.has(valor) : definicionEmparejada(valor);
      if (emparejado) {
        const termino = lado === "terminos" ? valor : [...pares.keys()].find((t) => pares.get(t) === valor);
        pares.delete(termino);
        seleccion = null;
      } else if (seleccion && seleccion.lado !== lado) {
        const termino = lado === "terminos" ? valor : seleccion.valor;
        const definicion = lado === "terminos" ? seleccion.valor : valor;
        pares.set(termino, definicion);
        seleccion = null;
      } else if (seleccion && seleccion.lado === lado && seleccion.valor === valor) {
        seleccion = null;
      } else {
        seleccion = { lado, valor };
      }
      pintar();
      avisar();
    }

    const columna = (titulo, lado, valores) =>
      h(
        "div",
        { clase: "puzle-columna" },
        h("p", { clase: "puzle-subtitulo" }, titulo),
        valores.map((valor) => {
          const b = h(
            "button",
            { type: "button", clase: "puzle-tarjeta", onclick: () => tocar(lado, valor) },
            h("span", { clase: "puzle-insignia", "aria-hidden": "true" }, ""),
            h("span", { clase: "puzle-texto" }, valor),
          );
          botones[lado].set(valor, b);
          return b;
        }),
      );

    return {
      elemento: h(
        "div",
        { clase: "puzle-emparejar" },
        columna("Términos", "terminos", datos.terminos),
        columna("Definiciones", "definiciones", datos.definiciones),
      ),
      respuesta: () =>
        pares.size === datos.terminos.length
          ? { pares: [...pares].map(([termino, definicion]) => ({ termino, definicion })) }
          : null,
    };
  }

  /* ---------- 3. la pieza que falta ---------- */

  function crearPieza(datos, avisar) {
    let elegida = null;
    const hueco = h("span", { clase: "puzle-pieza puzle-hueco", "aria-label": "Pieza que falta" }, "?");
    const serie = h(
      "div",
      { clase: "puzle-serie", role: "list" },
      datos.serie.map((valor) => (valor === null ? hueco : h("span", { clase: "puzle-pieza", role: "listitem" }, valor))),
    );
    const botones = new Map();
    const opciones = h(
      "div",
      { clase: "puzle-opciones", role: "group", "aria-label": "Opciones" },
      datos.opciones.map((valor) => {
        const b = h(
          "button",
          {
            type: "button",
            clase: "puzle-tarjeta",
            onclick: () => {
              elegida = valor;
              hueco.textContent = valor;
              hueco.classList.add("llena");
              botones.forEach((otro, clave) => otro.classList.toggle("elegido", clave === valor));
              avisar();
            },
          },
          h("span", { clase: "puzle-texto" }, valor),
        );
        botones.set(valor, b);
        return b;
      }),
    );
    return {
      elemento: h("div", { clase: "puzle-pieza-faltante" }, serie, opciones),
      respuesta: () => (elegida === null ? null : { opcion: elegida }),
    };
  }

  /* ---------- 4. clasificar ---------- */

  function crearClasificar(datos, avisar) {
    const asignacion = new Map(datos.elementos.map((texto) => [texto, null]));
    let seleccionado = null;
    const chips = new Map();
    const zonas = new Map();
    const reserva = h("div", { clase: "puzle-reserva", "data-zona": "" });

    const zonaBajo = (x, y) => {
      const bajo = document.elementFromPoint(x, y);
      return bajo ? bajo.closest("[data-zona]") : null;
    };
    const asignar = (texto, categoria) => {
      asignacion.set(texto, categoria || null);
      seleccionado = null;
      pintar();
      avisar();
    };

    function pintar() {
      chips.forEach((chip, texto) => {
        const categoria = asignacion.get(texto);
        const destino = categoria === null ? reserva : zonas.get(categoria).querySelector(".puzle-zona-items");
        if (chip.parentElement !== destino) destino.append(chip);
        chip.classList.toggle("elegido", texto === seleccionado);
      });
      zonas.forEach((zona) => zona.classList.toggle("destino", seleccionado !== null));
      reserva.classList.toggle("destino", seleccionado !== null);
    }

    function enganchar(chip, texto) {
      let inicio = null;
      let fantasma = null;
      chip.addEventListener("pointerdown", (e) => {
        chip.setPointerCapture(e.pointerId);
        inicio = { x: e.clientX, y: e.clientY };
      });
      chip.addEventListener("pointermove", (e) => {
        if (!inicio) return;
        const movido = Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) > 8;
        if (movido && !fantasma) {
          fantasma = chip.cloneNode(true);
          fantasma.classList.add("puzle-fantasma");
          document.body.append(fantasma);
          chip.classList.add("arrastrando");
        }
        if (fantasma) {
          fantasma.style.left = `${e.clientX}px`;
          fantasma.style.top = `${e.clientY}px`;
        }
      });
      const soltar = (e) => {
        if (!inicio) return;
        if (fantasma) {
          const zona = zonaBajo(e.clientX, e.clientY);
          fantasma.remove();
          chip.classList.remove("arrastrando");
          fantasma = null;
          if (zona) asignar(texto, zona.dataset.zona);
        } else {
          seleccionado = seleccionado === texto ? null : texto;
          pintar();
        }
        inicio = null;
      };
      chip.addEventListener("pointerup", soltar);
      chip.addEventListener("pointercancel", () => {
        if (fantasma) fantasma.remove();
        fantasma = null;
        inicio = null;
        chip.classList.remove("arrastrando");
      });
      chip.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          seleccionado = seleccionado === texto ? null : texto;
          pintar();
        }
      });
    }

    datos.elementos.forEach((texto) => {
      const chip = h("button", { type: "button", clase: "puzle-chip" }, texto);
      enganchar(chip, texto);
      chips.set(texto, chip);
    });

    datos.categorias.forEach((categoria) => {
      const zona = h(
        "section",
        {
          clase: "puzle-zona",
          "data-zona": categoria,
          onclick: (e) => {
            if (e.target.closest(".puzle-chip")) return;
            if (seleccionado !== null) asignar(seleccionado, categoria);
          },
        },
        h("h3", { clase: "puzle-subtitulo" }, categoria),
        h("div", { clase: "puzle-zona-items" }),
      );
      zonas.set(categoria, zona);
    });
    reserva.addEventListener("click", (e) => {
      if (seleccionado !== null && e.target === reserva) asignar(seleccionado, null);
    });
    pintar();

    return {
      elemento: h(
        "div",
        { clase: "puzle-clasificar" },
        h("div", { clase: "puzle-zonas" }, [...zonas.values()]),
        h("p", { clase: "puzle-subtitulo" }, "Por clasificar"),
        reserva,
      ),
      respuesta: () =>
        [...asignacion.values()].every((categoria) => categoria !== null)
          ? { asignaciones: [...asignacion].map(([texto, categoria]) => ({ texto, categoria })) }
          : null,
    };
  }

  const CONSTRUCTORES = {
    ORDENAR_SECUENCIA: crearOrdenar,
    EMPAREJAR_CONCEPTOS: crearEmparejar,
    PIEZA_FALTANTE: crearPieza,
    CLASIFICAR: crearClasificar,
  };

  /*
   * Monta un puzzle dentro de `contenedor`.
   *   puzzle:     { id, tipo, enunciado, tiempo_seg, datos } (vista del estudiante, sin solución)
   *   verificar:  async (respuesta) => ({ acerto })   — lo resuelve el servidor
   *   alTerminar: (resultado) => void  con "acerto" | "fallo" | "salto" | "tiempo"
   *   alVolver:   opcional; vuelve atrás SIN dar el puzzle por resuelto (RF-10)
   */
  function montar(contenedor, puzzle, { verificar, alTerminar, alVolver, textoVolver = "← Volver" }) {
    let terminado = false;
    let intervalo = null;
    const constructor = CONSTRUCTORES[puzzle.tipo];
    if (!constructor) {
      alTerminar("salto");
      return { destruir() {} };
    }

    const cuerpo = constructor(puzzle.datos, () => actualizarComprobar());
    const comprobar = boton("COMPROBAR", { clase: "boton boton-grande boton-principal", disabled: true });
    const saltar = boton("Saltar puzle", { clase: "boton boton-fantasma", onclick: () => terminar("salto") });
    const etiquetaReloj = h("span", { id: "puzle-tiempo" }, "");
    const reloj = h(
      "div",
      { clase: "temporizador temporizador-chico", role: "timer", "aria-label": "Tiempo del puzle" },
      h("span", { "aria-hidden": "true" }, "⏱"),
      etiquetaReloj,
    );
    const finMs = performance.now() + puzzle.tiempo_seg * 1000;

    function actualizarComprobar() {
      comprobar.disabled = terminado || cuerpo.respuesta() === null;
    }

    function pintarReloj() {
      const restante = Math.max(0, Math.ceil((finMs - performance.now()) / 1000));
      etiquetaReloj.textContent = `0:${String(restante).padStart(2, "0")}`;
      reloj.classList.toggle("alerta", restante <= 10);
      reloj.classList.toggle("critico", restante <= 5);
      if (restante === 0) terminar("tiempo");
    }

    function destruir() {
      terminado = true;
      clearInterval(intervalo);
    }

    function terminar(resultado) {
      if (terminado) return;
      destruir();
      const mensaje = RESULTADOS[resultado] || RESULTADOS.salto;
      Dom.reemplazar(
        contenedor,
        h(
          "section",
          { clase: `puzle puzle-resultado puzle-${resultado} aparece`, role: "status" },
          h("p", { clase: "emoji-grande", "aria-hidden": "true" }, mensaje.icono),
          h("h2", { clase: "titulo-capitulo" }, mensaje.titulo),
          h("p", { clase: "texto-suave" }, mensaje.texto),
          boton("CONTINUAR →", {
            clase: "boton boton-grande boton-principal",
            onclick: () => alTerminar(resultado),
          }),
        ),
      );
    }

    comprobar.addEventListener("click", async () => {
      const respuesta = cuerpo.respuesta();
      if (!respuesta || terminado) return;
      comprobar.disabled = true;
      comprobar.classList.add("cargando");
      try {
        const veredicto = await verificar(respuesta);
        terminar(veredicto.acerto ? "acerto" : "fallo");
      } catch (error) {
        comprobar.classList.remove("cargando");
        Aviso.deError(error);
        actualizarComprobar();
      }
    });

    Dom.reemplazar(
      contenedor,
      h(
        "section",
        { clase: "puzle aparece" },
        h("p", { clase: "kicker" }, `${ICONOS[puzzle.tipo]} Mente ágil · ${NOMBRES[puzzle.tipo]}`),
        h("div", { clase: "puzle-cabecera" }, h("h2", { clase: "enunciado" }, puzzle.enunciado), reloj),
        h("p", { clase: "ayuda" }, AYUDAS[puzzle.tipo]),
        cuerpo.elemento,
        h("div", { clase: "navegacion puzle-navegacion" }, saltar, comprobar),
        alVolver &&
          boton(textoVolver, {
            clase: "boton boton-fantasma boton-chico puzle-volver",
            onclick: () => {
              destruir();
              alVolver();
            },
          }),
      ),
    );
    actualizarComprobar();
    pintarReloj();
    intervalo = setInterval(pintarReloj, 250);
    return { destruir };
  }

  return { montar, NOMBRES, ICONOS };
})();
