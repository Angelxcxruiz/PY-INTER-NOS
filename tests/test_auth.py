from datetime import UTC, datetime

from app.core.exceptions import ErrorAutenticacion
from app.modules.auth import models
from app.modules.auth.service import ServicioUsuarios


class RelojFalso:
    def ahora(self) -> datetime:
        return datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


class RepositorioFalso:
    def __init__(self, usuario) -> None:
        self.usuario = usuario

    def por_correo(self, correo: str):
        if correo == self.usuario.correo:
            return self.usuario
        return None

    def permisos(self, usuario):
        return ["CREAR_CASOS"]


def usuario_docente():
    ahora = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    return models.Usuario(
        id="11111111-1111-1111-1111-111111111111",
        nombre="Docente Uno",
        correo="docente@unal.edu.co",
        hash_contrasena="hash",
        rol="DOCENTE",
        activo=True,
        creado_en=ahora,
        actualizado_en=ahora,
    )


def test_login_rechaza_credenciales_sin_hacer_sql() -> None:
    usuario = usuario_docente()
    usuario.hash_contrasena = None
    servicio = ServicioUsuarios(db=None, reloj=RelojFalso())
    servicio.repositorio = RepositorioFalso(usuario)

    try:
        servicio.login(usuario.correo, "clave")
    except ErrorAutenticacion as exc:
        assert exc.codigo == "NO_AUTENTICADO"
    else:
        raise AssertionError("Debe rechazar credenciales invalidas")
