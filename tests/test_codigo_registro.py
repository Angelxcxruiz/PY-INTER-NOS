"""Código de verificación del registro: pruebas unitarias, sin base de datos."""

import re
import uuid
from datetime import timedelta

import pytest

from app.core.clock import ahora
from app.core.config import obtener_configuracion
from app.core.exceptions import ErrorDominio
from app.core.security import generar_codigo_numerico, hash_codigo_registro
from app.modules.auth import service as modulo_servicio
from app.modules.auth.models import CodigoRegistro, Usuario
from app.modules.auth.service import MENSAJE_CODIGO_INVALIDO, ServicioUsuarios

USUARIO_ID = str(uuid.uuid4())
CODIGO = "042917"  # con cero a la izquierda a propósito


def test_el_codigo_generado_tiene_seis_digitos_y_solo_numeros() -> None:
    codigos = {generar_codigo_numerico(6) for _ in range(300)}

    assert all(re.fullmatch(r"\d{6}", codigo) for codigo in codigos)
    assert len(codigos) > 250  # no es constante ni repetitivo


def test_el_hash_es_estable_y_no_coincide_con_el_codigo_en_claro() -> None:
    primero = hash_codigo_registro(USUARIO_ID, CODIGO)

    assert primero == hash_codigo_registro(USUARIO_ID, CODIGO)
    assert primero != CODIGO and CODIGO not in primero
    assert len(primero) == 64
    # Atado al usuario y al código; los espacios no cambian el resultado.
    assert primero != hash_codigo_registro(str(uuid.uuid4()), CODIGO)
    assert primero != hash_codigo_registro(USUARIO_ID, "042918")
    assert primero == hash_codigo_registro(USUARIO_ID, " 042 917 ")


class DbFalsa:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _objeto) -> None:
        pass


class RepositorioFalso:
    def __init__(self, usuario, fila) -> None:
        self.usuario = usuario
        self.fila = fila

    def por_correo(self, correo):
        return self.usuario if self.usuario and self.usuario.correo == correo else None

    def ultimo_codigo_registro(self, _usuario_id):
        return self.fila


def _usuario(rol: str = "ESTUDIANTE", estado: str = "SIN_VERIFICAR") -> Usuario:
    return Usuario(
        id=USUARIO_ID,
        nombre="Ana",
        correo="ana@prueba.edu",
        rol=rol,
        activo=True,
        estado_cuenta=estado,
        correo_verificado=False,
        creado_en=ahora(),
        actualizado_en=ahora(),
    )


def _fila(**cambios) -> CodigoRegistro:
    valores = {
        "id": str(uuid.uuid4()),
        "usuario_id": USUARIO_ID,
        "codigo_hash": hash_codigo_registro(USUARIO_ID, CODIGO),
        "expira_en": ahora() + timedelta(minutes=10),
        "intentos": 0,
        "usado_en": None,
        "creada_en": ahora(),
    }
    valores.update(cambios)
    return CodigoRegistro(**valores)


@pytest.fixture
def eventos(monkeypatch) -> list[str]:
    publicados: list[str] = []
    monkeypatch.setattr(
        modulo_servicio, "publicar", lambda _db, tipo, *_resto: publicados.append(tipo)
    )
    return publicados


def _servicio(usuario, fila) -> tuple[ServicioUsuarios, DbFalsa]:
    servicio = ServicioUsuarios.__new__(ServicioUsuarios)
    servicio.db = DbFalsa()
    servicio.repositorio = RepositorioFalso(usuario, fila)
    servicio.reloj = None
    servicio.configuracion = obtener_configuracion()
    return servicio, servicio.db


@pytest.mark.parametrize(
    "cambios",
    [
        {"expira_en": ahora() - timedelta(seconds=1)},  # vencido
        {"usado_en": ahora()},  # ya usado
        {"intentos": obtener_configuracion().codigo_registro_max_intentos},  # intentos agotados
        {"codigo_hash": None},  # el correo aún no generó el código
    ],
    ids=["vencido", "usado", "intentos_agotados", "sin_generar"],
)
def test_un_codigo_vencido_usado_o_agotado_da_un_error_claro(cambios, eventos) -> None:
    usuario = _usuario()
    fila = _fila(**cambios)
    servicio, _ = _servicio(usuario, fila)

    with pytest.raises(ErrorDominio) as error:
        servicio.verificar_registro(usuario.correo, CODIGO)  # el código es el correcto

    assert error.value.codigo == "CODIGO_INVALIDO"
    assert error.value.mensaje == MENSAJE_CODIGO_INVALIDO
    assert usuario.estado_cuenta == "SIN_VERIFICAR"
    assert eventos == []


def test_un_codigo_incorrecto_suma_un_intento_y_lo_deja_guardado(eventos) -> None:
    usuario, fila = _usuario(), _fila()
    servicio, db = _servicio(usuario, fila)

    with pytest.raises(ErrorDominio):
        servicio.verificar_registro(usuario.correo, "000000")

    assert fila.intentos == 1 and db.commits == 1
    assert usuario.estado_cuenta == "SIN_VERIFICAR"


@pytest.mark.parametrize(("rol", "esperado"), [("ESTUDIANTE", "ACTIVO"), ("DOCENTE", "PENDIENTE")])
def test_un_codigo_correcto_activa_o_deja_pendiente_segun_el_rol(rol, esperado, eventos) -> None:
    usuario, fila = _usuario(rol=rol), _fila()
    servicio, _ = _servicio(usuario, fila)

    resultado = servicio.verificar_registro(usuario.correo, CODIGO)

    assert resultado.estado_cuenta == esperado
    assert usuario.correo_verificado is True and fila.usado_en is not None
    assert eventos == ["REGISTRO_VERIFICADO"]


def test_un_correo_desconocido_o_ya_verificado_da_el_mismo_error(eventos) -> None:
    sin_usuario, _ = _servicio(None, None)
    activo = _usuario(estado="ACTIVO")
    ya_verificado, _ = _servicio(activo, _fila())

    for servicio, correo in ((sin_usuario, "nadie@prueba.edu"), (ya_verificado, activo.correo)):
        with pytest.raises(ErrorDominio) as error:
            servicio.verificar_registro(correo, CODIGO)
        assert error.value.mensaje == MENSAJE_CODIGO_INVALIDO
