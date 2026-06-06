"""PyInstaller runtime hook: fix python-docx template resolution when frozen.

python-docx's FooterPart/HeaderPart resolve their default XML via a path
relative to docx/parts/ ( ../templates/default-*.xml ). In a onefile build the
classmethod __file__ can resolve to a parts/ directory that does not physically
exist in the MEIPASS extraction tree, so the relative open() fails. This hook
rebinds those classmethods to read from the collected MEIPASS/docx/templates.
"""
import os
import sys

meipass = getattr(sys, "_MEIPASS", None)
if meipass:
    tpl_dir = os.path.join(meipass, "docx", "templates")
    if os.path.isdir(tpl_dir):
        try:
            from docx.parts.hdrftr import FooterPart, HeaderPart

            def _read(name):
                with open(os.path.join(tpl_dir, name), "rb") as f:
                    return f.read()

            FooterPart._default_footer_xml = classmethod(
                lambda cls: _read("default-footer.xml"))
            HeaderPart._default_header_xml = classmethod(
                lambda cls: _read("default-header.xml"))
        except Exception:
            pass
