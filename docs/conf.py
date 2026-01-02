from pathlib import Path
import sys

project = "KaivosAI"
author = "KaivosAI"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from version import VERSION

release = VERSION
version = VERSION

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
]

autosummary_generate = True
autodoc_member_order = "bysource"

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

language = "fi"

html_theme = "alabaster"
html_static_path = ["_static"]
