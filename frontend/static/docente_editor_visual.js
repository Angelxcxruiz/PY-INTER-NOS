"use strict";

/*
 * Editor visual de escenarios: el docente arma el lienzo de un escenario con capas (imagen,
 * texto, forma, icono). Se guarda la composición (capas en JSON) para poder editarla después.
 * Habla solo con la API; el servidor valida las capas, las imágenes y que el caso sea borrador.
 */

const EditorVisual = (() => {
  const h = Dom.h.bind(Dom);
  const LIMITE_BYTES = 5 * 1024 * 1024;
  const MAX_CAPAS = 60;
  const COORDENADA_MAX = 10000;
  const FORMATOS = [
    { nombre: "Horizontal 16:9 (1280 × 720)", ancho: 1280, alto: 720 },
    { nombre: "Clásico 4:3 (1024 × 768)", ancho: 1024, alto: 768 },
    { nombre: "Cuadrado (900 × 900)", ancho: 900, alto: 900 },
    { nombre: "Vertical 9:16 (720 × 1280)", ancho: 720, alto: 1280 },
  ];
  const NOMBRES_FORMA = {
    rectangulo: "Rectángulo",
    rectangulo_redondeado: "Rectángulo redondeado",
    circulo: "Círculo",
    linea: "Línea",
  };
  const NOMBRES_ICONO = {
    persona: "Persona",
    grupo: "Grupo",
    corazon: "Corazón",
    mensaje: "Mensaje",
    pregunta: "Pregunta",
    alerta: "Alerta",
    escudo: "Escudo",
    reloj: "Reloj",
    casa: "Casa",
    libro: "Libro",
    estrella: "Estrella",
    ojo: "Ojo",
  };

  const redondear = (n) => Math.round(n * 100) / 100;
  const acotar = (n, minimo, maximo) => Math.min(maximo, Math.max(minimo, n));
  const nuevoId = () => "c" + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-3);
  const clonar = (objeto) => JSON.parse(JSON.stringify(objeto));
  const definido = (valor) => valor !== null && valor !== undefined;

  /* Vista de solo lectura (caso publicado o revisión rápida). */
  function vistaPrevia(composicion, titulo = "Composición del escenario") {
    const contenedor = h("div", { clase: "ev-previa" });
    const hoja = Modal.hoja(titulo, contenedor);
    const montado = Composicion.montar(contenedor, composicion);
    return { cerrar: () => { montado.destruir(); hoja.cerrar(); } };
  }

  function abrir({ casoId, escenario, soloLectura = false, alGuardar }) {
    const paleta = Composicion.paleta();
    const color = (nombre) => paleta.find((p) => p.nombre === nombre).hex;
    const BLANCO = color("Blanco");
    const AMBAR = color("Ámbar");
    const TURQUESA = color("Turquesa");

    const ruta = `/cases/${casoId}/escenarios/${escenario.id}/composicion`;
    const inicial = escenario.composicion;
    let existe = Boolean(inicial);
    let comp = inicial
      ? { ancho: inicial.ancho, alto: inicial.alto, fondo_color: inicial.fondo_color, capas: clonar(inicial.capas) }
      : { ancho: FORMATOS[0].ancho, alto: FORMATOS[0].alto, fondo_color: color("Azul noche"), capas: [] };
    let seleccionId = null;
    let sucio = false;
    let accion = null; // arrastre o cambio de tamaño en curso
    let campos = {}; // inputs numéricos de la capa seleccionada, para refrescarlos al arrastrar
    let archivos = null; // biblioteca de imágenes del docente
    let estadoIA = null; // ¿se puede generar con IA? cuántas quedan esta hora

    const zona = h("div", { clase: "ev-zona" });
    const vista = Composicion.montar(zona, comp);
    const marco = h("div", { clase: "ev-marco" }, h("span", { clase: "ev-asa", title: "Arrastra para cambiar el tamaño" }));
    const herramientas = h("aside", { clase: "ev-herramientas", "aria-label": "Herramientas" });
    const panel = h("div", { clase: "ev-propiedades-capa" });
    const listaCapas = h("div", { clase: "ev-capas" });
    const propiedades = h("aside", { clase: "ev-propiedades", "aria-label": "Propiedades" }, panel, listaCapas);
    const biblioteca = h("div", { clase: "ev-biblioteca" });

    /* ---------- estado de la composición ---------- */

    const seleccionada = () => comp.capas.find((capa) => capa.id === seleccionId) || null;

    function marcarSucio() {
      sucio = true;
      botonGuardar.disabled = false;
    }

    function renumerar() {
      comp.capas.sort((a, b) => a.orden - b.orden);
      comp.capas.forEach((capa, i) => (capa.orden = i + 1));
    }

    function posicionarMarco() {
      const el = seleccionId && vista.capas.get(seleccionId);
      if (!el) {
        marco.remove();
        return;
      }
      if (marco.parentNode !== vista.lienzo) vista.lienzo.append(marco);
      marco.style.left = `${el.offsetLeft}px`;
      marco.style.top = `${el.offsetTop}px`;
      marco.style.width = `${el.offsetWidth}px`;
      marco.style.height = `${el.offsetHeight}px`;
    }

    function redibujar() {
      vista.redibujar(comp);
      const elegida = seleccionId && vista.capas.get(seleccionId);
      if (elegida) elegida.classList.add("cmp-seleccionada");
      posicionarMarco();
      pintarCapas();
    }

    function refrescarCapa(capa) {
      Composicion.aplicar(vista.capas.get(capa.id), capa);
      posicionarMarco();
      marcarSucio();
    }

    function seleccionar(id) {
      if (seleccionId === id) return;
      seleccionId = id;
      vista.lienzo.querySelectorAll(".cmp-seleccionada").forEach((el) => el.classList.remove("cmp-seleccionada"));
      const el = id && vista.capas.get(id);
      if (el) el.classList.add("cmp-seleccionada");
      posicionarMarco();
      pintarPropiedades();
      pintarCapas();
    }

    function agregar(capa) {
      if (comp.capas.length >= MAX_CAPAS) {
        Aviso.error(`Una composición admite como máximo ${MAX_CAPAS} capas.`);
        return;
      }
      const desplazamiento = (comp.capas.length % 8) * 30;
      capa.id = capa.id || nuevoId();
      capa.x = redondear(definido(capa.x) ? capa.x : 80 + desplazamiento);
      capa.y = redondear(definido(capa.y) ? capa.y : 80 + desplazamiento);
      capa.orden = comp.capas.length + 1;
      comp.capas.push(capa);
      marcarSucio();
      seleccionId = null;
      redibujar();
      seleccionar(capa.id);
    }

    function eliminarSeleccionada() {
      const capa = seleccionada();
      if (!capa) return;
      comp.capas = comp.capas.filter((otra) => otra.id !== capa.id);
      renumerar();
      seleccionId = null;
      marcarSucio();
      redibujar();
      pintarPropiedades();
    }

    function duplicar(capa) {
      const copia = clonar(capa);
      copia.id = nuevoId();
      copia.x = redondear(capa.x + 30);
      copia.y = redondear(capa.y + 30);
      agregar(copia);
    }

    function moverEnPila(capa, delta) {
      const posicion = comp.capas.findIndex((otra) => otra.id === capa.id);
      const destino = posicion + delta;
      if (destino < 0 || destino >= comp.capas.length) return;
      [comp.capas[posicion], comp.capas[destino]] = [comp.capas[destino], comp.capas[posicion]];
      comp.capas.forEach((otra, i) => (otra.orden = i + 1));
      marcarSucio();
      redibujar();
      pintarPropiedades();
    }

    /* ---------- capas nuevas ---------- */

    const agregarTexto = () =>
      agregar({
        tipo: "texto",
        contenido: "Escribe aquí",
        tamano: 56,
        color: BLANCO,
        alineacion: "izquierda",
        negrita: false,
        cursiva: false,
        ancho: 600,
        alto: null,
      });

    function agregarForma(forma) {
      const base = { tipo: "forma", forma, opacidad: 1, borde_grosor: 0, borde_color: null, radio: 24 };
      if (forma === "linea") {
        agregar({ ...base, relleno: null, borde_color: AMBAR, borde_grosor: 6, ancho: 400, alto: 0 });
        return;
      }
      const lado = forma === "circulo" ? { ancho: 240, alto: 240 } : { ancho: 360, alto: 200 };
      agregar({ ...base, relleno: TURQUESA, opacidad: 0.6, ...lado });
    }

    const agregarIcono = (nombre) =>
      agregar({ tipo: "icono", icono: nombre, color: AMBAR, opacidad: 1, ancho: 120, alto: 120 });

    async function agregarImagen(archivo) {
      const medidas = await new Promise((resolver) => {
        const imagen = new Image();
        imagen.onload = () => resolver({ ancho: imagen.naturalWidth, alto: imagen.naturalHeight });
        imagen.onerror = () => resolver(null);
        imagen.src = archivo.url;
      });
      if (!medidas) {
        Aviso.error("No se pudo leer la imagen.");
        return;
      }
      const factor = Math.min(1, (comp.ancho * 0.6) / medidas.ancho, (comp.alto * 0.6) / medidas.alto);
      agregar({
        tipo: "imagen",
        archivo_id: archivo.id,
        url: archivo.url,
        origen: archivo.origen === "GENERADO_IA" ? "IA" : "SUBIDA",
        ajuste: "contener",
        opacidad: 1,
        ancho: redondear(medidas.ancho * factor),
        alto: redondear(medidas.alto * factor),
      });
    }

    /* ---------- arrastrar y cambiar tamaño ---------- */

    function iniciar(modo, evento) {
      const capa = seleccionada();
      const el = capa && vista.capas.get(capa.id);
      if (!el) return;
      const unidad = vista.lienzo.clientWidth / comp.ancho;
      accion = {
        modo,
        capa,
        el,
        unidad,
        x0: evento.clientX,
        y0: evento.clientY,
        origen: {
          x: capa.x,
          y: capa.y,
          ancho: definido(capa.ancho) ? capa.ancho : el.offsetWidth / unidad,
          alto: definido(capa.alto) ? capa.alto : el.offsetHeight / unidad,
        },
      };
      vista.lienzo.setPointerCapture(evento.pointerId);
      evento.preventDefault();
    }

    function arrastrar(evento) {
      if (!accion) return;
      const { capa, origen, unidad } = accion;
      const dx = (evento.clientX - accion.x0) / unidad;
      const dy = (evento.clientY - accion.y0) / unidad;
      if (accion.modo === "mover") {
        capa.x = redondear(acotar(origen.x + dx, -COORDENADA_MAX, COORDENADA_MAX));
        capa.y = redondear(acotar(origen.y + dy, -COORDENADA_MAX, COORDENADA_MAX));
      } else {
        const minimo = capa.tipo === "forma" && capa.forma === "linea" ? 0 : 10;
        capa.ancho = redondear(acotar(origen.ancho + dx, 10, COORDENADA_MAX));
        // El texto crece solo en alto: únicamente se cambia su ancho.
        if (capa.tipo !== "texto") capa.alto = redondear(acotar(origen.alto + dy, minimo, COORDENADA_MAX));
      }
      refrescarCapa(capa);
      Object.entries(campos).forEach(([clave, entrada]) => {
        if (definido(capa[clave])) entrada.value = capa[clave];
      });
    }

    function terminarArrastre() {
      accion = null;
    }

    vista.lienzo.addEventListener("pointerdown", (evento) => {
      if (soloLectura) return;
      const capaEl = evento.target.closest(".cmp-capa");
      if (evento.target.closest(".ev-asa") && seleccionada()) {
        iniciar("tamano", evento);
      } else if (capaEl) {
        seleccionar(capaEl.dataset.capaId);
        iniciar("mover", evento);
      } else {
        seleccionar(null);
      }
    });
    vista.lienzo.addEventListener("pointermove", arrastrar);
    vista.lienzo.addEventListener("pointerup", terminarArrastre);
    vista.lienzo.addEventListener("pointercancel", terminarArrastre);

    /* ---------- controles de propiedades ---------- */

    function campoNumero(etiqueta, capa, clave, { minimo = -COORDENADA_MAX, maximo = COORDENADA_MAX, paso = 1, vacio = false } = {}) {
      const entrada = h("input", {
        type: "number",
        inputmode: "decimal",
        min: minimo,
        max: maximo,
        step: paso,
        value: definido(capa[clave]) ? capa[clave] : "",
        placeholder: vacio ? "auto" : null,
        "aria-label": etiqueta,
      });
      entrada.addEventListener("input", () => {
        if (entrada.value === "" && vacio) {
          capa[clave] = null;
        } else {
          const numero = parseFloat(entrada.value);
          if (Number.isNaN(numero)) return;
          capa[clave] = redondear(acotar(numero, minimo, maximo));
        }
        refrescarCapa(capa);
      });
      campos[clave] = entrada;
      return h("label", { clase: "campo ev-campo-corto" }, h("span", {}, etiqueta), entrada);
    }

    function campoColor(etiqueta, valor, alCambiar) {
      const entrada = h("input", { type: "color", value: valor, "aria-label": etiqueta });
      entrada.addEventListener("input", () => alCambiar(entrada.value));
      const muestras = paleta.map((p) => {
        const muestra = h("button", {
          type: "button",
          clase: "ev-muestra",
          title: p.nombre,
          "aria-label": `${etiqueta}: ${p.nombre}`,
          onclick: () => {
            entrada.value = p.hex;
            alCambiar(p.hex);
          },
        });
        muestra.style.backgroundColor = p.hex;
        return muestra;
      });
      return h("div", { clase: "campo ev-campo-color" }, h("span", {}, etiqueta), h("div", { clase: "ev-muestras" }, entrada, muestras));
    }

    function campoColorOpcional(etiqueta, capa, clave, porDefecto) {
      const activo = h("input", { type: "checkbox", "aria-label": `Usar ${etiqueta.toLowerCase()}` });
      activo.checked = definido(capa[clave]);
      const contenedor = h("div", { clase: "ev-color-opcional" });
      const pintar = () => {
        const selector = campoColor(etiqueta, capa[clave] || porDefecto, (valor) => {
          capa[clave] = valor;
          refrescarCapa(capa);
        });
        contenedor.replaceChildren(selector);
        contenedor.classList.toggle("oculto", !activo.checked);
      };
      activo.addEventListener("change", () => {
        capa[clave] = activo.checked ? capa[clave] || porDefecto : null;
        pintar();
        refrescarCapa(capa);
      });
      pintar();
      return h("div", {}, h("label", { clase: "ev-interruptor" }, activo, h("span", {}, etiqueta)), contenedor);
    }

    function campoOpacidad(capa) {
      const entrada = h("input", { type: "range", min: 0, max: 1, step: 0.05, value: capa.opacidad, "aria-label": "Opacidad" });
      entrada.addEventListener("input", () => {
        capa.opacidad = parseFloat(entrada.value);
        refrescarCapa(capa);
      });
      return h("label", { clase: "campo" }, h("span", {}, "Opacidad"), entrada);
    }

    function boton(texto, alPulsar, { clase = "boton-fantasma", titulo, deshabilitado = false } = {}) {
      return h("button", { type: "button", clase: `boton ${clase} boton-chico`, texto, title: titulo, disabled: deshabilitado, onclick: alPulsar });
    }

    function alternar(texto, activo, alPulsar, titulo) {
      return h("button", {
        type: "button",
        clase: `boton boton-chico ev-alternar ${activo ? "activo" : ""}`,
        "aria-pressed": String(activo),
        title: titulo,
        texto,
        onclick: alPulsar,
      });
    }

    function propiedadesTexto(capa) {
      const contenido = h("textarea", { rows: 3, maxlength: 1000, "aria-label": "Texto" });
      contenido.value = capa.contenido;
      contenido.addEventListener("input", () => {
        capa.contenido = contenido.value;
        refrescarCapa(capa);
      });
      const alineaciones = h(
        "div",
        { clase: "ev-segmentos", role: "group", "aria-label": "Alineación" },
        [
          ["izquierda", "⯇ Izq."],
          ["centro", "≡ Centro"],
          ["derecha", "Der. ⯈"],
        ].map(([valor, texto]) =>
          alternar(texto, capa.alineacion === valor, () => {
            capa.alineacion = valor;
            refrescarCapa(capa);
            pintarPropiedades();
          }),
        ),
      );
      return [
        h("label", { clase: "campo" }, h("span", {}, "Texto"), contenido),
        campoNumero("Tamaño", capa, "tamano", { minimo: 8, maximo: 400 }),
        campoColor("Color", capa.color, (valor) => {
          capa.color = valor;
          refrescarCapa(capa);
        }),
        alineaciones,
        h(
          "div",
          { clase: "ev-segmentos" },
          alternar("N Negrita", capa.negrita, () => {
            capa.negrita = !capa.negrita;
            refrescarCapa(capa);
            pintarPropiedades();
          }),
          alternar("I Cursiva", capa.cursiva, () => {
            capa.cursiva = !capa.cursiva;
            refrescarCapa(capa);
            pintarPropiedades();
          }),
        ),
      ];
    }

    function propiedadesForma(capa) {
      const tipo = h(
        "select",
        { "aria-label": "Tipo de forma" },
        Object.entries(NOMBRES_FORMA).map(([valor, nombre]) => h("option", { value: valor, selected: valor === capa.forma }, nombre)),
      );
      tipo.addEventListener("change", () => {
        capa.forma = tipo.value;
        if (capa.forma === "linea" && !capa.borde_color) capa.borde_color = AMBAR;
        if (capa.forma === "linea" && !capa.borde_grosor) capa.borde_grosor = 6;
        refrescarCapa(capa);
        pintarPropiedades();
      });
      const esLinea = capa.forma === "linea";
      return [
        h("label", { clase: "campo" }, h("span", {}, "Forma"), tipo),
        !esLinea && campoColorOpcional("Relleno", capa, "relleno", TURQUESA),
        campoColorOpcional(esLinea ? "Color de la línea" : "Borde", capa, "borde_color", AMBAR),
        campoNumero(esLinea ? "Grosor" : "Grosor del borde", capa, "borde_grosor", { minimo: 0, maximo: 100 }),
        capa.forma === "rectangulo_redondeado" && campoNumero("Redondeo", capa, "radio", { minimo: 0, maximo: 1000 }),
        campoOpacidad(capa),
      ];
    }

    function selectorIconos(actual, alElegir) {
      return h(
        "div",
        { clase: "ev-iconos", role: "group", "aria-label": "Iconos" },
        Composicion.ICONOS.map((nombre) => {
          const miniatura = h("span", { clase: "ev-icono-mini", "aria-hidden": "true" });
          miniatura.style.webkitMaskImage = miniatura.style.maskImage = `url("${Composicion.RUTA_ICONOS}${nombre}.svg")`;
          return h(
            "button",
            {
              type: "button",
              clase: `ev-icono-boton ${nombre === actual ? "activo" : ""}`,
              title: NOMBRES_ICONO[nombre],
              "aria-label": NOMBRES_ICONO[nombre],
              "aria-pressed": String(nombre === actual),
              onclick: () => alElegir(nombre),
            },
            miniatura,
          );
        }),
      );
    }

    function propiedadesIcono(capa) {
      return [
        selectorIconos(capa.icono, (nombre) => {
          capa.icono = nombre;
          refrescarCapa(capa);
          pintarPropiedades();
        }),
        campoColor("Color", capa.color, (valor) => {
          capa.color = valor;
          refrescarCapa(capa);
        }),
        campoOpacidad(capa),
      ];
    }

    function propiedadesImagen(capa) {
      const ajuste = h(
        "select",
        { "aria-label": "Ajuste de la imagen" },
        [
          ["contener", "Contener (se ve completa)"],
          ["cubrir", "Cubrir (recorta lo que sobre)"],
          ["estirar", "Estirar"],
        ].map(([valor, nombre]) => h("option", { value: valor, selected: valor === capa.ajuste }, nombre)),
      );
      ajuste.addEventListener("change", () => {
        capa.ajuste = ajuste.value;
        refrescarCapa(capa);
      });
      return [
        h("label", { clase: "campo" }, h("span", {}, "Ajuste"), ajuste),
        campoOpacidad(capa),
        boton("▣ Usar como fondo (cubre el lienzo)", () => {
          Object.assign(capa, { x: 0, y: 0, ancho: comp.ancho, alto: comp.alto, ajuste: "cubrir" });
          while (comp.capas[0] !== capa) moverEnPila(capa, -1);
          refrescarCapa(capa);
          pintarPropiedades();
        }),
      ];
    }

    const NOMBRES_TIPO = { texto: "Texto", imagen: "Imagen", forma: "Forma", icono: "Icono" };
    const PROPIEDADES = { texto: propiedadesTexto, forma: propiedadesForma, icono: propiedadesIcono, imagen: propiedadesImagen };

    function pintarPropiedades() {
      campos = {};
      const capa = seleccionada();
      if (!capa) {
        Dom.reemplazar(panel, h("p", { clase: "ayuda" }, "Toca una capa del lienzo para editarla, o agrega una desde el panel izquierdo."));
        return;
      }
      const posicion = comp.capas.findIndex((otra) => otra.id === capa.id);
      Dom.reemplazar(
        panel,
        h("h4", { clase: "ev-subtitulo" }, `Capa: ${NOMBRES_TIPO[capa.tipo]}`),
        PROPIEDADES[capa.tipo](capa),
        h(
          "div",
          { clase: "ev-medidas" },
          campoNumero("X", capa, "x"),
          campoNumero("Y", capa, "y"),
          campoNumero("Ancho", capa, "ancho", { minimo: 0, vacio: true }),
          campoNumero("Alto", capa, "alto", { minimo: 0, vacio: true }),
        ),
        h(
          "div",
          { clase: "ev-fila-botones" },
          boton("⬆ Al frente", () => moverEnPila(capa, 1), { deshabilitado: posicion === comp.capas.length - 1 }),
          boton("⬇ Atrás", () => moverEnPila(capa, -1), { deshabilitado: posicion === 0 }),
          boton("⧉ Duplicar", () => duplicar(capa)),
          boton("🗑 Borrar", eliminarSeleccionada, { clase: "boton-peligro" }),
        ),
      );
    }

    function resumenDe(capa) {
      if (capa.tipo === "texto") return `Texto · ${capa.contenido.slice(0, 22) || "(vacío)"}`;
      if (capa.tipo === "forma") return NOMBRES_FORMA[capa.forma];
      if (capa.tipo === "icono") return `Icono · ${NOMBRES_ICONO[capa.icono]}`;
      return "Imagen";
    }

    function pintarCapas() {
      const ordenadas = [...comp.capas].sort((a, b) => b.orden - a.orden); // la de arriba primero
      Dom.reemplazar(
        listaCapas,
        h("h4", { clase: "ev-subtitulo" }, `Capas (${comp.capas.length})`),
        ordenadas.length
          ? ordenadas.map((capa) =>
              h(
                "button",
                {
                  type: "button",
                  clase: `ev-capa-fila ${capa.id === seleccionId ? "activa" : ""}`,
                  "aria-pressed": String(capa.id === seleccionId),
                  onclick: () => seleccionar(capa.id),
                },
                h("span", { clase: "ev-capa-numero" }, String(capa.orden)),
                h("span", { clase: "ev-capa-nombre" }, resumenDe(capa)),
              ),
            )
          : h("p", { clase: "ayuda" }, "Todavía no hay capas."),
      );
    }

    /* ---------- barra de herramientas ---------- */

    async function subirImagen(archivo) {
      if (!archivo) return;
      if (!["image/jpeg", "image/png"].includes(archivo.type)) {
        Aviso.error("Solo se admiten imágenes JPG o PNG.");
        return;
      }
      if (archivo.size > LIMITE_BYTES) {
        Aviso.error("La imagen supera el máximo de 5 MB.");
        return;
      }
      try {
        const subido = await Api.subirArchivo("/archivos/escenarios", archivo);
        Aviso.exito("Imagen subida.");
        archivos = [subido, ...(archivos || [])];
        pintarBiblioteca();
        await agregarImagen(subido);
      } catch (error) {
        Aviso.deError(error);
      }
    }

    async function cargarBiblioteca() {
      try {
        archivos = await Api.get("/archivos", { limite: 50 });
      } catch (error) {
        archivos = [];
        Aviso.deError(error);
      }
      pintarBiblioteca();
    }

    function verPrompt(archivo) {
      const cuerpo = h(
        "div",
        { clase: "ev-ia-dialogo" },
        h("p", { clase: "ayuda" }, "Descripción con la que se generó esta imagen. Puedes ajustarla y generar otra."),
        h("blockquote", { clase: "ev-prompt" }, archivo.prompt_generacion),
        h(
          "div",
          { clase: "ev-fila-botones" },
          boton("✨ Ajustar y regenerar", () => {
            hoja.cerrar();
            abrirGenerador({ prompt: archivo.prompt_generacion });
          }, { clase: "boton-info" }),
          boton("Agregar al lienzo", () => {
            hoja.cerrar();
            agregarImagen(archivo);
          }),
        ),
      );
      const hoja = Modal.hoja("✨ Imagen generada con IA", cuerpo);
    }

    function pintarBiblioteca() {
      if (archivos === null) {
        Dom.reemplazar(biblioteca, h("p", { clase: "ayuda" }, "Cargando tus imágenes…"));
        return;
      }
      if (!archivos.length) {
        Dom.reemplazar(biblioteca, h("p", { clase: "ayuda" }, "Aún no has subido ni generado imágenes."));
        return;
      }
      Dom.reemplazar(
        biblioteca,
        archivos.map((archivo) => {
          const generada = archivo.origen === "GENERADO_IA";
          return h(
            "div",
            { clase: `ev-miniatura ${generada ? "ev-miniatura-ia" : ""}` },
            h(
              "button",
              { type: "button", clase: "ev-miniatura-boton", title: `Agregar «${archivo.nombre_original}»`, onclick: () => agregarImagen(archivo) },
              h("img", { src: archivo.url, alt: generada ? "Imagen generada con IA" : archivo.nombre_original, draggable: "false" }),
            ),
            generada && h("span", { clase: "ev-insignia-ia", title: "Generada con IA" }, "✨ IA"),
            generada &&
              archivo.prompt_generacion &&
              h("button", {
                type: "button",
                clase: "ev-miniatura-prompt",
                "aria-label": "Ver la descripción con la que se generó",
                title: "Ver la descripción (prompt)",
                texto: "ℹ",
                onclick: () => verPrompt(archivo),
              }),
            h("button", {
              type: "button",
              clase: "ev-miniatura-borrar",
              "aria-label": `Borrar ${archivo.nombre_original}`,
              title: "Borrar del servidor",
              texto: "×",
              onclick: async () => {
                const confirmado = await Modal.confirmar({
                  titulo: "¿Borrar la imagen?",
                  mensaje: "Se elimina de tu biblioteca y del servidor. Si algún escenario la usa, no se podrá borrar.",
                  textoConfirmar: "Borrar",
                  peligro: true,
                });
                if (!confirmado) return;
                try {
                  await Api.eliminar(`/archivos/${archivo.id}`);
                  archivos = archivos.filter((otro) => otro.id !== archivo.id);
                  pintarBiblioteca();
                } catch (error) {
                  Aviso.deError(error);
                }
              },
            }),
          );
        }),
      );
    }

    /* ---------- generar con IA ---------- */

    async function cargarEstadoIA() {
      try {
        estadoIA = await Api.get("/archivos/generacion");
      } catch (_) {
        estadoIA = { disponible: false, motivo: "No se pudo comprobar si la generación está disponible.", restantes: 0, max_por_hora: 0, largo_max_prompt: 500, tamanos: [] };
      }
      pintarHerramientas();
    }

    function tamanoSugerido() {
      if (comp.ancho > comp.alto) return "1536x1024";
      return comp.ancho < comp.alto ? "1024x1536" : "1024x1024";
    }

    function abrirGenerador({ prompt = "" } = {}) {
      const estado = estadoIA;
      const tamanos = estado.tamanos;
      let elegido = tamanos.some((t) => t.valor === tamanoSugerido()) ? tamanoSugerido() : (tamanos[0] || {}).valor;
      let generada = null;

      const area = h("textarea", {
        rows: 4,
        maxlength: estado.largo_max_prompt,
        placeholder: "Ej.: Un pasillo de universidad al atardecer, ilustración plana, sin texto",
        "aria-label": "Descripción de la imagen",
      });
      area.value = prompt;
      const contador = h("small", { clase: "ayuda" });
      const cupo = h("small", { clase: "ayuda" });
      const resultado = h("div", { clase: "ev-ia-resultado", "aria-live": "polite" });
      const botonGenerar = h("button", { type: "button", clase: "boton boton-principal", texto: "✨ Generar imagen" });
      const botonAgregar = h("button", { type: "button", clase: "boton boton-info oculto", texto: "Agregar al lienzo" });

      const opciones = h(
        "div",
        { clase: "ev-segmentos", role: "radiogroup", "aria-label": "Forma de la imagen" },
        tamanos.map((t) =>
          h(
            "label",
            { clase: "ev-opcion-tamano" },
            h("input", {
              type: "radio",
              name: "tamano-ia",
              value: t.valor,
              checked: t.valor === elegido,
              onchange: () => (elegido = t.valor),
            }),
            h("span", {}, `${t.etiqueta} (${t.ancho} × ${t.alto})`),
          ),
        ),
      );

      function refrescar() {
        contador.textContent = `${area.value.length} / ${estado.largo_max_prompt}`;
        cupo.textContent = `Te quedan ${estado.restantes} de ${estado.max_por_hora} imágenes esta hora.`;
        botonGenerar.disabled = !estado.disponible || estado.restantes <= 0 || !area.value.trim();
      }
      area.addEventListener("input", refrescar);

      function error(mensaje) {
        Dom.reemplazar(resultado, h("p", { clase: "ev-ia-error", role: "alert" }, mensaje));
      }

      botonGenerar.addEventListener("click", async () => {
        botonGenerar.disabled = true;
        botonGenerar.classList.add("cargando");
        botonAgregar.classList.add("oculto");
        Dom.reemplazar(resultado, h("p", { clase: "ayuda" }, "Generando la imagen… puede tardar hasta un minuto."));
        try {
          generada = await Api.post("/archivos/generar", {
            caso_id: casoId,
            escenario_id: escenario.id,
            prompt: area.value.trim(),
            tamano: elegido,
          });
          archivos = [generada, ...(archivos || [])];
          pintarBiblioteca();
          Dom.reemplazar(
            resultado,
            h("img", { src: generada.url, alt: "Imagen generada con IA", clase: "ev-ia-vista" }),
            h("p", { clase: "ayuda" }, "Ya está en tu biblioteca. Si no te convence, ajusta la descripción y vuelve a generar."),
          );
          botonAgregar.classList.remove("oculto");
        } catch (fallo) {
          error(Api.mensajeDe(fallo));
        } finally {
          botonGenerar.classList.remove("cargando");
          try {
            estadoIA = await Api.get("/archivos/generacion");
            Object.assign(estado, estadoIA);
          } catch (_) {
            // el cupo se refresca la próxima vez
          }
          refrescar();
          pintarHerramientas();
        }
      });
      botonAgregar.addEventListener("click", () => {
        hoja.cerrar();
        if (generada) agregarImagen(generada);
      });

      const cuerpo = h(
        "div",
        { clase: "ev-ia-dialogo" },
        h("p", { clase: "ev-nota-ia" }, "💡 La imagen es el contexto del escenario; no marques la respuesta correcta ni des pistas."),
        estado.disponible ? null : h("p", { clase: "ev-ia-error", role: "alert" }, estado.motivo),
        h("label", { clase: "campo" }, h("span", {}, "Describe la imagen"), area),
        contador,
        h("span", { clase: "ev-etiqueta" }, "Forma"),
        opciones,
        cupo,
        h("div", { clase: "ev-fila-botones" }, botonGenerar, botonAgregar),
        resultado,
      );
      const hoja = Modal.hoja("✨ Generar imagen con IA", cuerpo);
      refrescar();
      area.focus();
    }

    function cambiarFormato(valor) {
      const formato = FORMATOS[Number(valor)];
      if (!formato) return;
      comp.ancho = formato.ancho;
      comp.alto = formato.alto;
      marcarSucio();
      redibujar();
    }

    function pintarHerramientas() {
      const indice = FORMATOS.findIndex((f) => f.ancho === comp.ancho && f.alto === comp.alto);
      const formatos = h(
        "select",
        { "aria-label": "Tamaño del lienzo", onchange: (evento) => cambiarFormato(evento.target.value) },
        indice < 0 ? h("option", { value: "-1", selected: true }, `Actual (${comp.ancho} × ${comp.alto})`) : null,
        FORMATOS.map((f, i) => h("option", { value: String(i), selected: i === indice }, f.nombre)),
      );
      const archivo = h("input", {
        type: "file",
        accept: "image/jpeg,image/png",
        clase: "oculto",
        "aria-label": "Subir imagen",
        onchange: (evento) => {
          subirImagen(evento.target.files[0]);
          evento.target.value = "";
        },
      });
      Dom.reemplazar(
        herramientas,
        h("h4", { clase: "ev-subtitulo" }, "Lienzo"),
        h("label", { clase: "campo" }, h("span", {}, "Tamaño"), formatos),
        campoColor("Color de fondo", comp.fondo_color, (valor) => {
          comp.fondo_color = valor;
          vista.lienzo.style.backgroundColor = valor;
          marcarSucio();
        }),
        h("h4", { clase: "ev-subtitulo" }, "Agregar"),
        h(
          "div",
          { clase: "ev-fila-botones" },
          boton("🔤 Texto", agregarTexto, { clase: "boton-info" }),
          boton("▭ Rectángulo", () => agregarForma("rectangulo"), { clase: "boton-info" }),
          boton("▢ Redondeado", () => agregarForma("rectangulo_redondeado"), { clase: "boton-info" }),
          boton("◯ Círculo", () => agregarForma("circulo"), { clase: "boton-info" }),
          boton("╱ Línea", () => agregarForma("linea"), { clase: "boton-info" }),
        ),
        h("h4", { clase: "ev-subtitulo" }, "Iconos"),
        selectorIconos(null, agregarIcono),
        h("h4", { clase: "ev-subtitulo" }, "Imágenes"),
        boton("⬆ Subir imagen (JPG o PNG, máx. 5 MB)", () => archivo.click(), { clase: "boton-principal" }),
        archivo,
        biblioteca,
        h(
          "div",
          { clase: "ev-ia" },
          h("button", {
            type: "button",
            clase: "boton boton-info boton-chico",
            disabled: !estadoIA || !estadoIA.disponible,
            title: estadoIA && !estadoIA.disponible ? estadoIA.motivo : "Generar una imagen con IA",
            texto: "✨ Generar imagen con IA",
            onclick: () => abrirGenerador(),
          }),
          h(
            "small",
            { clase: "ayuda" },
            !estadoIA
              ? "Comprobando…"
              : estadoIA.disponible
                ? `Te quedan ${estadoIA.restantes} de ${estadoIA.max_por_hora} esta hora.`
                : estadoIA.motivo,
          ),
        ),
      );
    }

    /* ---------- guardar y cerrar ---------- */

    async function guardar() {
      if (comp.capas.some((capa) => capa.tipo === "texto" && !capa.contenido.trim())) {
        Aviso.error("Hay una capa de texto vacía: escribe algo o bórrala.");
        return;
      }
      botonGuardar.disabled = true;
      botonGuardar.classList.add("cargando");
      try {
        const respuesta = await Api.put(ruta, {
          ancho: comp.ancho,
          alto: comp.alto,
          fondo_color: comp.fondo_color,
          capas: comp.capas,
        });
        existe = true;
        sucio = false;
        comp = { ancho: respuesta.ancho, alto: respuesta.alto, fondo_color: respuesta.fondo_color, capas: respuesta.capas };
        escenario.composicion = respuesta;
        redibujar();
        pintarPropiedades();
        botonQuitar.classList.remove("oculto");
        Aviso.exito("Composición guardada.");
        if (alGuardar) alGuardar(respuesta);
      } catch (error) {
        botonGuardar.disabled = false;
        Aviso.deError(error);
      } finally {
        botonGuardar.classList.remove("cargando");
      }
    }

    async function quitar() {
      const confirmado = await Modal.confirmar({
        titulo: "¿Quitar la composición?",
        mensaje: "El escenario volverá a mostrarse solo con su texto. Las imágenes subidas siguen en tu biblioteca.",
        textoConfirmar: "Quitar",
        peligro: true,
      });
      if (!confirmado) return;
      try {
        await Api.eliminar(ruta);
        existe = false;
        sucio = false;
        escenario.composicion = null;
        comp = { ancho: FORMATOS[0].ancho, alto: FORMATOS[0].alto, fondo_color: color("Azul noche"), capas: [] };
        seleccionId = null;
        redibujar();
        pintarPropiedades();
        pintarHerramientas();
        botonQuitar.classList.add("oculto");
        botonGuardar.disabled = true;
        Aviso.exito("Composición quitada.");
        if (alGuardar) alGuardar(null);
      } catch (error) {
        Aviso.deError(error);
      }
    }

    async function cerrar() {
      if (sucio) {
        const descartar = await Modal.confirmar({
          titulo: "Tienes cambios sin guardar",
          mensaje: "Si cierras ahora se pierden los cambios de esta composición.",
          textoConfirmar: "Cerrar sin guardar",
          textoCancelar: "Seguir editando",
          peligro: true,
        });
        if (!descartar) return;
      }
      document.removeEventListener("keydown", alTeclear);
      document.body.classList.remove("ev-abierto");
      vista.destruir();
      fondo.remove();
    }

    function alTeclear(evento) {
      if (document.querySelector(".modal-fondo")) return;
      if (evento.key === "Escape") {
        cerrar();
        return;
      }
      if (soloLectura || !seleccionId || /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return;
      const capa = seleccionada();
      const paso = evento.shiftKey ? 10 : 1;
      const desplazamientos = { ArrowLeft: [-paso, 0], ArrowRight: [paso, 0], ArrowUp: [0, -paso], ArrowDown: [0, paso] };
      if (evento.key === "Delete" || evento.key === "Backspace") {
        evento.preventDefault();
        eliminarSeleccionada();
      } else if (desplazamientos[evento.key]) {
        evento.preventDefault();
        capa.x = redondear(capa.x + desplazamientos[evento.key][0]);
        capa.y = redondear(capa.y + desplazamientos[evento.key][1]);
        refrescarCapa(capa);
        Object.entries(campos).forEach(([clave, entrada]) => {
          if (definido(capa[clave])) entrada.value = capa[clave];
        });
      }
    }

    /* ---------- armado de la pantalla ---------- */

    const botonGuardar = h("button", { type: "button", clase: "boton boton-principal boton-chico", texto: "💾 Guardar", disabled: true, onclick: guardar });
    const botonQuitar = h("button", {
      type: "button",
      clase: `boton boton-fantasma boton-chico ${existe ? "" : "oculto"}`,
      texto: "Quitar composición",
      onclick: quitar,
    });
    const botonCerrar = h("button", { type: "button", clase: "boton boton-fantasma boton-chico", texto: "✕ Cerrar", onclick: cerrar });

    const fondo = h(
      "div",
      { clase: "ev-fondo", role: "dialog", "aria-modal": "true", "aria-label": "Editor visual de escenarios" },
      h(
        "header",
        { clase: "ev-cabecera" },
        h(
          "div",
          { clase: "ev-titulo" },
          h("h2", { clase: "titulo-tarjeta" }, "🎨 Editor visual de escenarios"),
          h("p", { clase: "ayuda" }, escenario.titulo),
        ),
        h("div", { clase: "ev-acciones" }, soloLectura ? null : [botonQuitar, botonGuardar], botonCerrar),
      ),
      h(
        "p",
        { clase: "ev-nota" },
        soloLectura
          ? "🔒 El caso está publicado: la composición no se puede cambiar. Crea una nueva versión del caso para editarla."
          : "💡 La imagen es el contexto del escenario; no marques la respuesta correcta ni des pistas.",
      ),
      soloLectura ? null : h("p", { clase: "ev-aviso-movil" }, "Este editor está pensado para pantalla de computador: arrastrar capas con el dedo es incómodo. Lo que importa es cómo se ve el resultado en el celular del estudiante."),
      h("div", { clase: `ev-cuerpo ${soloLectura ? "ev-solo-lectura" : ""}` }, soloLectura ? null : herramientas, zona, soloLectura ? null : propiedades),
    );

    document.addEventListener("keydown", alTeclear);
    document.body.classList.add("ev-abierto");
    document.body.append(fondo);
    if (!soloLectura) {
      pintarHerramientas();
      pintarPropiedades();
      pintarCapas();
      pintarBiblioteca();
      cargarBiblioteca();
      cargarEstadoIA();
    }
    vista.ajustar();
  }

  return { abrir, vistaPrevia };
})();
