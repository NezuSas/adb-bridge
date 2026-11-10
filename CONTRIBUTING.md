# Cómo contribuir

Gracias por el interés en ADB Bridge. Este repositorio lo mantiene NEZU S.A.S. y lo publicamos para que clientes, integradores y colaboradores puedan consultarlo, instalarlo y proponer mejoras. Se publica bajo la [licencia Apache 2.0](LICENSE).

## Antes de empezar

- Para fallos de seguridad, sigue la [política de seguridad](SECURITY.md); no abras un issue público.
- Para un fallo o una propuesta, abre un issue con la plantilla que corresponda. Así acordamos el cambio antes de que escribas código.
- Para dudas de instalación o de uso en tu caso, también sirve un issue; si prefieres que lo hagamos nosotros, [escríbenos](https://nezuecuador.com/es/contacto).

## Pull requests

1. Parte de `main` en una rama con un nombre descriptivo.
2. Un cambio por pull request, pequeño y explicado: qué resuelve y cómo lo probaste.
3. Antes de enviarlo, ejecuta las comprobaciones del proyecto desde la raíz (Python 3.10 o superior):

   ```bash
   pip install -r requirements-dev.txt
   ruff check . && ruff format --check .
   pytest
   ```

   Las pruebas usan un `adb` simulado (`tests/conftest.py`), así que no hace falta ningún dispositivo. Un cambio de comportamiento viene con su prueba; si corriges un fallo, añade primero la prueba que lo reproduce.
4. Mantén el estilo del código existente (`ruff format` lo aplica) y no añadas dependencias sin justificarlas en la descripción.
5. No incluyas secretos, direcciones internas ni datos de clientes en código, pruebas ni capturas.
6. Anota el cambio en [CHANGELOG.md](CHANGELOG.md), en la sección de la próxima versión.

Revisamos cada pull request y respondemos en el propio hilo. Al enviarlo aceptas que tu aportación se publique bajo la licencia Apache 2.0 de este repositorio.

## Commits

Mensajes en imperativo y con prefijo de tipo, como en el historial: `fix: …`, `feat: …`, `docs: …`, `chore: …`.
