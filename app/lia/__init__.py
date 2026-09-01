"""
lia/__init__.py — Pacote de infraestrutura da Lia.

Agrupa a lógica de configuração, caminhos, logs e depuração em módulos de
responsabilidade única, para que o entry point (app/lia_app.py) fique enxuto e
o processo possa ser depurado facilmente.

Módulos:
    config   — constantes do projeto (caminhos, portas, paletas, tamanhos, i18n)
    paths    — auxiliares de caminho (diretórios de dados/artefatos)
    log      — logger estruturado por categoria (console + arquivo)
    debug    — coleta de contexto de depuração (config, logs, estado)
"""

from . import config, paths, log, debug

__all__ = ["config", "paths", "log", "debug"]
