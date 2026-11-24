"use strict";

(function () {
  const formulario = document.getElementById("formulario-registro");
  const pestanas = document.querySelectorAll(".pestana");
  const ayudaRol = document.getElementById("ayuda-rol");
  const boton = document.getElementById("boton-registrar");

  const AYUDAS = {
    ESTUDIANTE:
      "Usa tu correo institucional (termina en .edu.co). Podrás ingresar apenas verifiques tu correo con un código de 6 dígitos. Para jugar un caso necesitarás el código que te envíe tu docente.",
    DOCENTE:
      "Puedes usar cualquier correo. Verificarás tu correo con un código de 6 dígitos y luego un administrador debe aprobar tu cuenta antes de que puedas crear casos y sesiones. Mientras tanto podrás ingresar para ver el estado de tu solicitud.",
  };

  let rol = "ESTUDIANTE";

  function seleccionarRol(nuevo) {
    rol = nuevo;
    pestanas.forEach((otra) => {
      const activa = otra.dataset.rol === nuevo;
      otra.classList.toggle("activa", activa);
      otra.setAttribute("aria-selected", String(activa));
    });
    ayudaRol.textContent = AYUDAS[nuevo];
    document.getElementById("correo").placeholder =
      nuevo === "DOCENTE" ? "tucorreo@ejemplo.com (cualquier correo)" : "nombre@universidad.edu.co";
  }

  pestanas.forEach((pestana) =>
    pestana.addEventListener("click", () => seleccionarRol(pestana.dataset.rol)),
  );

  const rolSolicitado = new URLSearchParams(window.location.search).get("rol");
  if (rolSolicitado === "DOCENTE" || rolSolicitado === "ESTUDIANTE") seleccionarRol(rolSolicitado);

  // Si ya hay una sesión válida no tiene sentido registrarse otra vez.
  const claims = Api.claims();
  if (claims && !(claims.exp && claims.exp * 1000 <= Date.now())) {
    window.location.replace(Api.rutaInicioDelRol(claims.rol));
    return;
  }

  const vistaFormulario = document.querySelector("main > section.tarjeta");
  const ayudaDuplicado = document.getElementById("ayuda-duplicado");
  const enlaceVerificar = document.getElementById("enlace-verificar");
  const vistaCodigo = document.getElementById("vista-codigo");
  const contenedorCasillas = document.getElementById("casillas-codigo");
  const formularioCodigo = document.getElementById("formulario-codigo");
  const botonVerificar = document.getElementById("boton-verificar");
  const botonReenviar = document.getElementById("boton-reenviar");
  const textoVigencia = document.getElementById("vigencia-codigo");
  const LONGITUD = 6;

  // La contraseña solo vive en memoria mientras dura esta pantalla: sirve para
  // entrar solo tras verificar y nunca se guarda en el navegador.
  let correoActual = "";
  let contrasenaEnMemoria = null;
  let vigenciaHasta = 0;
  let reenvioHasta = 0;
  let temporizador = null;
  let verificando = false;

  const casillas = Array.from({ length: LONGITUD }, (_, indice) => {
    const casilla = Dom.h("input", {
      type: "text",
      clase: "casilla-codigo",
      inputmode: "numeric",
      maxlength: "1",
      autocomplete: indice === 0 ? "one-time-code" : "off",
      "aria-label": `Dígito ${indice + 1} de ${LONGITUD}`,
    });
    contenedorCasillas.append(casilla);
    return casilla;
  });

  const valorCodigo = () => casillas.map((casilla) => casilla.value).join("");

  function refrescarCasillas() {
    casillas.forEach((casilla) => casilla.classList.toggle("llena", casilla.value !== ""));
    botonVerificar.disabled = valorCodigo().length !== LONGITUD || verificando;
  }

  function limpiarCasillas() {
    contenedorCasillas.classList.remove("error", "acierto");
    casillas.forEach((casilla) => (casilla.value = ""));
    refrescarCasillas();
    casillas[0].focus();
  }

  function rellenar(digitos, desde = 0) {
    const limpios = digitos.replace(/\D/g, "").slice(0, LONGITUD - desde);
    [...limpios].forEach((digito, posicion) => (casillas[desde + posicion].value = digito));
    refrescarCasillas();
    const siguiente = Math.min(desde + limpios.length, LONGITUD - 1);
    casillas[siguiente].focus();
    if (valorCodigo().length === LONGITUD) verificar();
  }

  casillas.forEach((casilla, indice) => {
    casilla.addEventListener("input", () => {
      const digitos = casilla.value.replace(/\D/g, "");
      casilla.value = "";
      if (digitos) rellenar(digitos, indice);
      else refrescarCasillas();
    });
    casilla.addEventListener("keydown", (evento) => {
      if (evento.key === "Backspace" && casilla.value === "" && indice > 0) {
        casillas[indice - 1].value = "";
        casillas[indice - 1].focus();
        refrescarCasillas();
      } else if (evento.key === "ArrowLeft" && indice > 0) {
        casillas[indice - 1].focus();
      } else if (evento.key === "ArrowRight" && indice < LONGITUD - 1) {
        casillas[indice + 1].focus();
      }
    });
    casilla.addEventListener("paste", (evento) => {
      evento.preventDefault();
      rellenar((evento.clipboardData || window.clipboardData).getData("text"));
    });
    casilla.addEventListener("focus", () => casilla.select());
  });

  const formatoTiempo = (segundos) =>
    `${String(Math.floor(segundos / 60)).padStart(2, "0")}:${String(segundos % 60).padStart(2, "0")}`;

  function actualizarContadores() {
    const restoReenvio = Math.max(0, Math.ceil((reenvioHasta - Date.now()) / 1000));
    botonReenviar.disabled = restoReenvio > 0;
    botonReenviar.textContent =
      restoReenvio > 0 ? `Reenviar código (${restoReenvio} s)` : "Reenviar código";
    if (vigenciaHasta === null) {
      textoVigencia.textContent = "Escribe el código de 6 dígitos que te enviamos.";
      return;
    }
    const restoVigencia = Math.max(0, Math.ceil((vigenciaHasta - Date.now()) / 1000));
    textoVigencia.classList.toggle("vencido", restoVigencia === 0);
    textoVigencia.textContent =
      restoVigencia > 0
        ? `El código vence en ${formatoTiempo(restoVigencia)}`
        : "El código venció. Pide uno nuevo.";
  }

  function iniciarContadores(vigenciaSeg, reenvioSeg) {
    vigenciaHasta = vigenciaSeg > 0 ? Date.now() + vigenciaSeg * 1000 : null;
    reenvioHasta = Date.now() + reenvioSeg * 1000;
    actualizarContadores();
    clearInterval(temporizador);
    temporizador = setInterval(actualizarContadores, 1000);
  }

  function mostrarCodigo(correo, vigenciaSeg, reenvioSeg) {
    correoActual = correo;
    document.getElementById("correo-codigo").textContent = correo;
    vistaFormulario.hidden = true;
    vistaCodigo.hidden = false;
    limpiarCasillas();
    iniciarContadores(vigenciaSeg, reenvioSeg);
  }

  function marcarCasillas(clase) {
    contenedorCasillas.classList.remove("error", "acierto");
    void contenedorCasillas.offsetWidth;
    contenedorCasillas.classList.add(clase);
  }

  async function entrarAutomaticamente() {
    if (!contrasenaEnMemoria) {
      sessionStorage.setItem(CLAVES_SESION.aviso, "Correo verificado. Ya puedes ingresar.");
      window.location.href = "/app/";
      return;
    }
    try {
      const respuesta = await Api.post(
        "/auth/login",
        { correo: correoActual, contrasena: contrasenaEnMemoria },
        { credenciales: true },
      );
      Api.guardarSesion(respuesta.token_acceso, respuesta.usuario);
      window.location.href = Api.rutaInicioDelRol(Api.rol());
    } catch (error) {
      sessionStorage.setItem(CLAVES_SESION.aviso, "Correo verificado. Ingresa con tu contraseña.");
      window.location.href = "/app/";
    }
  }

  async function verificar() {
    const codigo = valorCodigo();
    if (verificando || codigo.length !== LONGITUD) return;
    verificando = true;
    botonVerificar.disabled = true;
    botonVerificar.classList.add("cargando");
    try {
      const respuesta = await Api.post(
        "/auth/registro/verificar",
        { correo: correoActual, codigo },
        { credenciales: true },
      );
      marcarCasillas("acierto");
      clearInterval(temporizador);
      botonReenviar.disabled = true;
      Aviso.exito(respuesta.mensaje);
      setTimeout(entrarAutomaticamente, 1200);
    } catch (error) {
      marcarCasillas("error");
      Aviso.deError(error);
      verificando = false;
      botonVerificar.classList.remove("cargando");
      setTimeout(limpiarCasillas, 400);
      return;
    }
    botonVerificar.classList.remove("cargando");
  }

  formularioCodigo.addEventListener("submit", (evento) => {
    evento.preventDefault();
    verificar();
  });

  botonReenviar.addEventListener("click", async () => {
    botonReenviar.disabled = true;
    try {
      const respuesta = await Api.post(
        "/auth/registro/reenviar",
        { correo: correoActual },
        { credenciales: true },
      );
      Aviso.info(respuesta.mensaje);
      iniciarContadores(respuesta.vigencia_segundos, respuesta.reenvio_segundos);
      limpiarCasillas();
    } catch (error) {
      Aviso.deError(error);
      botonReenviar.disabled = false;
    }
  });

  // Entrada desde el login de una cuenta sin verificar: pantalla de código directa.
  const correoPendiente = new URLSearchParams(window.location.search).get("verificar");
  if (correoPendiente) {
    mostrarCodigo(correoPendiente, 0, 0);
    Aviso.info("Escribe el código que te enviamos o pide uno nuevo con «Reenviar código».");
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const nombre = document.getElementById("nombre").value.trim();
    const correo = document.getElementById("correo").value.trim();
    const contrasena = document.getElementById("contrasena").value;
    const repetida = document.getElementById("contrasena2").value;

    if (!nombre || !correo || !contrasena) {
      Aviso.error("Completa todos los campos.");
      return;
    }
    if (contrasena.length < 8) {
      Aviso.error("La contraseña debe tener al menos 8 caracteres.");
      return;
    }
    if (contrasena !== repetida) {
      Aviso.error("Las contraseñas no coinciden.");
      return;
    }

    boton.disabled = true;
    boton.classList.add("cargando");
    try {
      const respuesta = await Api.post(
        "/auth/registro",
        { nombre, correo, contrasena, rol },
        { credenciales: true },
      );
      contrasenaEnMemoria = contrasena;
      mostrarCodigo(respuesta.correo, respuesta.vigencia_segundos, respuesta.reenvio_segundos);
      Aviso.exito(respuesta.mensaje);
      boton.disabled = false;
      boton.classList.remove("cargando");
    } catch (error) {
      Aviso.deError(error);
      if (error.estado === 409) {
        enlaceVerificar.href = `/app/registro?verificar=${encodeURIComponent(correo)}`;
        ayudaDuplicado.hidden = false;
      }
      boton.disabled = false;
      boton.classList.remove("cargando");
    }
  });
})();
