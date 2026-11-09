# Cómo contribuir

Gracias por el interés en ADB Bridge. Este repositorio lo mantiene NEZU S.A.S. y lo publicamos para que clientes, integradores y colaboradores puedan consultarlo, instalarlo y proponer mejoras. La [licencia](LICENSE.md) explica qué está permitido.

## Antes de empezar

- Para fallos de seguridad, sigue la [política de seguridad](SECURITY.md); no abras un issue público.
- Para un fallo o una propuesta, abre un issue con la plantilla que corresponda. Así acordamos el cambio antes de que escribas código.
- Para dudas de instalación o de uso en tu caso, también sirve un issue; si prefieres que lo hagamos nosotros, [escríbenos](https://nezuecuador.com/es/contacto).

## Pull requests

1. Parte de `main` en una rama con un nombre descriptivo.
2. Un cambio por pull request, pequeño y explicado: qué resuelve y cómo lo probaste.
3. Antes de enviarlo, ejecuta las comprobaciones del proyecto (Python 3 y FastAPI): `python -m compileall main.py`.
4. Mantén el estilo del código existente y no añadas dependencias sin justificarlas en la descripción.
5. No incluyas secretos, direcciones internas ni datos de clientes en código, pruebas ni capturas.

Revisamos cada pull request y respondemos en el propio hilo. Al enviarlo aceptas que tu aportación se publique bajo la licencia de este repositorio.

## Commits

Mensajes en imperativo y con prefijo de tipo, como en el historial: `fix: …`, `feat: …`, `docs: …`, `chore: …`.
