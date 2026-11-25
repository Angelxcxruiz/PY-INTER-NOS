"use strict";

(function () {
  const formulario = document.getElementById("formulario-login");
  const pestanas = document.querySelectorAll(".pestana");
  const campoSecreto = document.getElementById("secreto");
  const etiquetaSecreto = document.getElementById("etiqueta-secreto");
  const ayudaSecreto = document.getElementById("ayuda-secreto");
  const botonIngresar = document.getElementById("boton-ingresar");
  const campoCorreo = document.getElementById("correo");

  const MODOS = {
    estudiante: {
      etiqueta: "Código de la convocatoria",
      ayuda: "Tu docente te envió el código por correo cuando te convocó a la sesión.",
      autocompletar: "off",
      ruta: "/auth/student-login",
      cuerpo: (correo, secreto) => ({ correo, codigo: secreto }),
    },
    docente: {
      etiqueta: "Contraseña",
      ayuda: "Para docentes, administradores y estudiantes con cuenta registrada.",
      autocompletar: "current-password",
      ruta: "/auth/login",
      cuerpo: (correo, secreto) => ({ correo, contrasena: secreto }),
    },
  };

  let modo = "estudiante";

  function cambiarModo(nuevo) {
    modo = nuevo;
    pestanas.forEach((pestana) => {
      const activa = pestana.dataset.modo === nuevo;
      pestana.classList.toggle("activa", activa);
      pestana.setAttribute("aria-selected", String(activa));
    });
    const config = MODOS[nuevo];
    etiquetaSecreto.textContent = config.etiqueta;
    ayudaSecreto.textContent = config.ayuda;
    campoSecreto.setAttribute("autocomplete", config.autocompletar);
    campoSecreto.value = "";
  }

  pestanas.forEach((pestana) =>
    pestana.addEventListener("click", () => cambiarModo(pestana.dataset.modo)),
  );

  // Aviso dejado por una redirección (sesión vencida, etc.).
  const pendiente = sessionStorage.getItem(CLAVES_SESION.aviso);
  if (pendiente) {
    sessionStorage.removeItem(CLAVES_SESION.aviso);
    Aviso.info(pendiente);
  }

  // Si ya hay una sesión válida, se entra directo.
  const claims = Api.claims();
  if (claims && !(claims.exp && claims.exp * 1000 <= Date.now())) {
    window.location.replace(Api.rutaInicioDelRol(claims.rol));
    return;
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const correo = campoCorreo.value.trim();
    const secreto = campoSecreto.value;
    if (!correo || !secreto) {
      Aviso.error(
        modo === "estudiante"
          ? "Escribe tu correo y el código de la convocatoria."
          : "Escribe tu correo y tu contraseña.",
      );
      return;
    }

    const config = MODOS[modo];
    botonIngresar.disabled = true;
    botonIngresar.classList.add("cargando");
    try {
      const respuesta = await Api.post(config.ruta, config.cuerpo(correo, secreto), {
        credenciales: true,
      });
      Api.guardarSesion(respuesta.token_acceso, respuesta.usuario);
      window.location.href = Api.rutaInicioDelRol(Api.rol());
    } catch (error) {
      if (error.codigo === "CORREO_SIN_VERIFICAR") {
        sessionStorage.setItem(
          CLAVES_SESION.aviso,
          "Verifica tu correo para activar tu cuenta: escribe el código que te enviamos o pide uno nuevo.",
        );
        window.location.href = `/app/registro?verificar=${encodeURIComponent(correo)}`;
        return;
      }
      Aviso.deError(error);
      botonIngresar.disabled = false;
      botonIngresar.classList.remove("cargando");
    }
  });
})();
