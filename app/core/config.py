import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor que trae .env.example en los secretos: los scripts de seed se niegan a usarlo.
MARCADOR_SECRETO = "CAMBIAR-EN-PRODUCCION"

# Secretos que estuvieron publicados en el repositorio: se dan por comprometidos y la API no
# arranca con ellos. La clave Fernet se compara por su huella para no volver a escribirla aquí.
_SECRETOS_RECHAZADOS = {MARCADOR_SECRETO, "cambiar-en-entorno", "cambiar-por-un-secreto-largo"}
_HUELLAS_RECHAZADAS = {"1aeb65c7564634b9f6da4342629ec840b21019a6acfca0944e0576b6031dc906"}

_AYUDA_SECRETOS = (
    "Defina valores propios en el .env.\n"
    '  JWT_SECRET: python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
    '  FERNET_KEY: python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())"'
)


def _es_secreto_publico(valor: str) -> bool:
    huella = hashlib.sha256(valor.encode("utf-8")).hexdigest()
    return valor in _SECRETOS_RECHAZADOS or huella in _HUELLAS_RECHAZADAS


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Los errores de validación no deben imprimir el valor de entrada: incluiría secretos.
        hide_input_in_errors=True,
    )

    database_url: str = Field(
        default="mysql+pymysql://inter_nos:inter_nos@127.0.0.1:3306/inter_nos?charset=utf8mb4",
    )
    test_database_url: str | None = None
    jwt_secreto: str = Field(default="", validation_alias="JWT_SECRET")
    jwt_expira_min: int = Field(default=60, validation_alias="JWT_EXPIRA_MIN")
    fernet_key: str = Field(default="", validation_alias="FERNET_KEY")
    # Lista separada por comas (varios dominios). Sin valor por defecto: la API no arranca sin él.
    dominio_institucional: str = Field(default="", validation_alias="DOMINIO_INSTITUCIONAL")
    frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")
    email_backend: str = Field(default="consola", validation_alias="EMAIL_BACKEND")
    smtp_host: str = Field(default="127.0.0.1", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")
    smtp_remitente: str | None = Field(default=None, validation_alias="SMTP_REMITENTE")
    escala_nota_max: str = Field(default="5.00", validation_alias="ESCALA_NOTA_MAX")
    nota_aprobatoria: str = Field(default="3.00", validation_alias="NOTA_APROBATORIA")
    fraccion_ingreso_tardio: str = Field(
        default="0.5",
        validation_alias="FRACCION_INGRESO_TARDIO",
    )
    csv_separador: str = Field(default=";", validation_alias="CSV_SEPARADOR")
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ORIGINS",
    )
    token_restablecer_expira_min: int = Field(
        default=60,
        validation_alias="TOKEN_RESTABLECER_EXPIRA_MIN",
    )
    token_cooldown_seg: int = Field(default=60, validation_alias="TOKEN_COOLDOWN_SEG")
    verificacion_expira_horas: int = Field(default=48, validation_alias="VERIFICACION_EXPIRA_HORAS")
    verificacion_cooldown_min: int = Field(default=5, validation_alias="VERIFICACION_COOLDOWN_MIN")
    exigir_correo_verificado: bool = Field(
        default=False, validation_alias="EXIGIR_CORREO_VERIFICADO"
    )
    dias_cierre_automatico: int = Field(
        default=1,
        validation_alias="DIAS_CIERRE_AUTOMATICO",
    )
    max_intentos: int = Field(default=5, validation_alias="MAX_INTENTOS")
    outbox_max_intentos: int = Field(default=5, validation_alias="OUTBOX_MAX_INTENTOS")
    outbox_intervalo_seg: int = Field(default=10, validation_alias="OUTBOX_INTERVALO_SEG")
    worker_intervalo_expiracion_seg: int = Field(
        default=60,
        validation_alias="WORKER_INTERVALO_EXPIRACION_SEG",
    )
    worker_intervalo_cierre_seg: int = Field(
        default=300,
        validation_alias="WORKER_INTERVALO_CIERRE_SEG",
    )
    admin_inicial_nombre: str | None = Field(
        default=None,
        validation_alias="ADMIN_INICIAL_NOMBRE",
    )
    admin_inicial_correo: str | None = Field(
        default=None,
        validation_alias="ADMIN_INICIAL_CORREO",
    )
    admin_inicial_contrasena: str | None = Field(
        default=None,
        validation_alias="ADMIN_INICIAL_CONTRASENA",
    )
    docente_password: str | None = Field(default=None, validation_alias="DOCENTE_PASSWORD")
    # Registro con verificación por código de 6 dígitos (Fase 11b).
    codigo_registro_expira_min: int = Field(
        default=15, ge=1, validation_alias="CODIGO_REGISTRO_EXPIRA_MIN"
    )
    codigo_registro_max_intentos: int = Field(
        default=5, ge=1, validation_alias="CODIGO_REGISTRO_MAX_INTENTOS"
    )
    codigo_registro_cooldown_seg: int = Field(
        default=60, ge=0, validation_alias="CODIGO_REGISTRO_COOLDOWN_SEG"
    )
    # Archivos subidos por el docente (editor visual de escenarios, Fase 14). Solo se pide el
    # puerto PuertoAlmacenamiento; "local" escribe en disco y "s3" está reservado (sin implementar).
    almacenamiento_backend: str = Field(default="local", validation_alias="ALMACENAMIENTO_BACKEND")
    almacenamiento_dir: str = Field(default="uploads", validation_alias="ALMACENAMIENTO_DIR")
    # Tras responder al registro, intenta enviar el correo en el mismo proceso de la API, sin
    # esperar al worker. El outbox sigue siendo la fuente de verdad (el worker reintenta).
    despacho_inmediato: bool = Field(default=True, validation_alias="DESPACHO_INMEDIATO")

    @model_validator(mode="after")
    def _exigir_dominio(self) -> "Configuracion":
        if not self.dominios_permitidos:
            raise ValueError(
                "Configuracion incompleta: DOMINIO_INSTITUCIONAL no esta definida. "
                "Use el dominio de su institucion, o varios separados por comas "
                "(ej. unihumboldt.edu.co,humboldt.edu.co)."
            )
        return self

    @property
    def dominios_permitidos(self) -> list[str]:
        """Dominios de correo aceptados (minúsculas, sin '@')."""
        return [
            dominio.strip().lstrip("@").lower()
            for dominio in self.dominio_institucional.split(",")
            if dominio.strip().lstrip("@")
        ]

    @property
    def dominio_principal(self) -> str:
        """Primer dominio de la lista: el que usan los scripts y el remitente por defecto."""
        return self.dominios_permitidos[0]

    @model_validator(mode="after")
    def _exigir_secretos_propios(self) -> "Configuracion":
        problemas = []
        for variable, valor in (("JWT_SECRET", self.jwt_secreto), ("FERNET_KEY", self.fernet_key)):
            valor = valor.strip()
            if not valor:
                problemas.append(f"{variable} no esta definida")
            elif _es_secreto_publico(valor):
                problemas.append(f"{variable} sigue con un valor de ejemplo o publicado")
        if self.fernet_key.strip() and not _es_secreto_publico(self.fernet_key.strip()):
            try:
                Fernet(self.fernet_key.strip().encode("utf-8"))
            except ValueError:
                problemas.append("FERNET_KEY no es una clave Fernet valida")
        if problemas:
            raise ValueError(f"Configuracion insegura: {'; '.join(problemas)}.\n{_AYUDA_SECRETOS}")
        return self

    @property
    def cors_origins_lista(self) -> list[str]:
        return [origen.strip() for origen in self.cors_origins.split(",") if origen.strip()]


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()
