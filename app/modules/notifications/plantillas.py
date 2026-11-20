from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

directorio = Path(__file__).parent / "templates"
entorno = Environment(
    loader=FileSystemLoader(directorio),
    autoescape=select_autoescape(["html", "xml"]),
)


def renderizar(
    nombre_html: str,
    nombre_texto: str,
    datos: dict,
) -> tuple[str, str]:
    html = entorno.get_template(nombre_html).render(**datos)
    texto = entorno.get_template(nombre_texto).render(**datos)
    return html, texto
