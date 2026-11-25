"""Registro con verificación por código y aprobación de docentes (Fases 11 y 11b), contra MySQL."""

import json
import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.database import SessionLocal
from app.core.security import hash_contrasena, verificar_jwt
from app.modules.auth.models import CodigoRegistro, Permiso, Usuario, UsuarioPermiso
from app.modules.cases.models import Caso
from app.modules.notifications.adapters import FakeAdapter
from app.modules.notifications.dependencies import construir_despachador
from app.modules.notifications.models import EventoOutbox, Notificacion
from app.modules.notifications.procesador import ProcesadorOutbox

TIPOS_EVENTO = (
    "REGISTRO_INICIADO",
    "REGISTRO_VERIFICADO",
    "DOCENTE_REGISTRADO",
    "DOCENTE_APROBADO",
    "DOCENTE_RECHAZADO",
)
CLAVE = "Clave-de-prueba-1"
CLAVE_ADMIN = "Admin-de-prueba-1"
URL_REGISTRO = "/api/v1/auth/registro"
URL_VERIFICAR = "/api/v1/auth/registro/verificar"
URL_REENVIAR = "/api/v1/auth/registro/reenviar"
URL_LOGIN = "/api/v1/auth/login"
CAMPOS_REGISTRO = {"usuario_id", "correo", "mensaje", "vigencia_segundos", "reenvio_segundos"}


def _dominio() -> str:
    return obtener_configuracion().dominio_principal


def _correo(prefijo: str = "u") -> str:
    return f"{prefijo}.{uuid.uuid4().hex[:10]}@{_dominio()}"


@pytest.fixture
def db(base_real):
    with SessionLocal() as sesion:
        yield sesion


@pytest.fixture
def limpieza(db):
    correos: list[str] = []
    yield correos
    db.rollback()
    ids = list(db.scalars(select(Usuario.id).where(Usuario.correo.in_(correos))).all())
    db.execute(delete(EventoOutbox).where(EventoOutbox.tipo.in_(TIPOS_EVENTO)))
    db.execute(delete(Caso).where(Caso.docente_creador_id.in_(ids)))
    db.execute(delete(Usuario).where(Usuario.id.in_(ids)))
    db.commit()


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def permiso_crear_casos(db) -> Permiso:
    permiso = db.scalar(select(Permiso).where(Permiso.codigo == "CREAR_CASOS"))
    if permiso is None:
        permiso = Permiso(codigo="CREAR_CASOS", nombre="Crear casos")
        db.add(permiso)
        db.commit()
    return permiso


@pytest.fixture
def admin(cliente, db, limpieza) -> dict:
    momento = ahora()
    usuario = Usuario(
        nombre="Admin de prueba",
        correo=_correo("admin"),
        hash_contrasena=hash_contrasena(CLAVE_ADMIN),
        rol="ADMINISTRADOR",
        activo=True,
        correo_verificado=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db.add(usuario)
    db.commit()
    limpieza.append(usuario.correo)
    acceso = cliente.post(
        URL_LOGIN, json={"correo": usuario.correo, "contrasena": CLAVE_ADMIN}
    ).json()["token_acceso"]
    return {"id": usuario.id, "cabeceras": {"Authorization": f"Bearer {acceso}"}}


def _procesar(db, adapter: FakeAdapter) -> None:
    ProcesadorOutbox(db, construir_despachador(adapter)).procesar_lote(100)


def _codigo_enviado(adapter: FakeAdapter, correo: str) -> str:
    """Lee el código del correo que recibió el usuario (el único lugar donde existe en claro)."""
    textos = [
        envio["texto"]
        for envio in adapter.envios
        if envio["destinatario"] == correo and "verificación" in envio["asunto"]
    ]
    assert textos, f"no se envió ningún código a {correo}"
    coincidencia = re.search(r"(?<!\d)(\d{6})(?!\d)", textos[-1])
    assert coincidencia, "el correo no trae un código de 6 dígitos"
    return coincidencia.group(1)


def _registrar(cliente, limpieza, rol: str, **cambios):
    datos = {"nombre": "Persona de Prueba", "correo": _correo(rol.lower()), "contrasena": CLAVE}
    datos["rol"] = rol
    datos.update(cambios)
    limpieza.append(datos["correo"])
    return datos, cliente.post(URL_REGISTRO, json=datos)


def _alta(cliente, db, adapter, limpieza, rol: str, **cambios) -> dict:
    """Registra y procesa el outbox: deja el código en el 'correo' del FakeAdapter."""
    datos, respuesta = _registrar(cliente, limpieza, rol, **cambios)
    assert respuesta.status_code == 201, respuesta.text
    _procesar(db, adapter)
    datos["codigo"] = _codigo_enviado(adapter, datos["correo"])
    return datos


def _verificar(cliente, correo: str, codigo: str):
    return cliente.post(URL_VERIFICAR, json={"correo": correo, "codigo": codigo})


def _alta_verificada(cliente, db, adapter, limpieza, rol: str, **cambios) -> dict:
    datos = _alta(cliente, db, adapter, limpieza, rol, **cambios)
    respuesta = _verificar(cliente, datos["correo"], datos["codigo"])
    assert respuesta.status_code == 200, respuesta.text
    return datos


def _entrar(cliente, correo: str, contrasena: str = CLAVE):
    return cliente.post(URL_LOGIN, json={"correo": correo, "contrasena": contrasena})


def _cabeceras(respuesta) -> dict:
    return {"Authorization": f"Bearer {respuesta.json()['token_acceso']}"}


def _usuario(db, correo: str) -> Usuario:
    db.rollback()  # REPEATABLE READ: relee lo que escribió la API
    return db.scalar(select(Usuario).where(Usuario.correo == correo))


def _fila_codigo(db, correo: str) -> CodigoRegistro:
    usuario = _usuario(db, correo)
    return db.scalar(select(CodigoRegistro).where(CodigoRegistro.usuario_id == usuario.id))


def _codigo_incorrecto(correcto: str) -> str:
    return f"{(int(correcto) + 1) % 1_000_000:06d}"


CASO = {
    "nombre": "Caso del docente aprobado",
    "desarrollo_situacional": "Desarrollo",
    "contexto_historia": "Historia",
    "tiempo_estimado_min": 30,
}


# --- Registro y verificación por código -----------------------------------------------------


def test_registro_crea_cuenta_sin_verificar_y_el_login_la_rechaza(cliente, db, limpieza) -> None:
    datos, registro = _registrar(cliente, limpieza, "ESTUDIANTE")

    assert registro.status_code == 201
    assert set(registro.json()) == CAMPOS_REGISTRO
    assert registro.json()["correo"] == datos["correo"]
    usuario = _usuario(db, datos["correo"])
    assert usuario.estado_cuenta == "SIN_VERIFICAR"
    assert _fila_codigo(db, datos["correo"]).codigo_hash is None  # aún no se generó el código

    acceso = _entrar(cliente, datos["correo"])
    assert acceso.status_code == 401
    assert acceso.json()["error"]["codigo"] == "CORREO_SIN_VERIFICAR"
    assert acceso.json()["error"]["detalles"]["reenviar"] == "/api/v1/auth/registro/reenviar"
    # Sin la contraseña correcta no se revela que la cuenta existe.
    otra = _entrar(cliente, datos["correo"], "otra-clave-12")
    assert otra.json()["error"]["mensaje"] == "Credenciales invalidas"


def test_el_codigo_nunca_aparece_en_la_respuesta_ni_en_el_outbox(
    cliente, db, adapter, limpieza
) -> None:
    datos, registro = _registrar(cliente, limpieza, "ESTUDIANTE")
    _procesar(db, adapter)
    codigo = _codigo_enviado(adapter, datos["correo"])

    assert re.fullmatch(r"\d{6}", codigo)
    assert codigo not in registro.text
    db.rollback()
    payloads = [e.payload for e in db.scalars(select(EventoOutbox)).all()]
    assert all(codigo not in json.dumps(payload) for payload in payloads)
    fila = _fila_codigo(db, datos["correo"])
    assert fila.codigo_hash is not None and len(fila.codigo_hash) == 64
    assert fila.codigo_hash != codigo
    evento = db.scalars(
        select(EventoOutbox).where(
            EventoOutbox.tipo == "REGISTRO_INICIADO",
            EventoOutbox.agregado_id == _usuario(db, datos["correo"]).id,
        )
    ).one()
    assert set(evento.payload) == {"usuario_id", "codigo_registro_id"}


def test_verificar_con_el_codigo_correcto_activa_al_estudiante(
    cliente, db, adapter, limpieza
) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "ESTUDIANTE")

    verificado = _verificar(cliente, datos["correo"], datos["codigo"])

    assert verificado.status_code == 200
    assert "ya puedes ingresar" in verificado.json()["mensaje"]
    assert verificado.json()["estado_cuenta"] == "ACTIVO"
    assert _usuario(db, datos["correo"]).correo_verificado is True
    assert _fila_codigo(db, datos["correo"]).usado_en is not None
    acceso = _entrar(cliente, datos["correo"])
    assert acceso.status_code == 200
    assert acceso.json()["usuario"]["rol"] == "ESTUDIANTE"
    # Un código solo se usa una vez.
    assert _verificar(cliente, datos["correo"], datos["codigo"]).status_code == 400


def test_verificar_con_codigo_incorrecto_no_activa_y_suma_un_intento(
    cliente, db, adapter, limpieza
) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "ESTUDIANTE")

    malo = _verificar(cliente, datos["correo"], _codigo_incorrecto(datos["codigo"]))

    assert malo.status_code == 400
    assert malo.json()["error"]["codigo"] == "CODIGO_INVALIDO"
    assert _usuario(db, datos["correo"]).estado_cuenta == "SIN_VERIFICAR"
    assert _fila_codigo(db, datos["correo"]).intentos == 1
    assert _entrar(cliente, datos["correo"]).status_code == 401


def test_al_sexto_intento_el_codigo_queda_invalidado(cliente, db, adapter, limpieza) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "ESTUDIANTE")
    maximo = obtener_configuracion().codigo_registro_max_intentos
    incorrecto = _codigo_incorrecto(datos["codigo"])

    for _ in range(maximo):
        assert _verificar(cliente, datos["correo"], incorrecto).status_code == 400
    # Ya agotado: ni siquiera el código correcto sirve.
    assert _verificar(cliente, datos["correo"], datos["codigo"]).status_code == 400
    assert _fila_codigo(db, datos["correo"]).intentos == maximo
    assert _usuario(db, datos["correo"]).estado_cuenta == "SIN_VERIFICAR"

    # Hay que pedir uno nuevo.
    fila = _fila_codigo(db, datos["correo"])
    fila.creada_en = ahora() - timedelta(minutes=5)
    db.commit()
    assert cliente.post(URL_REENVIAR, json={"correo": datos["correo"]}).status_code == 200
    _procesar(db, adapter)
    nuevo = _codigo_enviado(adapter, datos["correo"])
    assert _verificar(cliente, datos["correo"], nuevo).status_code == 200


def test_reenviar_respeta_el_cooldown_y_el_codigo_viejo_deja_de_servir(
    cliente, db, adapter, limpieza
) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "ESTUDIANTE")
    primero = datos["codigo"]
    usuario = _usuario(db, datos["correo"])

    def eventos() -> int:
        db.rollback()
        return db.scalar(
            select(func.count())
            .select_from(EventoOutbox)
            .where(EventoOutbox.tipo == "REGISTRO_INICIADO", EventoOutbox.agregado_id == usuario.id)
        )

    assert eventos() == 1
    for _ in range(2):  # dos seguidas, dentro del cooldown: no se emite nada
        assert cliente.post(URL_REENVIAR, json={"correo": datos["correo"]}).status_code == 200
    assert eventos() == 1

    fila = _fila_codigo(db, datos["correo"])
    espera = obtener_configuracion().codigo_registro_cooldown_seg + 5
    fila.creada_en = ahora() - timedelta(seconds=espera)
    db.commit()
    cliente.post(URL_REENVIAR, json={"correo": datos["correo"]})
    assert eventos() == 2
    _procesar(db, adapter)
    segundo = _codigo_enviado(adapter, datos["correo"])

    if segundo != primero:  # 1 de cada millón podría coincidir
        assert _verificar(cliente, datos["correo"], primero).status_code == 400
    assert _verificar(cliente, datos["correo"], segundo).status_code == 200


def test_reenviar_a_un_correo_inexistente_responde_igual_que_a_uno_existente(
    cliente, db, adapter, limpieza
) -> None:
    pendiente, _ = _registrar(cliente, limpieza, "ESTUDIANTE")
    verificado = _alta_verificada(cliente, db, adapter, limpieza, "ESTUDIANTE")

    respuestas = [
        cliente.post(URL_REENVIAR, json={"correo": correo})
        for correo in (pendiente["correo"], _correo("nadie"), verificado["correo"])
    ]

    assert {r.status_code for r in respuestas} == {200}
    assert len({json.dumps(r.json(), sort_keys=True) for r in respuestas}) == 1


def test_verificar_un_correo_inexistente_da_el_mismo_error_que_un_codigo_malo(
    cliente, db, adapter, limpieza
) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "ESTUDIANTE")

    inexistente = _verificar(cliente, _correo("nadie"), "123456")
    malo = _verificar(cliente, datos["correo"], _codigo_incorrecto(datos["codigo"]))

    assert inexistente.status_code == malo.status_code == 400
    assert inexistente.json() == malo.json()


def test_el_registro_acepta_el_dominio_configurado_y_rechaza_otros(
    cliente, limpieza, monkeypatch
) -> None:
    monkeypatch.setattr(obtener_configuracion(), "dominio_institucional", "unihumboldt.edu.co")
    bueno = f"sgaribello_{uuid.uuid4().hex[:6]}@unihumboldt.edu.co"
    limpieza.append(bueno)

    aceptado = cliente.post(
        URL_REGISTRO,
        json={"nombre": "Sofía", "correo": bueno, "contrasena": CLAVE, "rol": "ESTUDIANTE"},
    )
    rechazado = cliente.post(
        URL_REGISTRO,
        json={
            "nombre": "Otra",
            "correo": "alguien@gmail.com",
            "contrasena": CLAVE,
            "rol": "ESTUDIANTE",
        },
    )

    assert aceptado.status_code == 201
    assert rechazado.status_code == 422


def test_el_docente_puede_registrarse_con_cualquier_correo(cliente, limpieza, monkeypatch) -> None:
    monkeypatch.setattr(obtener_configuracion(), "dominio_institucional", "unihumboldt.edu.co")
    correo = f"profe_{uuid.uuid4().hex[:8]}@gmail.com"
    limpieza.append(correo)

    docente = cliente.post(
        URL_REGISTRO,
        json={"nombre": "Profe", "correo": correo, "contrasena": CLAVE, "rol": "DOCENTE"},
    )
    estudiante = cliente.post(
        URL_REGISTRO,
        json={"nombre": "Est", "correo": correo, "contrasena": CLAVE, "rol": "ESTUDIANTE"},
    )

    assert docente.status_code == 201
    assert estudiante.status_code == 422


# --- Aprobación de docentes ---------------------------------------------------------------


def test_docente_verificado_queda_pendiente_hasta_que_el_admin_lo_aprueba(
    cliente, db, adapter, limpieza, admin
) -> None:
    datos = _alta(cliente, db, adapter, limpieza, "DOCENTE")
    docente = _usuario(db, datos["correo"])
    # Sin verificar todavía: no es solicitud y el admin no recibió ningún aviso.
    pendientes = cliente.get("/api/v1/admin/solicitudes?limite=100", headers=admin["cabeceras"])
    assert docente.id not in [fila["id"] for fila in pendientes.json()]
    db.rollback()
    avisos_antes = db.scalar(
        select(func.count()).select_from(Notificacion).where(Notificacion.usuario_id == admin["id"])
    )
    assert avisos_antes == 0

    verificado = _verificar(cliente, datos["correo"], datos["codigo"])
    assert "revisada por el administrador" in verificado.json()["mensaje"]
    _procesar(db, adapter)

    docente = _usuario(db, datos["correo"])
    assert docente.estado_cuenta == "PENDIENTE"
    permisos = db.scalar(
        select(func.count())
        .select_from(UsuarioPermiso)
        .where(UsuarioPermiso.usuario_id == docente.id)
    )
    assert permisos == 0
    pendientes = cliente.get("/api/v1/admin/solicitudes?limite=100", headers=admin["cabeceras"])
    assert docente.id in [fila["id"] for fila in pendientes.json()]
    avisos = db.scalars(
        select(Notificacion).where(
            Notificacion.usuario_id == admin["id"], Notificacion.tipo == "REGISTRO_VERIFICADO"
        )
    ).all()
    assert len(avisos) == 1

    acceso = _entrar(cliente, datos["correo"])
    assert acceso.status_code == 200
    claims = verificar_jwt(acceso.json()["token_acceso"])
    assert (claims["estado_cuenta"], claims["permisos"]) == ("PENDIENTE", [])
    yo = cliente.get("/api/v1/auth/me", headers=_cabeceras(acceso))
    assert yo.json()["estado_cuenta"] == "PENDIENTE"


def test_docente_pendiente_no_puede_crear_casos_ni_ver_sesiones(
    cliente, db, adapter, limpieza
) -> None:
    datos = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    cabeceras = _cabeceras(_entrar(cliente, datos["correo"]))

    crear = cliente.post("/api/v1/cases", headers=cabeceras, json=CASO)
    assert crear.status_code == 403
    assert "cuenta está en revisión" in crear.json()["error"]["mensaje"]
    for ruta in ("/api/v1/cases", "/api/v1/sessions", "/api/v1/espacios-academicos"):
        assert cliente.get(ruta, headers=cabeceras).status_code == 403, ruta


def test_admin_aprueba_y_el_docente_ya_puede_crear_casos(
    cliente, db, adapter, limpieza, admin, permiso_crear_casos
) -> None:
    datos = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    docente = _usuario(db, datos["correo"])

    aprobada = cliente.post(
        f"/api/v1/admin/solicitudes/{docente.id}/aprobar",
        headers=admin["cabeceras"],
        json={"permisos": ["CREAR_CASOS"]},
    )

    assert aprobada.status_code == 200
    assert aprobada.json()["estado_cuenta"] == "ACTIVO"
    docente = _usuario(db, datos["correo"])
    assert docente.aprobado_por_id == admin["id"] and docente.aprobado_en is not None
    # El permiso entra en el token nuevo: debe volver a ingresar.
    cabeceras = _cabeceras(_entrar(cliente, datos["correo"]))
    assert cliente.post("/api/v1/cases", headers=cabeceras, json=CASO).status_code == 201


def test_admin_rechaza_y_el_login_devuelve_401_claro(cliente, db, adapter, limpieza, admin) -> None:
    datos = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    docente = _usuario(db, datos["correo"])

    rechazada = cliente.post(
        f"/api/v1/admin/solicitudes/{docente.id}/rechazar",
        headers=admin["cabeceras"],
        json={"motivo": "No pertenece a la facultad"},
    )

    assert rechazada.json()["estado_cuenta"] == "RECHAZADO"
    acceso = _entrar(cliente, datos["correo"])
    assert acceso.status_code == 401
    assert acceso.json()["error"]["codigo"] == "CUENTA_RECHAZADA"
    asegurado = _entrar(cliente, datos["correo"], "otra-contrasena-1")
    assert asegurado.json()["error"]["mensaje"] == "Credenciales invalidas"


def test_aprobar_dos_veces_no_duplica_ni_falla(
    cliente, db, adapter, limpieza, admin, permiso_crear_casos
) -> None:
    datos = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    docente = _usuario(db, datos["correo"])
    url = f"/api/v1/admin/solicitudes/{docente.id}/aprobar"
    cuerpo = {"permisos": ["CREAR_CASOS"]}

    primera = cliente.post(url, headers=admin["cabeceras"], json=cuerpo)
    segunda = cliente.post(url, headers=admin["cabeceras"], json=cuerpo)

    assert primera.status_code == segunda.status_code == 200
    db.rollback()
    eventos = db.scalar(
        select(func.count())
        .select_from(EventoOutbox)
        .where(EventoOutbox.tipo == "DOCENTE_APROBADO", EventoOutbox.agregado_id == docente.id)
    )
    permisos = db.scalar(
        select(func.count())
        .select_from(UsuarioPermiso)
        .where(UsuarioPermiso.usuario_id == docente.id)
    )
    assert (eventos, permisos) == (1, 1)


def test_una_solicitud_rechazada_no_se_aprueba_ni_una_aprobada_se_rechaza(
    cliente, db, adapter, limpieza, admin
) -> None:
    rechazado = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    aprobado = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    id_rechazado = _usuario(db, rechazado["correo"]).id
    id_aprobado = _usuario(db, aprobado["correo"]).id
    base = "/api/v1/admin/solicitudes"
    cab = admin["cabeceras"]
    cliente.post(f"{base}/{id_rechazado}/rechazar", headers=cab, json={})
    cliente.post(f"{base}/{id_aprobado}/aprobar", headers=cab)

    assert cliente.post(f"{base}/{id_rechazado}/aprobar", headers=cab).status_code == 409
    assert cliente.post(f"{base}/{id_aprobado}/rechazar", headers=cab).status_code == 409
    assert cliente.post(f"{base}/{id_rechazado}/rechazar", headers=cab, json={}).status_code == 200


def test_correo_duplicado_da_409_con_el_mismo_mensaje_para_ambos_roles(
    cliente, db, adapter, limpieza
) -> None:
    estudiante = _alta_verificada(cliente, db, adapter, limpieza, "ESTUDIANTE")
    docente, _ = _registrar(cliente, limpieza, "DOCENTE")  # sigue SIN_VERIFICAR

    mensajes = []
    for correo, rol in [
        (estudiante["correo"], "ESTUDIANTE"),
        (estudiante["correo"], "DOCENTE"),
        (docente["correo"], "DOCENTE"),
        (docente["correo"], "ESTUDIANTE"),
    ]:
        respuesta = cliente.post(
            URL_REGISTRO,
            json={"nombre": "X", "correo": correo, "contrasena": CLAVE, "rol": rol},
        )
        assert respuesta.status_code == 409
        mensajes.append(respuesta.json()["error"]["mensaje"])

    assert len(set(mensajes)) == 1
    assert "estudiante" not in mensajes[0].lower() and "docente" not in mensajes[0].lower()


def test_estudiante_creado_por_convocatoria_no_entra_con_contrasena(cliente, db, limpieza) -> None:
    momento = ahora()
    sin_clave = Usuario(
        nombre="Convocado",
        correo=_correo("conv"),
        hash_contrasena=None,
        rol="ESTUDIANTE",
        activo=True,
        creado_en=momento,
        actualizado_en=momento,
    )
    db.add(sin_clave)
    db.commit()
    limpieza.append(sin_clave.correo)

    assert _entrar(cliente, sin_clave.correo, CLAVE).status_code == 401


def test_solicitudes_y_filtro_de_usuarios_son_solo_del_administrador(
    cliente, db, adapter, limpieza, admin
) -> None:
    estudiante = _alta_verificada(cliente, db, adapter, limpieza, "ESTUDIANTE")
    docente = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    cab_estudiante = _cabeceras(_entrar(cliente, estudiante["correo"]))

    assert cliente.get("/api/v1/admin/solicitudes").status_code == 401
    assert cliente.get("/api/v1/admin/solicitudes", headers=cab_estudiante).status_code == 403
    filtrados = cliente.get(
        "/api/v1/admin/users?estado_cuenta=PENDIENTE&limite=100", headers=admin["cabeceras"]
    )
    assert docente["correo"] in [fila["correo"] for fila in filtrados.json()]
    assert {fila["estado_cuenta"] for fila in filtrados.json()} == {"PENDIENTE"}
    invalido = cliente.get("/api/v1/admin/users?estado_cuenta=OTRO", headers=admin["cabeceras"])
    assert invalido.status_code == 422


def test_eventos_avisan_por_correo_al_docente_aprobado_y_rechazado(
    cliente, db, adapter, limpieza, admin
) -> None:
    aprobado = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    rechazado = _alta_verificada(cliente, db, adapter, limpieza, "DOCENTE")
    base = "/api/v1/admin/solicitudes"
    cab = admin["cabeceras"]
    cliente.post(f"{base}/{_usuario(db, aprobado['correo']).id}/aprobar", headers=cab)
    cliente.post(
        f"{base}/{_usuario(db, rechazado['correo']).id}/rechazar",
        headers=cab,
        json={"motivo": "Sin vínculo con la facultad"},
    )

    _procesar(db, adapter)
    _procesar(db, adapter)  # reprocesar no duplica nada

    decisiones = {
        envio["destinatario"]: envio
        for envio in adapter.envios
        if "verificación" not in envio["asunto"]
    }
    assert "aprobada" in decisiones[aprobado["correo"]]["asunto"]
    assert "Sin vínculo con la facultad" in decisiones[rechazado["correo"]]["texto"]
    destinatarios = [envio["destinatario"] for envio in adapter.envios]
    assert destinatarios.count(aprobado["correo"]) == 2  # código + aprobación
